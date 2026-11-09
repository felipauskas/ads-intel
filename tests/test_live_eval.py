"""Eval artifact integrity: each check keeps its own report/digest.

ad_check writes the HTML report and digest under a path keyed only by
query/country/advertiser, so a second check for the same watch rewrites the
first check's files. The eval must copy check1's artifacts before check2 runs,
and must verify the copied digest still describes check1.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVALS = ROOT / "evals"
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import report  # noqa: E402
import tools  # noqa: E402

import live_eval  # noqa: E402


def _ad(ad_id: str = "1") -> dict:
    return {
        "id": ad_id,
        "page_name": "KFC",
        "status": "active",
        "creative_text": "KFC AED 5",
    }


def _write_check(shared: Path, *, new: list[dict], checked_at: str) -> dict:
    """Write one check's report+digest at the shared store-keyed paths."""
    ad = _ad()
    return report.write_report(
        "KFC",
        {"new": new, "ended": [], "changed": []},
        {"1": ad},
        {"checked_at": checked_at},
        out_dir=shared,
        country="AE",
        advertiser="KFC",
    )


def test_copy_artifacts_flags_digest_overwritten_by_later_check(tmp_path):
    """A copy made after check2 must not pass off check2's files as check1's."""
    shared = tmp_path / "reports"
    first = _write_check(shared, new=[_ad()], checked_at="t1")
    second = _write_check(shared, new=[], checked_at="t2")
    assert first == second  # one path per watch: the collision under test

    row = {
        "query": "KFC",
        "country": "AE",
        "advertiser": "KFC",
        "new_ads": 1,
        "ended_ads": 0,
        "changed_ads": 0,
        "new": [_ad()],
        "artifacts": first,
    }
    rel, ok, problems = live_eval.copy_artifacts(row, tmp_path / "pair")

    assert rel["digest"] == "artifacts/digest.json"
    assert not ok, "overwritten digest must fail verification"
    assert "digest_new_mismatch: expected 1 got 0" in problems, problems
    # The html banner is check2's too; assert it separately, not just "mismatch".
    assert any(p.startswith("html_banner_mismatch:") for p in problems), problems
    # The bytes on disk are check2's: proof the check is looking at content,
    # not at file existence.
    assert json.loads((tmp_path / "pair" / rel["digest"]).read_text())["new"] == 0


def test_copy_artifacts_fails_when_row_has_no_counts(tmp_path):
    """Missing expected counts must fail verification, not silently pass."""
    shared = tmp_path / "reports"
    _write_check(shared, new=[_ad()], checked_at="t1")
    second = _write_check(shared, new=[], checked_at="t2")

    # A row whose result.json lost its counts cannot prove the digest is its own.
    row = {
        "query": "KFC",
        "country": "AE",
        "advertiser": "KFC",
        "artifacts": second,
    }
    _, ok, problems = live_eval.copy_artifacts(row, tmp_path / "pair")

    assert not ok, "unverifiable provenance must fail closed"
    assert "digest_new_unverified: row has no new_ads count" in problems, problems
    assert "digest_ended_unverified: row has no ended_ads count" in problems, problems
    assert "digest_changed_unverified: row has no changed_ads count" in problems, problems


def test_artifact_failure_calls_wrong_content_invalid_not_missing():
    """Files present but wrong must not be reported as missing."""
    line = live_eval._artifact_failure(
        "artifacts",
        [
            "digest_new_mismatch: expected 1 got 0",
            "html_banner_mismatch: expected '1 new / 0 ended / 0 changed'",
        ],
    )
    assert line.startswith("artifacts_invalid: "), line
    assert "artifacts_missing" not in line
    assert "digest_new_mismatch: expected 1 got 0" in line


def test_artifact_failure_keeps_missing_label_for_absent_files():
    line = live_eval._artifact_failure(
        "artifacts2", ["html_missing: /x/a.html", "digest_missing: /x/b.json"]
    )
    assert line.startswith("artifacts2_missing: "), line


def test_artifact_failure_does_not_repeat_artifacts_error_prefix():
    line = live_eval._artifact_failure("artifacts", ["artifacts_error: no artifacts"])
    assert line == "artifacts_error: no artifacts", line
    assert line.count("artifacts_error") == 1


def test_run_pair_preserves_check1_artifacts_when_check2_shares_paths(
    tmp_path, monkeypatch
):
    """run_pair copies check1 before check2 can rewrite the shared paths."""
    # No-op kept for clarity: tools.store already resolves paths under tmp_path
    # (live_eval.ROOT is patched below), so this re-set changes nothing.
    monkeypatch.setattr(tools.store, "_data_dir", tools.store._data_dir)
    shared = tmp_path / "reports"
    calls = {"n": 0}

    def fake_search(args):
        resolved = "advertiser" in args
        return json.dumps(
            {
                "ads": [_ad()],
                "count": 1,
                "complete": True,
                "fetched": 1,
                "country": "AE",
                **(
                    {
                        "resolved": {"page_name": "KFC", "score": 1.0},
                        "target": "KFC",
                        "candidates": [],
                        "threshold": 0.6,
                    }
                    if resolved
                    else {}
                ),
            }
        )

    def fake_watch(_args):
        return json.dumps({"watchlist": [{"query": "KFC", "country": "AE"}]})

    def fake_check(_args):
        calls["n"] += 1
        first = calls["n"] == 1
        artifacts = _write_check(
            shared, new=[_ad()] if first else [], checked_at=f"t{calls['n']}"
        )
        return json.dumps(
            {
                "results": [
                    {
                        "query": "KFC",
                        "country": "AE",
                        "advertiser": "KFC",
                        "partial": False,
                        "new_ads": 1 if first else 0,
                        "ended_ads": 0,
                        "changed_ads": 0,
                        "new": [_ad()] if first else [],
                        "ended": [],
                        "changed": [],
                        "artifacts": artifacts,
                    }
                ]
            }
        )

    monkeypatch.setattr(tools, "ad_search", fake_search)
    monkeypatch.setattr(tools, "ad_watch", fake_watch)
    monkeypatch.setattr(tools, "ad_check", fake_check)

    out_root = tmp_path / "out"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(live_eval, "ROOT", tmp_path)
    row = live_eval.run_pair("KFC", "KFC", "AE", object(), work, out_root)

    pair = out_root / "kfc-ae"
    c1_digest = json.loads((pair / row["check1"]["artifacts"]["digest"]).read_text())
    c2_digest = json.loads((pair / row["check2"]["artifacts"]["digest"]).read_text())

    assert calls["n"] == 2
    assert row["check1"]["new_ads"] == 1
    assert c1_digest["new"] == 1, "check1 digest must hold check1's counts"
    assert c1_digest["checked_at"] == "t1"
    assert c2_digest["new"] == 0
    assert c2_digest["checked_at"] == "t2"
    # Distinct per-check paths, and both verified against result.json counts.
    assert row["check1"]["artifacts"]["digest"] != row["check2"]["artifacts"]["digest"]
    assert row["artifacts_ok"] is True
    assert row["status"] == "PASS", row["failures"]


def test_run_pair_clears_stale_artifacts_when_check_fails(tmp_path, monkeypatch):
    """A failed rerun must not leave the previous run's digest behind.

    ``copy_artifacts`` writes nothing when the check has no artifacts, so
    without an explicit clear the pair folder keeps a digest.json from the
    earlier run while result.json reports no counts — evidence that contradicts
    itself.
    """
    pair = tmp_path / "out" / "kfc-ae"
    (pair / "artifacts" / "check2").mkdir(parents=True)
    (pair / "artifacts" / "digest.json").write_text('{"new": 9}', encoding="utf-8")
    (pair / "artifacts" / "check2" / "digest.json").write_text(
        '{"new": 9}', encoding="utf-8"
    )

    def fake_search(args):
        return json.dumps(
            {
                "ads": [_ad()],
                "count": 1,
                "complete": True,
                "fetched": 1,
                "country": "AE",
                "resolved": {"page_name": "KFC", "score": 1.0},
            }
        )

    def fake_watch(_args):
        return json.dumps({"watchlist": [{"query": "KFC", "country": "AE"}]})

    def fake_check(_args):
        return json.dumps(
            {
                "results": [
                    {
                        "query": "KFC",
                        "country": "AE",
                        "error": "fetch_failed",
                        "partial": True,
                        "artifacts": {"error": "fetch_failed"},
                    }
                ]
            }
        )

    monkeypatch.setattr(tools, "ad_search", fake_search)
    monkeypatch.setattr(tools, "ad_watch", fake_watch)
    monkeypatch.setattr(tools, "ad_check", fake_check)
    monkeypatch.setattr(live_eval, "ROOT", tmp_path)

    work = tmp_path / "work"
    work.mkdir()
    row = live_eval.run_pair("KFC", "KFC", "AE", object(), work, pair.parent)

    assert row["status"] == "FAIL"
    assert row["check1"]["artifacts"] == {"error": "fetch_failed"}
    assert not (pair / "artifacts" / "digest.json").exists(), "stale digest survived"
    assert not (pair / "artifacts" / "check2").exists(), "stale check2 copy survived"
    on_disk = json.loads((pair / "result.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "FAIL"


def test_attempt_counts_separates_transport_from_dead_renders():
    """A 200 shell is a failure, not a success: 210 attempts / 0 failed hid 10."""
    dispatches = [
        {"failed": True, "transport_failed": True, "dead_render": None},
        {"failed": True, "transport_failed": False, "dead_render": "shell"},
        {"failed": True, "transport_failed": False, "dead_render": "shell"},
        {"failed": True, "transport_failed": False, "dead_render": "blocked"},
        {"failed": False, "transport_failed": False, "dead_render": None},
    ]
    counts = live_eval.attempt_counts(dispatches)

    assert counts["total"] == 5
    assert counts["failed"] == 4, "dead renders must count in the headline"
    assert counts["transport_failed"] == 1
    assert counts["parse_failed"] == 3
    assert counts["shell"] == 2
    assert counts["blocked"] == 1
    assert counts["markup_changed"] == 0


def test_attempt_counts_treats_legacy_failed_as_transport():
    """Old attempts.json rows carry only ``failed``."""
    older = live_eval.attempt_counts([{"failed": True}, {"failed": False}])
    assert older["transport_failed"] == 1
    assert older["parse_failed"] == 0
    assert older["failed"] == 1


def test_aggregate_reports_dead_renders_as_failures(tmp_path):
    rows = {
        "kfc-ae": {
            "brand": "KFC",
            "country": "AE",
            "status": "FAIL",
            "failures": [],
            "attempts": {
                "total": 4,
                "failed": 3,
                "transport_failed": 0,
                "parse_failed": 3,
                "shell": 3,
                "blocked": 0,
                "markup_changed": 0,
            },
        },
        "kfc-us": {
            "brand": "KFC",
            "country": "US",
            "status": "PASS",
            "failures": [],
            "attempts": {
                "total": 2,
                "failed": 1,
                "transport_failed": 1,
                "parse_failed": 0,
                "shell": 0,
                "blocked": 0,
                "markup_changed": 0,
            },
        },
    }
    for name, row in rows.items():
        folder = tmp_path / name
        folder.mkdir()
        (folder / "result.json").write_text(json.dumps(row), encoding="utf-8")

    live_eval.aggregate(tmp_path)
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")

    assert "attempts: 6  failed: 4 (67%)" in summary, summary
    assert "transport 1, dead render 3 (shell 3, blocked 0, markup_changed 0)" in summary
    assert "## Dead renders" in summary
    assert "KFC AE: 3 / 4 attempts (shell 3" in summary


# ---------------------------------------------------------------------------
# Currency spot-check: only a present non-AED token is a caveat, never a FAIL.
# ---------------------------------------------------------------------------


def test_currency_aed_present_is_a_clean_pass():
    currency = live_eval.currency_check("AE", "KFC AED 5 meal")
    assert currency["ok"] is True
    assert currency["found"] == ["AED"]
    assert currency["caveat"] is None


def test_currency_no_price_token_is_unknown_not_missing():
    """McDonald's AE carries 0 price tokens; that is not a product failure."""
    currency = live_eval.currency_check("AE", "McDonald's\nOrder now")
    assert currency["ok"] is None
    assert currency["found"] == []
    assert currency["caveat"].startswith("unknown:")


def test_currency_neighbour_gcc_token_is_a_caveat_not_a_failure():
    """Pizza Hut AE shipped an OMR creative: record it, do not fail the pair."""
    currency = live_eval.currency_check("AE", "Pizza Hut OMR 3.500")
    assert currency["found"] == ["OMR"]
    assert currency["ok"] is False
    assert currency["caveat"] == "non_aed: OMR"


def test_currency_aed_wins_over_a_stray_other_token():
    currency = live_eval.currency_check("AE", "AED 20 / OMR 2")
    assert currency["ok"] is True


def test_currency_ascii_marker_needs_a_word_boundary():
    """``SAR`` inside a name is not a Saudi riyal."""
    currency = live_eval.currency_check("AE", "Sarah's Salon\nOrder now")
    assert currency["found"] == []
    assert currency["caveat"].startswith("unknown:")


def test_currency_eg_is_record_only():
    currency = live_eval.currency_check("EG", "KFC EGP 120")
    assert currency["expected"] == "EGP/جنيه"
    assert currency["ok"] is True
    assert currency["caveat"] is None


def test_currency_check_never_produces_a_failure_label():
    """The pair-level oracle has no currency failure path left."""
    import inspect

    source = inspect.getsource(live_eval.currency_check)
    assert "currency_missing" not in source
    assert "failures.append" not in source
