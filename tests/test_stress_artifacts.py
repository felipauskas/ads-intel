"""Contract tests for the stress harness's live artifact validation.

Existence-only checks are the failure mode this guards: the report path is
keyed by the watch, so a file can exist while describing another check. The
harness must verify content — the digest's counts/identity and the HTML's
counts banner — exactly as the live eval's checked-in-copy verifier does.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stress_e2e import _artifact_problems  # noqa: E402


def _row(tmp_path: Path, *, digest_counts=None, banner="1 new / 0 ended / 0 changed"):
    row = {
        "query": "KFC",
        "country": "US",
        "new_ads": 1,
        "ended_ads": 0,
        "changed_ads": 0,
    }
    counts = digest_counts or {"new": 1, "ended": 0, "changed": 0}
    digest = {"query": "KFC", "country": "US", **counts}
    html = tmp_path / "report.html"
    html.write_text(f"<html><body>{banner}</body></html>", encoding="utf-8")
    digest_path = tmp_path / "report.digest.json"
    digest_path.write_text(json.dumps(digest), encoding="utf-8")
    row["artifacts"] = {"html": str(html), "digest": str(digest_path)}
    return row


def test_matching_artifacts_pass(tmp_path):
    assert _artifact_problems(_row(tmp_path)) == []


def test_digest_with_wrong_counts_fails(tmp_path):
    """A digest that exists but describes another check is not evidence."""
    row = _row(tmp_path, digest_counts={"new": 0, "ended": 0, "changed": 1})
    problems = _artifact_problems(row)
    assert any(p.startswith("digest_new_mismatch") for p in problems), problems


def test_missing_file_fails(tmp_path):
    row = _row(tmp_path)
    Path(row["artifacts"]["html"]).unlink()
    problems = _artifact_problems(row)
    assert any(p.startswith("html_missing") for p in problems), problems


def test_artifacts_error_is_reported_not_ignored(tmp_path):
    row = _row(tmp_path)
    row["artifacts"] = {"error": "report write failed"}
    assert _artifact_problems(row) == ["artifacts_error: report write failed"]


def test_html_banner_mismatch_fails(tmp_path):
    row = _row(tmp_path, banner="0 new / 0 ended / 0 changed")
    problems = _artifact_problems(row)
    assert any(p.startswith("html_banner_mismatch") for p in problems), problems
