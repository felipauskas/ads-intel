#!/usr/bin/env python3
"""Live QSR eval for ads-intel. Runs brand x country pairs through the real
host web_extract bridge (reuses scripts/stress_e2e.py machinery).

Per pair, writes a self-contained folder under ``evals/live-matrix/``:

    <brand-slug>-<CC>/
        result.json    search + advertiser + check1 + check2 summaries
        ads.json       full ad objects (limit 20 per search)
        attempts.json  every web_extract dispatch attempt
        summary.md     counts, page names, statuses, currency spot-check
        artifacts/     checked-in copies: check1 report+digest at the root,
                       check2's under check2/ (distinct, never overwritten)

Usage:
    .venv/bin/python evals/live_eval.py --smoke   # one pair: KFC/AE
    .venv/bin/python evals/live_eval.py           # full 5x5 matrix
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sources  # noqa: E402
import tools  # noqa: E402

# Brand -> advertiser page-name filter. Apostrophes are kept: quoting was ruled
# out as a cause on 2026-11-08. The filter must be the page's display name, not
# a short form: Meta renders the Domino's page as "Domino's Pizza", and the old
# "Domino's" filter rejected it at substring 0.60 on all five countries.
BRANDS: tuple[tuple[str, str], ...] = (
    ("KFC", "KFC"),
    ("McDonald's", "McDonald's"),
    ("Burger King", "Burger King"),
    ("Domino's Pizza", "Domino's Pizza"),
    ("Pizza Hut", "Pizza Hut"),
)
COUNTRIES: tuple[str, ...] = ("AE", "SA", "EG", "US", "GB")
OUT_ROOT = ROOT / "evals" / "live-matrix"

SEARCH_LIMIT = 20
CHECK1_LIMIT = 20

# Only invisible characters are removed from saved files; Arabic copy and every
# other byte of creative text stay verbatim.
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")

# The Hermes install whose dependency environment can actually serve
# web_extract (the plugin's own .venv is stdlib + pytest only).
HERMES_HOME = Path(
    os.environ.get("HERMES_INSTALL", str(Path.home() / ".hermes" / "hermes-agent"))
)

_RUNTIME_PRELUDE = r"""
import os, sys
os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)
os.environ.pop("VIRTUAL_ENV", None)
sys.path.insert(0, %(root)r)
sys._hermes_pin_default_home = True
import hermes_bootstrap  # noqa: F401  - sets up the install's dependency paths
"""

_BRIDGE_CODE = r"""
import asyncio, json, sys

async def main():
    from tools.web_tools import web_extract_tool
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            out = await web_extract_tool(req["urls"], char_limit=req.get("char_limit"))
        except BaseException as exc:  # noqa: BLE001 - reported to the driver
            out = json.dumps({"error": "%s: %s" % (type(exc).__name__, exc)})
        try:
            out = json.loads(out)
        except (TypeError, ValueError):
            pass
        sys.stdout.write("###RESULT###" + json.dumps(out) + "\n")
        sys.stdout.flush()

asyncio.run(main())
"""


def _runtime_argv() -> list[str] | None:
    """The command that runs code inside the live Hermes runtime."""
    hermes = shutil.which("hermes")
    if hermes:
        try:
            done = subprocess.run(
                [hermes, "--print-runtime-command"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            argv = json.loads(done.stdout)
            if isinstance(argv, list) and len(argv) >= 3 and argv[1] == "-I":
                return argv[:3]
        except Exception:
            pass
    candidates = sorted(
        str(p)
        for p in (Path.home() / ".hermes" / "tools").glob("python-*/bin/python3")
    )
    if candidates:
        return [candidates[-1], "-I", "-c"]
    return None


class _LiveBridge:
    """Subprocess bridge to the real host web_extract tool."""

    def __init__(self, timeout: float = 180.0) -> None:
        self.timeout = timeout
        self.argv = _runtime_argv()
        if not self.argv:
            raise RuntimeError(
                "could not resolve the Hermes runtime command "
                "(`hermes --print-runtime-command` and ~/.hermes/tools both failed)"
            )
        code = (_RUNTIME_PRELUDE % {"root": str(HERMES_HOME)}) + _BRIDGE_CODE
        self._err = tempfile.TemporaryFile(mode="w+")
        self.proc = subprocess.Popen(
            [*self.argv, code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._err,
            text=True,
            env=dict(os.environ),
            # Neutral cwd: the plugin repo has a `tools.py` that would shadow
            # the host's `tools` package.
            cwd=tempfile.gettempdir(),
        )
        self.log: list[str] = []

    def _stderr_tail(self) -> str:
        try:
            self._err.flush()
            self._err.seek(0)
            return self._err.read()[-2000:]
        except Exception:
            return ""

    def fetch(self, urls: list[str], char_limit: int | None = None) -> Any:
        assert self.proc.stdin and self.proc.stdout
        payload = json.dumps({"urls": urls, "char_limit": char_limit})
        self.proc.stdin.write(payload + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"web_extract bridge timed out after {self.timeout}s")
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                continue
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(
                    f"bridge exited; stderr={self._stderr_tail()!r} log={self.log[-5:]}"
                )
            if line.startswith("###RESULT###"):
                return json.loads(line[len("###RESULT###") :])
            self.log.append(line.rstrip())

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        finally:
            try:
                self._err.close()
            except Exception:
                pass


def _fresh_data_dir(parent: Path) -> Path:
    path = Path(tempfile.mkdtemp(dir=str(parent)))
    tools.store._data_dir = lambda: path
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slug(brand: str) -> str:
    text = brand.lower().replace("\u2019", "'")
    text = text.replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def pair_dir(brand: str, country: str, out_root: Path) -> Path:
    return out_root / f"{slug(brand)}-{country.lower()}"


def clean(value: Any) -> Any:
    """Recursively strip only U+200B/U+200C/U+200D/U+FEFF from strings."""
    if isinstance(value, str):
        return _ZERO_WIDTH.sub("", value)
    if isinstance(value, dict):
        return {clean(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(clean(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clean(text), encoding="utf-8")


def page_names(ads: list[dict]) -> list[str]:
    seen = []
    for ad in ads or []:
        name = str(ad.get("page_name") or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def ads_text(ads: list[dict]) -> str:
    keys = ("creative_text", "link_title", "cta_text", "page_name")
    return "\n".join(
        str(ad.get(key) or "") for ad in (ads or []) for key in keys
    )


def check_summary(row: dict, artifact_paths: dict | None = None) -> dict:
    out = {
        key: row.get(key)
        for key in (
            "query",
            "country",
            "advertiser",
            "resolved",
            "new_ads",
            "ended_ads",
            "changed_ads",
            "partial",
            "error",
            "skipped",
            "reason",
            "target",
            "candidates",
            "threshold",
        )
        if key in row
    }
    out["artifacts"] = artifact_paths if artifact_paths is not None else row.get("artifacts")
    out["new_page_names"] = page_names(row.get("new") or [])
    return out


def _artifact_mismatches(row: dict, digest: dict) -> list[str]:
    """Reasons a copied digest does not describe ``row``'s check."""
    problems: list[str] = []
    for key, field in (
        ("new", "new_ads"),
        ("ended", "ended_ads"),
        ("changed", "changed_ads"),
    ):
        want = row.get(field)
        if want is None:
            # A digest we cannot tie to this check's counts verifies nothing;
            # fail closed rather than silently downgrade provenance.
            problems.append(f"digest_{key}_unverified: row has no {field} count")
            continue
        got = digest.get(key)
        if got != want:
            problems.append(f"digest_{key}_mismatch: expected {want} got {got}")
    for key in ("query", "country", "advertiser"):
        want = str(row.get(key) or "").strip()
        got = str(digest.get(key) or "").strip()
        if want and got and want != got:
            problems.append(f"digest_{key}_mismatch: expected {want!r} got {got!r}")
    return problems


def _artifact_failure(label: str, problems: list[str]) -> str:
    """Name the artifact failure truthfully: error, missing, or wrong content."""
    if not problems:
        return f"{label}_missing: html/digest"
    heads = [p.split(":", 1)[0].strip() for p in problems]
    if all(head == "artifacts_error" for head in heads):
        category = "error"
    elif all(head == "artifacts_error" or head.endswith("_missing") for head in heads):
        category = "missing"
    else:
        category = "invalid"
    if category == "error":
        # The problems already carry the prefix; do not repeat it.
        details = [p[len("artifacts_error: "):] if p.startswith("artifacts_error: ") else p for p in problems]
        return f"{label}_error: {'; '.join(details)}"
    return f"{label}_{category}: {'; '.join(problems)}"


def _html_banner(row: dict) -> str | None:
    """The counts banner report.build_html renders, or None if incomplete."""
    parts = [row.get(key) for key in ("new_ads", "ended_ads", "changed_ads")]
    if any(part is None for part in parts):
        return None
    return f"{parts[0]} new / {parts[1]} ended / {parts[2]} changed"


def copy_artifacts(
    row: dict, target_dir: Path, *, subdir: str = "artifacts"
) -> tuple[dict, bool, list[str]]:
    """Copy one check's artifacts into the pair folder and verify their content.

    ad_check writes the HTML and digest under a path keyed only by the watch
    (query/country/advertiser), so a later check for the same watch overwrites
    them. Callers must copy each check right after it runs; ``subdir`` keeps
    the copies of two checks apart. Existence is not enough: the copied digest
    must still carry this check's counts and identity, and the HTML its counts
    banner, or the copy is reported as failed.

    Returns (relative paths for result.json, whether both files exist and
    verify, list of problems).
    """
    raw = row.get("artifacts") or {}
    if not isinstance(raw, dict) or raw.get("error"):
        error = raw.get("error", "no artifacts") if isinstance(raw, dict) else None
        error = error or "no artifacts"
        return {"error": error}, False, [f"artifacts_error: {error}"]
    outdir = target_dir / subdir
    outdir.mkdir(parents=True, exist_ok=True)
    rel: dict[str, str] = {}
    copied: dict[str, Path] = {}
    problems: list[str] = []
    for key in ("html", "digest"):
        src = Path(str(raw.get(key) or ""))
        dst = outdir / f"{key}{src.suffix or ('.html' if key == 'html' else '.json')}"
        if not src.is_file():
            rel[key] = f"missing:{src}"
            problems.append(f"{key}_missing: {src}")
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            rel[key] = f"unreadable:{src}"
            problems.append(f"{key}_unreadable: {src} ({exc.__class__.__name__})")
            continue
        write_text(dst, text)
        rel[key] = str(dst.relative_to(target_dir))
        copied[key] = dst

    if "digest" in copied:
        try:
            digest = json.loads(copied["digest"].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            digest = None
        if not isinstance(digest, dict):
            problems.append("digest_unreadable")
        else:
            problems.extend(_artifact_mismatches(row, digest))

    if "html" in copied:
        banner = _html_banner(row)
        if banner:
            try:
                html = copied["html"].read_text(encoding="utf-8", errors="replace")
            except OSError:
                html = ""
            if banner not in html:
                problems.append(f"html_banner_mismatch: expected {banner!r}")

    return rel, not problems, problems


def counts(row: dict) -> tuple:
    return (row.get("new_ads"), row.get("ended_ads"), row.get("changed_ads"))


# ---------------------------------------------------------------------------
# One pair
# ---------------------------------------------------------------------------


def run_pair(
    brand: str,
    advertiser: str,
    country: str,
    bridge: _LiveBridge,
    work_parent: Path,
    out_root: Path,
) -> dict:
    target_dir = pair_dir(brand, country, out_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    data_dir = _fresh_data_dir(work_parent)
    phase = {"name": "setup"}
    dispatches: list[dict] = []
    failures: list[str] = []
    row: dict = {
        "brand": brand,
        "country": country,
        "advertiser": advertiser,
        "folder": str(target_dir.relative_to(ROOT)),
        "data_dir": str(data_dir),
    }

    def dispatch(name: str, args: dict) -> Any:
        urls = args.get("urls") or []
        payload: Any = {}
        for attempt in range(2):
            started = time.perf_counter()
            try:
                payload = bridge.fetch(urls, char_limit=args.get("char_limit"))
            except Exception as exc:  # noqa: BLE001 - recorded, then surfaced
                dispatches.append(
                    {
                        "phase": phase["name"],
                        "url": urls[0] if urls else None,
                        "seconds": round(time.perf_counter() - started, 2),
                        "chars": 0,
                        "failed": True,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                payload = {"error": f"{type(exc).__name__}: {exc}"}
                break
            first = (payload.get("results") or [{}])[0] if isinstance(payload, dict) else {}
            chars = len(first.get("content") or "") if isinstance(first, dict) else 0
            failed = bool(
                not isinstance(payload, dict)
                or payload.get("error")
                or (isinstance(first, dict) and first.get("error"))
                or chars == 0
            )
            dispatches.append(
                {
                    "phase": phase["name"],
                    "url": urls[0] if urls else None,
                    "seconds": round(time.perf_counter() - started, 2),
                    "chars": chars,
                    "failed": failed,
                }
            )
            if not failed:
                break
            time.sleep(2)
        return payload

    tools.set_ctx(type("LiveCtx", (), {"dispatch_tool": staticmethod(dispatch)})())

    try:
        # 1. Keyword search — currently active in this market.
        phase["name"] = "search"
        started = time.perf_counter()
        search = json.loads(
            tools.ad_search(
                {
                    "query": brand,
                    "country": country,
                    "limit": SEARCH_LIMIT,
                    "active_status": "active",
                }
            )
        )
        search_seconds = round(time.perf_counter() - started, 2)
        search_ads = search.get("ads") or []
        row["search_summary"] = {
            "count": search.get("count"),
            "complete": search.get("complete"),
            "fetched": search.get("fetched"),
            "country": search.get("country"),
            "error": search.get("error"),
            "page_names": page_names(search_ads),
            "seconds": search_seconds,
        }

        # 2. Same query filtered to the brand's page name. A miss is truthful
        #    only when it says name_not_matched.
        phase["name"] = "advertiser_search"
        started = time.perf_counter()
        adv = json.loads(
            tools.ad_search(
                {
                    "query": brand,
                    "country": country,
                    "limit": SEARCH_LIMIT,
                    "active_status": "active",
                    "advertiser": advertiser,
                }
            )
        )
        adv_seconds = round(time.perf_counter() - started, 2)
        adv_ads = adv.get("ads") or []
        row["advertiser_summary"] = {
            "count": adv.get("count"),
            "complete": adv.get("complete"),
            "resolved": adv.get("resolved"),
            "error": adv.get("error"),
            "target": adv.get("target"),
            "candidates": adv.get("candidates"),
            "threshold": adv.get("threshold"),
            "page_names": page_names(adv_ads),
            "seconds": adv_seconds,
        }

        # 3. Watch the advertiser, then baseline + settle checks.
        phase["name"] = "watch_add"
        watch = json.loads(
            tools.ad_watch(
                {
                    "action": "add",
                    "query": brand,
                    "country": country,
                    "advertiser": advertiser,
                    "active_status": "active",
                }
            )
        )
        row["watch_add"] = {
            "error": watch.get("error"),
            "watchlist": watch.get("watchlist"),
        }

        phase["name"] = "check1"
        started = time.perf_counter()
        first_raw = json.loads(tools.ad_check({}))
        c1 = (first_raw.get("results") or [{}])[0]
        c1_seconds = round(time.perf_counter() - started, 2)
        # Copy now: check2 rewrites the same store-keyed report paths, so a
        # copy taken after both checks records check2's files as check1's.
        art_rel, artifacts_ok, art_problems = copy_artifacts(c1, target_dir)
        row["check1"] = check_summary(c1, art_rel)
        row["check1"]["seconds"] = c1_seconds
        if art_problems:
            row["check1"]["artifact_problems"] = art_problems

        phase["name"] = "check2"
        started = time.perf_counter()
        second_raw = json.loads(tools.ad_check({}))
        c2 = (second_raw.get("results") or [{}])[0]
        c2_seconds = round(time.perf_counter() - started, 2)

        art2_rel, artifacts2_ok, art2_problems = copy_artifacts(
            c2, target_dir, subdir="artifacts/check2"
        )
        row["check2"] = check_summary(c2, art2_rel)
        row["check2"]["seconds"] = c2_seconds
        if art2_problems:
            row["check2"]["artifact_problems"] = art2_problems
        row["artifacts_ok"] = artifacts_ok
        row["artifacts2_ok"] = artifacts2_ok

        # 4. Assertions (Task 4).
        count = search.get("count")
        if search.get("error"):
            failures.append(f"search_error: {search['error']}")
        elif count is None:
            failures.append("search_missing_count")
        elif count == 0:
            failures.append("silent_zero: count=0 with no error")
        elif count < 0:
            failures.append(f"search_bad_count: {count}")

        adv_error = adv.get("error")
        if adv_error == "name_not_matched":
            pass  # truthful miss
        elif adv_error:
            failures.append(f"advertiser_error: {adv_error}")
        elif (adv.get("count") or 0) == 0:
            failures.append("advertiser_silent_zero: count=0 with no error")
        elif not adv.get("resolved"):
            failures.append("advertiser_unresolved: count>0 without resolved")

        c1_counts, c2_counts = counts(c1), counts(c2)
        if c1.get("error"):
            failures.append(f"check1_error: {c1['error']}")
        elif (c1.get("new_ads") or 0) <= 0:
            failures.append(f"check1_no_new_ads: {c1_counts}")
        if c2.get("error"):
            failures.append(f"check2_error: {c2['error']}")
        elif c2_counts != (0, 0, 0):
            failures.append(f"check2_not_settled: {c2_counts}")
        if not artifacts_ok:
            failures.append(_artifact_failure("artifacts", art_problems))
        if not artifacts2_ok:
            failures.append(_artifact_failure("artifacts2", art2_problems))

        # 5. Currency spot-check. AE is the market proof; EG is recorded only.
        currency = {"expected": None, "found": [], "ok": None}
        if country == "AE":
            currency["expected"] = "AED"
            text = ads_text(search_ads) + "\n" + ads_text(adv_ads)
            if "AED" in text:
                currency["found"] = ["AED"]
                currency["ok"] = True
            else:
                currency["ok"] = False
                if count:
                    failures.append("currency_missing: AED absent from AE ad text")
        elif country == "EG":
            currency["expected"] = "EGP/جنيه"
            text = ads_text(search_ads) + "\n" + ads_text(adv_ads)
            currency["found"] = [m for m in ("EGP", "جنيه") if m in text]
            currency["ok"] = bool(currency["found"])  # record only
        row["currency"] = currency
        row["status"] = "PASS" if not failures else "FAIL"
        row["failures"] = failures
        row["timings"] = {
            "search": search_seconds,
            "advertiser_search": adv_seconds,
            "check1": c1_seconds,
            "check2": c2_seconds,
            "total": round(
                search_seconds + adv_seconds + c1_seconds + c2_seconds, 2
            ),
        }
        row["attempts"] = {
            "total": len(dispatches),
            "failed": sum(1 for d in dispatches if d["failed"]),
        }

        write_json(target_dir / "result.json", row)
        write_json(
            target_dir / "ads.json",
            {
                "brand": brand,
                "country": country,
                "search": search_ads[:SEARCH_LIMIT],
                "advertiser_search": adv_ads[:SEARCH_LIMIT],
            },
        )
        write_json(target_dir / "attempts.json", {"brand": brand, "country": country, "attempts": dispatches})
        write_pair_summary(target_dir, row)

    except Exception as exc:  # noqa: BLE001 - one pair must not kill the sweep
        row["status"] = "FAIL"
        row["failures"] = [
            *(row.get("failures") or []),
            f"exception: {type(exc).__name__}: {exc}",
        ]
        row["traceback"] = traceback.format_exc(limit=6)
        row["attempts"] = {
            "total": len(dispatches),
            "failed": sum(1 for d in dispatches if d["failed"]),
        }
        write_json(target_dir / "result.json", row)
        write_json(
            target_dir / "attempts.json",
            {"brand": brand, "country": country, "attempts": dispatches},
        )
        write_pair_summary(target_dir, row)
    finally:
        tools.set_ctx(None)

    return row


def write_pair_summary(target_dir: Path, row: dict) -> None:
    s = row.get("search_summary") or {}
    a = row.get("advertiser_summary") or {}
    c1 = row.get("check1") or {}
    c2 = row.get("check2") or {}
    cur = row.get("currency") or {}
    attempts = row.get("attempts") or {}
    lines = [
        f"# {row.get('brand')} × {row.get('country')} — {row.get('status', 'UNKNOWN')}",
        "",
        f"- folder: `{row.get('folder', '')}`",
        f"- advertiser filter: `{row.get('advertiser')}`",
        "",
        "## Keyword search (`active_status=active`, limit 20)",
        f"- count: {s.get('count')}  complete: {s.get('complete')}  fetched: {s.get('fetched')}  error: {s.get('error')}",
        f"- page names: {', '.join(s.get('page_names') or []) or '—'}",
        f"- seconds: {s.get('seconds')}",
        "",
        "## Advertiser search",
        f"- count: {a.get('count')}  resolved: {a.get('resolved')}  error: {a.get('error')}",
        f"- page names: {', '.join(a.get('page_names') or []) or '—'}",
        f"- seconds: {a.get('seconds')}",
        "",
        "## Watch checks",
        f"- check1: new={c1.get('new_ads')} ended={c1.get('ended_ads')} changed={c1.get('changed_ads')}"
        f" partial={c1.get('partial')} error={c1.get('error')} seconds={c1.get('seconds')}",
        f"- check2: new={c2.get('new_ads')} ended={c2.get('ended_ads')} changed={c2.get('changed_ads')}"
        f" partial={c2.get('partial')} error={c2.get('error')} seconds={c2.get('seconds')}",
        f"- artifacts: {json.dumps(c1.get('artifacts'), ensure_ascii=False)} (ok={row.get('artifacts_ok')})",
        f"- artifacts check2: {json.dumps(c2.get('artifacts'), ensure_ascii=False)} (ok={row.get('artifacts2_ok')})",
        "",
        "## Currency spot-check",
        f"- expected: {cur.get('expected') or '—'}  found: {', '.join(cur.get('found') or []) or 'none'}  ok: {cur.get('ok')}",
        "",
        "## Hydration",
        f"- attempts: {attempts.get('total')}  failed: {attempts.get('failed')}",
        "",
        "## Failures",
    ]
    lines.extend(f"- {f}" for f in (row.get("failures") or ["none"]))
    lines.append("")
    write_text(target_dir / "summary.md", "\n".join(lines))


# ---------------------------------------------------------------------------
# Aggregate + entry point
# ---------------------------------------------------------------------------


def aggregate(out_root: Path) -> None:
    rows = []
    for path in sorted(out_root.glob("*/result.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    order_brand = {brand: i for i, (brand, _) in enumerate(BRANDS)}
    order_cc = {cc: i for i, cc in enumerate(COUNTRIES)}
    rows.sort(key=lambda r: (order_brand.get(r.get("brand"), 99), order_cc.get(r.get("country"), 99)))
    passed = sum(1 for r in rows if r.get("status") == "PASS")
    lines = [
        "# QSR live eval — aggregate",
        "",
        f"- pairs: {len(rows)}  pass: {passed}  fail: {len(rows) - passed}",
        "",
        "| Brand | CC | search count | advertiser | check1 (n/e/c) | check2 (n/e/c) | currency | status | reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = r.get("search_summary") or {}
        a = r.get("advertiser_summary") or {}
        c1 = r.get("check1") or {}
        c2 = r.get("check2") or {}
        if a.get("error") == "name_not_matched":
            adv_out = "name_not_matched"
        elif a.get("resolved"):
            adv_out = f"resolved: {a['resolved'].get('page_name')} ({a['resolved'].get('score')})"
        else:
            adv_out = a.get("error") or f"{a.get('count')}"
        cur = r.get("currency") or {}
        cur_out = ",".join(cur.get("found") or []) or ("absent" if cur.get("expected") else "—")
        reason = "; ".join(r.get("failures") or []) or "—"
        lines.append(
            f"| {r.get('brand')} | {r.get('country')} | {s.get('count')} | {adv_out} | "
            f"{c1.get('new_ads')}/{c1.get('ended_ads')}/{c1.get('changed_ads')} | "
            f"{c2.get('new_ads')}/{c2.get('ended_ads')}/{c2.get('changed_ads')} | "
            f"{cur_out} | {r.get('status')} | {reason} |"
        )
    totals = [r.get("attempts") or {} for r in rows]
    total_attempts = sum(t.get("total") or 0 for t in totals)
    failed_attempts = sum(t.get("failed") or 0 for t in totals)
    lines += [
        "",
        f"- web_extract attempts: {total_attempts}  failed: {failed_attempts}"
        + (f" ({100 * failed_attempts / total_attempts:.0f}%)" if total_attempts else ""),
        "",
    ]
    write_text(out_root / "summary.md", "\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="run only KFC/AE")
    parser.add_argument("--brand", action="append", default=None, help="brand name to include")
    parser.add_argument("--country", action="append", default=None, help="country code to include")
    parser.add_argument("--out", default=str(OUT_ROOT), help="artifact root")
    args = parser.parse_args(argv)

    if _runtime_argv() is None:
        print("BLOCKED: missing Hermes runtime (`hermes` CLI and ~/.hermes/tools)")
        return 2

    if args.smoke:
        pairs = [("KFC", "AE")]
    else:
        pairs = [(brand, cc) for brand, _ in BRANDS for cc in COUNTRIES]
    if args.brand:
        wanted = {b.lower() for b in args.brand}
        pairs = [p for p in pairs if p[0].lower() in wanted]
    if args.country:
        wanted = {c.upper() for c in args.country}
        pairs = [p for p in pairs if p[1] in wanted]
    if not pairs:
        print("no pairs selected")
        return 1

    advertisers = dict(BRANDS)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    work_parent = Path(tempfile.mkdtemp(prefix="ads-intel-live-eval-"))
    print(f"repo:  {ROOT}")
    print(f"pairs: {len(pairs)}  out: {out_root}  work: {work_parent}")

    try:
        bridge = _LiveBridge()
    except Exception as exc:  # noqa: BLE001
        print(f"BLOCKED: bridge start failed: {type(exc).__name__}: {exc}")
        return 2

    rows = []
    try:
        for i, (brand, cc) in enumerate(pairs, 1):
            started = time.perf_counter()
            row = run_pair(brand, advertisers[brand], cc, bridge, work_parent, out_root)
            rows.append(row)
            took = round(time.perf_counter() - started, 1)
            print(
                f"[{i}/{len(pairs)}] {brand} {cc}: {row.get('status')} "
                f"search={((row.get('search_summary') or {}).get('count'))} "
                f"check1={counts(row.get('check1') or {})} "
                f"attempts={(row.get('attempts') or {}).get('total')} ({took}s)"
            )
            if row.get("failures"):
                print("    " + "; ".join(row["failures"]))
    finally:
        bridge.close()
        tools.set_ctx(None)
        aggregate(out_root)

    passed = sum(1 for r in rows if r.get("status") == "PASS")
    print(f"done: {passed}/{len(rows)} PASS  -> {out_root / 'summary.md'}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
