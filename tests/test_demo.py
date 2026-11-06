"""Offline end-to-end demo path: watch -> baseline -> tamper -> change.

Characterization test over the recorded Nike library render. Only the host
``web_extract`` dispatch is stubbed; URL building, parsing, snapshotting,
diffing and reporting all run for real.
"""

import json
from pathlib import Path

import pytest

import sources
import tools

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "library_page.md"

# ad_check does not pass a limit, so it inherits fetch_ads_with_meta's default.
AD_CHECK_LIMIT = 20


class _StubCtx:
    """Minimal host context: answers web_extract with the recorded render."""

    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def dispatch_tool(self, name, args):
        self.calls.append((name, args))
        return {"results": [{"url": args["urls"][0], "content": self.content}]}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.store, "_data_dir", lambda: tmp_path)
    return tmp_path


def test_demo_path_end_to_end(data_dir):
    markdown = FIXTURE.read_text()
    expected = sources.parse_library_markdown(markdown)
    assert expected, "fixture must parse to ads"
    assert len({ad["id"] for ad in expected}) == len(expected)

    ctx = _StubCtx(markdown)
    tools.set_ctx(ctx)
    try:
        # 1. Watch the recorded query.
        watched = json.loads(tools.ad_watch({"action": "add", "query": "nike"}))
        assert watched["watchlist"] == [{"query": "nike", "country": "US"}]

        # 2. First check: every ad that fits the fetch limit is new.
        first = json.loads(tools.ad_check({}))
        assert len(first["results"]) == 1
        baseline_row = first["results"][0]
        delivered = min(len(expected), AD_CHECK_LIMIT)
        # The fixture holds more ads than the check's default limit returns.
        assert len(expected) > AD_CHECK_LIMIT
        assert baseline_row["new_ads"] == delivered
        assert baseline_row["ended_ads"] == 0
        assert baseline_row["changed_ads"] == 0
        assert [ad["id"] for ad in baseline_row["new"]] == [
            ad["id"] for ad in expected[:delivered]
        ]
        # The render is longer than the default result limit, so the check
        # reports a partial listing and must not claim anything ended.
        assert baseline_row["partial"] is True
        assert baseline_row["ended"] == []

        # The real URL builder ran with the fixture's market.
        assert ctx.calls[0][0] == "web_extract"
        url = ctx.calls[0][1]["urls"][0]
        assert "country=US" in url and "q=nike" in url

        # 3. Tamper with one saved ad's creative text.
        snapshot = tools.store.load_snapshot("nike")
        assert len(snapshot["ads"]) == delivered
        target_id = expected[0]["id"]
        assert target_id in snapshot["ads"]
        snapshot["ads"][target_id]["creative_text"] = "tampered copy"
        tools.store.save_snapshot("nike", snapshot)

        # 4. Second check surfaces exactly that one change.
        second = json.loads(tools.ad_check({}))["results"][0]
        assert second["partial"] is True
        assert second["new_ads"] == 0
        assert second["ended_ads"] == 0
        assert second["changed_ads"] == 1
        assert [ad["id"] for ad in second["changed"]] == [target_id]

        # 5. Artifacts landed on disk and agree with the diff.
        artifacts = second["artifacts"]
        html_path = Path(artifacts["html"])
        digest_path = Path(artifacts["digest"])
        assert html_path.is_file() and html_path.suffix == ".html"
        assert digest_path.is_file() and digest_path.suffix == ".json"
        assert html_path.parent == data_dir / "reports"

        html = html_path.read_text()
        assert f'data-ad-id="{target_id}"' in html
        assert "0 new / 0 ended / 1 changed" in html

        digest = json.loads(digest_path.read_text())
        assert digest["query"] == "nike"
        assert digest["country"] == "US"
        assert digest["partial"] is True
        assert digest["new"] == second["new_ads"] == 0
        assert digest["ended"] == second["ended_ads"] == 0
        assert digest["changed"] == second["changed_ads"] == 1
        assert digest["total"] == len(tools.store.load_snapshot("nike")["ads"])
        assert digest["total"] == delivered

        # A partial run must not shrink the baseline.
        assert len(tools.store.load_snapshot("nike")["ads"]) == delivered
    finally:
        tools.set_ctx(None)
