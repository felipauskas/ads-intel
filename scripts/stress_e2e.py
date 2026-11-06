#!/usr/bin/env python3
"""End-to-end stress harness for ads-intel (stdlib only).

Offline mode (default, no network)
----------------------------------
Runs N iterations of the full tool path against the recorded library render:

    parse fixture -> ad_search -> ad_watch add -> ad_check (baseline)
    -> ad_check (settle: expect 0/0/0) -> tamper one creative
    -> ad_check (expect changed == 1) -> verify artifacts + digest counts

Every iteration gets its own data directory and its own watch query, so a
failure is isolated and reproducible (`iter-NNN` is printed with it).

Also exercises:
  * concurrency/atomicity — threads hammering watch_add/watch_list/
    save_snapshot/load_snapshot on one data dir; every JSON file is re-parsed
    afterwards.
  * corruption resilience — garbage in the watchlist and in a snapshot must
    not crash the tools (contract: ``[]`` / ``{"ads": {}}``).

Live mode (``--live``)
----------------------
Drives the real host ``web_extract`` through a bridge process that runs in the
Hermes install's own interpreter/dependency environment. If the bridge cannot
be started or every fetch fails, the live section is reported BLOCKED with the
captured evidence; it never fabricates results.

Usage:
    .venv/bin/python scripts/stress_e2e.py                 # 50 offline iters
    .venv/bin/python scripts/stress_e2e.py -n 200          # more iterations
    .venv/bin/python scripts/stress_e2e.py --live          # real fetches, once
"""

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sources  # noqa: E402
import tools  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "library_page.md"

# ad_check does not pass a limit, so it inherits fetch_ads_with_meta's default.
AD_CHECK_LIMIT = 20

LIVE_QUERIES = (("KFC", "US"), ("KFC", "AE"), ("BMW", "US"), ("Nike", "US"))

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
    """The command that runs code inside the live Hermes runtime.

    ``hermes --print-runtime-command`` reports the exact interpreter and
    bootstrap the agent itself uses; that is the only environment where the
    configured extract backend (and its dependencies) is available.
    """
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



class _StubCtx:
    """Minimal host context: answers web_extract with the recorded render."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[str, dict]] = []

    def dispatch_tool(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        url = (args.get("urls") or [""])[0]
        return {"results": [{"url": url, "content": self.content, "error": None}]}


class _LiveBridge:
    """Subprocess bridge to the real host web_extract tool.

    Runs in the Hermes install's interpreter so the configured extract backend
    and its dependencies are available. Requests/responses are one JSON line
    each; the driver tolerates log lines printed before the result marker.
    """

    def __init__(self, timeout: float = 180.0) -> None:
        self.timeout = timeout
        self.argv = _runtime_argv()
        if not self.argv:
            raise RuntimeError(
                "could not resolve the Hermes runtime command "
                "(`hermes --print-runtime-command` and ~/.hermes/tools both failed)"
            )
        code = (_RUNTIME_PRELUDE % {"root": str(HERMES_HOME)}) + _BRIDGE_CODE
        # stderr goes to a file: the provider logs there, and leaving a pipe
        # undrained would deadlock a chatty run.
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


def _check(failures: list[str], condition: bool, message: str) -> bool:
    if not condition:
        failures.append(message)
    return bool(condition)


def _fresh_data_dir(parent: Path) -> Path:
    path = Path(tempfile.mkdtemp(dir=str(parent)))
    tools.store._data_dir = lambda: path
    return path


# ---------------------------------------------------------------------------
# Offline: one full end-to-end iteration
# ---------------------------------------------------------------------------


def run_iteration(index: int, markdown: str, base_dir: Path) -> dict:
    failures: list[str] = []
    started = time.perf_counter()
    query = f"nike-stress-{index}"
    data_dir = _fresh_data_dir(base_dir)

    ctx = _StubCtx(markdown)
    tools.set_ctx(ctx)
    row_counts: dict[str, Any] = {"baseline": None, "settle": None, "changed": None}
    try:
        # 1. Parse the fixture (parser runs for real, every iteration).
        expected = sources.parse_library_markdown(markdown)
        _check(failures, bool(expected), "fixture parsed to no ads")
        ids = [ad["id"] for ad in expected]
        _check(failures, len(set(ids)) == len(ids), "fixture has duplicate ids")
        delivered = min(len(expected), AD_CHECK_LIMIT)

        # 2. ad_search through the real URL builder + parser.
        search = json.loads(tools.ad_search({"query": query, "country": "US"}))
        _check(failures, "error" not in search, f"ad_search error: {search.get('error')}")
        _check(
            failures,
            search.get("count") == delivered,
            f"ad_search count {search.get('count')} != {delivered}",
        )
        _check(
            failures,
            bool(ctx.calls) and ctx.calls[-1][0] == "web_extract",
            "ad_search did not dispatch web_extract",
        )
        if ctx.calls:
            url = ctx.calls[-1][1]["urls"][0]
            _check(
                failures,
                f"country=US" in url and f"q={query}" in url,
                f"ad_search URL wrong: {url}",
            )

        # 3. Watch the unique query.
        watch = json.loads(tools.ad_watch({"action": "add", "query": query}))
        _check(
            failures,
            watch.get("watchlist") == [{"query": query, "country": "US"}],
            f"watchlist after add: {watch.get('watchlist')}",
        )

        # 4. Baseline check: every delivered ad is new, nothing ended/changed.
        first = json.loads(tools.ad_check({}))
        _check(failures, len(first["results"]) == 1, f"ad_check rows: {len(first['results'])}")
        baseline = first["results"][0]
        row_counts["baseline"] = [
            baseline.get("new_ads"),
            baseline.get("ended_ads"),
            baseline.get("changed_ads"),
        ]
        _check(failures, baseline.get("new_ads") == delivered, "baseline new_ads wrong")
        _check(failures, baseline.get("ended_ads") == 0, "baseline ended_ads != 0")
        _check(failures, baseline.get("changed_ads") == 0, "baseline changed_ads != 0")
        _check(failures, baseline.get("partial") is True, "baseline should be partial (28>20)")
        snap = tools.store.load_snapshot(query)
        _check(failures, len(snap.get("ads") or {}) == delivered, "snapshot size after baseline")

        # 5. Settle: identical render -> 0/0/0.
        second = json.loads(tools.ad_check({}))["results"][0]
        row_counts["settle"] = [
            second.get("new_ads"),
            second.get("ended_ads"),
            second.get("changed_ads"),
        ]
        _check(
            failures,
            (second.get("new_ads"), second.get("ended_ads"), second.get("changed_ads"))
            == (0, 0, 0),
            f"did not settle: {row_counts['settle']}",
        )

        # 6. Tamper with exactly one creative, then re-check.
        target = expected[0]["id"]
        snap = tools.store.load_snapshot(query)
        _check(failures, target in (snap.get("ads") or {}), f"tamper target {target} missing")
        snap["ads"][target]["creative_text"] = "tampered copy"
        tools.store.save_snapshot(query, snap, country="US")

        third = json.loads(tools.ad_check({}))["results"][0]
        row_counts["changed"] = [
            third.get("new_ads"),
            third.get("ended_ads"),
            third.get("changed_ads"),
        ]
        _check(
            failures,
            (third.get("new_ads"), third.get("ended_ads"), third.get("changed_ads"))
            == (0, 0, 1),
            f"tamper not detected alone: {row_counts['changed']}",
        )
        _check(
            failures,
            [ad["id"] for ad in third.get("changed") or []] == [target],
            "changed bucket has the wrong id",
        )

        # 7. Artifacts exist, are inside the isolated dir, and agree with the row.
        artifacts = third.get("artifacts") or {}
        _check(failures, set(artifacts) == {"html", "digest"}, f"artifact keys: {artifacts}")
        html_path = Path(artifacts.get("html") or "")
        digest_path = Path(artifacts.get("digest") or "")
        _check(failures, html_path.is_file(), f"html missing: {html_path}")
        _check(failures, digest_path.is_file(), f"digest missing: {digest_path}")
        if html_path.is_file():
            html = html_path.read_text()
            _check(
                failures,
                f'data-ad-id="{target}"' in html,
                "html lacks the changed card",
            )
            _check(
                failures,
                "0 new / 0 ended / 1 changed" in html,
                "html banner disagrees with diff",
            )
        if digest_path.is_file():
            digest = json.loads(digest_path.read_text())
            _check(failures, digest.get("query") == query, "digest query mismatch")
            _check(failures, digest.get("country") == "US", "digest country mismatch")
            _check(failures, digest.get("partial") is True, "digest partial flag")
            _check(
                failures,
                (digest.get("new"), digest.get("ended"), digest.get("changed")) == (0, 0, 1),
                f"digest counts {digest}",
            )
            _check(
                failures,
                digest.get("total") == len(tools.store.load_snapshot(query)["ads"]),
                "digest total != snapshot size",
            )
        _check(
            failures,
            str(html_path).startswith(str(data_dir)),
            "artifact escaped the isolated data dir",
        )
    except BaseException as exc:  # noqa: BLE001 - recorded, never hidden
        failures.append(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        tools.set_ctx(None)

    return {
        "index": index,
        "query": query,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "failures": failures,
        "counts": row_counts,
    }


# ---------------------------------------------------------------------------
# Concurrency / atomicity
# ---------------------------------------------------------------------------


def run_concurrency(base_dir: Path, threads: int = 10, rounds: int = 25) -> dict:
    data_dir = _fresh_data_dir(base_dir)
    errors: list[str] = []
    barrier = threading.Barrier(threads)
    started = time.perf_counter()

    def worker(n: int) -> None:
        try:
            barrier.wait()
            for r in range(rounds):
                tools.store.watch_add(f"brand-{n}", country="US")
                tools.store.watch_list()
                ad = {
                    "id": f"{n}-{r}",
                    "page_name": f"Brand {n}",
                    "status": "active",
                    "first_seen": "",
                    "last_seen": "",
                    "creative_text": f"copy {r}",
                    "library_url": f"https://www.facebook.com/ads/library/?id={n}-{r}",
                }
                tools.store.save_snapshot("shared", {"ads": {ad["id"]: ad}})
                tools.store.load_snapshot("shared")
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"thread {n}: {type(exc).__name__}: {exc}")

    workers = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join(timeout=120)

    alive = [t.name for t in workers if t.is_alive()]
    if alive:
        errors.append(f"threads still alive after join: {alive}")

    corrupt: list[str] = []
    parsed = 0
    for path in sorted(data_dir.rglob("*.json")):
        try:
            json.loads(path.read_text())
            parsed += 1
        except Exception as exc:  # noqa: BLE001
            corrupt.append(f"{path.name}: {type(exc).__name__}: {exc}")

    entries = tools.store.watch_list()
    snapshot = tools.store.load_snapshot("shared")
    return {
        "threads": threads,
        "rounds": rounds,
        "ops_per_thread": rounds * 4,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "exceptions": errors,
        "corrupt_files": corrupt,
        "json_files_parsed": parsed,
        "watch_entries": len(entries),
        "watch_entries_expected": threads,
        "watch_entries_lost": max(0, threads - len(entries)),
        "snapshot_ads": len(snapshot.get("ads") or {}),
    }


# ---------------------------------------------------------------------------
# Corruption resilience
# ---------------------------------------------------------------------------


def run_corruption(base_dir: Path) -> dict:
    data_dir = _fresh_data_dir(base_dir)
    checks: list[str] = []
    failures: list[str] = []

    # Garbage watchlist: list must degrade to [], add must recover.
    (data_dir / tools.store.WATCH).write_text("{not json at all,,,")
    watch_list = tools.store.watch_list()
    checks.append(f"watch_list={watch_list}")
    if watch_list != []:
        failures.append(f"corrupt watchlist not degraded: {watch_list!r}")

    listed = json.loads(tools.ad_watch({"action": "list"}))
    checks.append(f"ad_watch list={listed}")
    if listed.get("watchlist") != []:
        failures.append(f"ad_watch list not degraded: {listed!r}")

    check_rows = json.loads(tools.ad_check({}))["results"]
    checks.append(f"ad_check rows={len(check_rows)}")
    if check_rows != []:
        failures.append(f"ad_check on corrupt watchlist returned rows: {check_rows!r}")

    recovered = json.loads(tools.ad_watch({"action": "add", "query": "recover"}))["watchlist"]
    checks.append(f"watch_add recovers={recovered}")
    if recovered != [{"query": "recover", "country": "US"}]:
        failures.append(f"watch_add did not recover: {recovered!r}")

    # Garbage snapshot at the exact path load_snapshot would read.
    snap_path = tools.store._snapshot_path("nike")
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_bytes(b"\xff\xfe garbage not json")
    loaded = tools.store.load_snapshot("nike")
    checks.append(f"load_snapshot={loaded}")
    if loaded != {"ads": {}}:
        failures.append(f"garbage snapshot not degraded: {loaded!r}")

    # A non-object snapshot (valid JSON, wrong shape) must also degrade.
    snap_path.write_text(json.dumps(["not", "a", "dict"]))
    loaded_list = tools.store.load_snapshot("nike")
    checks.append(f"load_snapshot list={loaded_list}")
    if loaded_list != {"ads": {}}:
        failures.append(f"list snapshot not degraded: {loaded_list!r}")

    return {"checks": checks, "failures": failures}



# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


def run_live(base_dir: Path) -> dict:
    rows: list[dict] = []
    result: dict = {"status": "PASS", "rows": rows, "evidence": []}

    if _runtime_argv() is None:
        result["status"] = "BLOCKED"
        result["evidence"].append("missing Hermes runtime (`hermes` CLI and ~/.hermes/tools)")
        return result

    try:
        bridge = _LiveBridge()
    except Exception as exc:  # noqa: BLE001
        result["status"] = "BLOCKED"
        result["evidence"].append(f"bridge start failed: {type(exc).__name__}: {exc}")
        return result

    tools.set_ctx(_StubCtx(""))  # placeholder, replaced below
    try:
        for query, country in LIVE_QUERIES:
            data_dir = _fresh_data_dir(base_dir)
            row: dict = {"query": query, "country": country, "data_dir": str(data_dir)}

            def dispatch(name: str, args: dict, _row=row) -> Any:
                urls = args.get("urls") or []
                attempts = []
                payload: Any = {}
                # One retry for transient host failures (the keyless rescue
                # path in this environment is rate-limited). Every attempt is
                # recorded; a retry never hides the first failure.
                for attempt in range(2):
                    started = time.perf_counter()
                    payload = bridge.fetch(urls, char_limit=args.get("char_limit"))
                    first = (payload.get("results") or [{}])[0] if isinstance(payload, dict) else {}
                    chars = len((first.get("content") or "")) if isinstance(first, dict) else 0
                    failed = bool(
                        not isinstance(payload, dict)
                        or payload.get("error")
                        or (isinstance(first, dict) and first.get("error"))
                        or chars == 0
                    )
                    attempts.append(
                        {
                            "url": urls[0] if urls else None,
                            "seconds": round(time.perf_counter() - started, 2),
                            "chars": chars,
                            "failed": failed,
                        }
                    )
                    if not failed:
                        break
                    time.sleep(2)
                _row.setdefault("dispatches", []).extend(attempts)
                return payload

            tools.set_ctx(type("LiveCtx", (), {"dispatch_tool": staticmethod(dispatch)})())

            started = time.perf_counter()
            search = json.loads(tools.ad_search({"query": query, "country": country, "limit": 10}))
            row["search_seconds"] = round(time.perf_counter() - started, 2)
            row["count"] = search.get("count")
            row["search_error"] = search.get("error")
            if search.get("error"):
                row["status"] = "FAIL"
                rows.append(row)
                continue

            tools.ad_watch({"action": "add", "query": query, "country": country})
            started = time.perf_counter()
            first = json.loads(tools.ad_check({}))
            row["check1_seconds"] = round(time.perf_counter() - started, 2)
            row["check1"] = (first["results"] or [{}])[0]
            started = time.perf_counter()
            second = json.loads(tools.ad_check({}))
            row["check2_seconds"] = round(time.perf_counter() - started, 2)
            row["check2"] = (second["results"] or [{}])[0]

            c1, c2 = row["check1"], row["check2"]
            counts1 = (c1.get("new_ads"), c1.get("ended_ads"), c1.get("changed_ads"))
            counts2 = (c2.get("new_ads"), c2.get("ended_ads"), c2.get("changed_ads"))
            row["counts1"] = counts1
            row["counts2"] = counts2
            row["partial1"] = c1.get("partial")
            row["artifacts_ok"] = bool(
                c1.get("artifacts")
                and Path(c1["artifacts"].get("html", "")).is_file()
                and Path(c1["artifacts"].get("digest", "")).is_file()
            )
            ok = (
                c1.get("new_ads", 0) > 0
                and counts2 == (0, 0, 0)
                and row["artifacts_ok"]
                and not c1.get("error")
                and not c2.get("error")
            )
            row["status"] = "PASS" if ok else "FAIL"
            rows.append(row)
    finally:
        tools.set_ctx(None)
        bridge.close()

    if not rows or all(r["status"] == "FAIL" for r in rows):
        result["status"] = "BLOCKED"
        result["evidence"].append(
            "every live query failed; see per-row search_error / bridge log"
        )
        result["evidence"].extend(bridge.log[-10:])
    elif any(r["status"] != "PASS" for r in rows):
        result["status"] = "PARTIAL"
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--iterations", type=int, default=50)
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--live", action="store_true", help="real web_extract run")
    parser.add_argument("--seed", type=int, default=None, help="accepted for repeatability")
    args = parser.parse_args(argv)

    base_dir = Path(tempfile.mkdtemp(prefix="ads-intel-stress-"))
    print(f"workdir: {base_dir}")
    print(f"repo:    {ROOT}")
    print(f"python:  {sys.version.split()[0]} ({sys.executable})")

    failed = 0
    if args.live:
        print("\n== live ==")
        live = run_live(base_dir)
        for row in live["rows"]:
            print(
                f"{row['query']}/{row['country']} {row['status']} "
                f"count={row.get('count')} search={row.get('search_seconds')}s "
                f"check1={row.get('check1_seconds')}s {row.get('counts1')} "
                f"check2={row.get('check2_seconds')}s {row.get('counts2')} "
                f"partial={row.get('partial1')} artifacts={row.get('artifacts_ok')}"
            )
            for d in row.get("dispatches") or []:
                flag = " (failed)" if d.get("failed") else ""
                print(f"  fetch {d['seconds']}s chars={d['chars']}{flag}")
            if row.get("search_error"):
                print(f"  error: {row['search_error']}")
        for line in live["evidence"]:
            print(f"  evidence: {line}")
        print(f"live status: {live['status']}")
        if live["status"] != "PASS":
            failed += 1
    else:
        print(f"\n== offline iterations: {args.iterations} ==")
        markdown = FIXTURE.read_text()
        results = []
        for i in range(1, args.iterations + 1):
            result = run_iteration(i, markdown, base_dir)
            results.append(result)
            if result["failures"]:
                failed += 1
                print(
                    f"iter {i:03d} FAIL {result['elapsed_ms']:7.1f}ms "
                    f"{result['counts']} :: {'; '.join(result['failures'])}"
                )
            else:
                print(
                    f"iter {i:03d} PASS {result['elapsed_ms']:7.1f}ms "
                    f"baseline={result['counts']['baseline'][0]} "
                    f"settle={'/'.join(str(x) for x in result['counts']['settle'])} "
                    f"changed={result['counts']['changed'][2]}"
                )
        times = [r["elapsed_ms"] for r in results]
        print(
            f"\noffline summary: iterations={len(results)} "
            f"failures={failed} max_ms={max(times) if times else 0:.1f} "
            f"total_s={sum(times) / 1000:.2f}"
        )

    print("\n== concurrency ==")
    conc = run_concurrency(base_dir, threads=args.threads)
    print(
        f"threads={conc['threads']} ops/thread={conc['ops_per_thread']} "
        f"elapsed={conc['elapsed_ms']}ms json_files={conc['json_files_parsed']} "
        f"corrupt={len(conc['corrupt_files'])} exceptions={len(conc['exceptions'])}"
    )
    print(
        f"watch entries: expected={conc['watch_entries_expected']} "
        f"got={conc['watch_entries']} lost={conc['watch_entries_lost']} "
        f"snapshot_ads={conc['snapshot_ads']}"
    )
    for line in conc["exceptions"]:
        print(f"  exception: {line}")
    for line in conc["corrupt_files"]:
        print(f"  corrupt: {line}")
    if conc["exceptions"] or conc["corrupt_files"]:
        failed += 1

    print("\n== corruption resilience ==")
    corr = run_corruption(base_dir)
    for line in corr["checks"]:
        print(f"  {line}")
    if corr["failures"]:
        failed += 1
        for line in corr["failures"]:
            print(f"  FAIL: {line}")
    else:
        print("corruption: PASS (degraded as contracted, no crash)")

    print(f"\nRESULT: {'PASS' if failed == 0 else 'FAIL'} ({failed} failing section(s))")
    if not args.live:
        shutil.rmtree(base_dir, ignore_errors=True)
    else:
        print(f"(live artifacts kept under {base_dir})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
