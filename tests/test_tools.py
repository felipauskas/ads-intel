import json

import pytest

import tools

AD = {
    "id": "1",
    "page_name": "Nike",
    "status": "active",
    "first_seen": "May 1, 2026",
    "last_seen": "",
    "creative_text": "v1",
    "library_url": "https://www.facebook.com/ads/library/?id=1",
}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.store, "_data_dir", lambda: tmp_path)
    return tmp_path


def test_ad_search_returns_count_and_ads(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [AD])
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["count"] == 1
    assert payload["ads"][0]["id"] == "1"


def test_ad_search_fetch_failure(monkeypatch):
    def boom(query, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(tools.sources, "fetch_ads", boom)
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["error"].startswith("fetch_failed")


def test_search_labels_parse_failure(monkeypatch):
    def boom(query, **kwargs):
        raise tools.sources.ParseError("3 card markers but no parseable ad", cards_seen=3)

    monkeypatch.setattr(tools.sources, "fetch_ads", boom)
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["error"].startswith("parse_failed")
    assert payload["cards_seen"] == 3
    assert "count" not in payload


def test_ad_search_requires_query():
    assert json.loads(tools.ad_search({})) == {"error": "query required"}
    assert json.loads(tools.ad_search({"query": "  "})) == {
        "error": "query required"
    }


def test_ad_search_rejects_bad_limit(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [AD])
    payload = json.loads(tools.ad_search({"query": "nike", "limit": "many"}))
    assert payload == {"error": "invalid limit"}


def test_ad_search_accepts_host_kwargs(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [])
    raw = tools.ad_search({"query": "x"}, task_id="t", session_id="s")
    assert isinstance(json.loads(raw), dict)


def test_ad_watch_roundtrip():
    assert json.loads(tools.ad_watch({"action": "add", "query": "nike"}))[
        "watchlist"
    ] == ["nike"]
    assert json.loads(tools.ad_watch({"action": "list"}))["watchlist"] == ["nike"]
    assert json.loads(tools.ad_watch({"action": "remove", "query": "nike"}))[
        "watchlist"
    ] == []


def test_ad_watch_add_requires_query():
    assert json.loads(tools.ad_watch({"action": "add", "query": "  "})) == {
        "error": "query required"
    }


def test_ad_watch_unknown_action():
    payload = json.loads(tools.ad_watch({"action": "explode"}))
    assert payload["error"].startswith("unknown action")


def test_ad_watch_store_failure_is_contained(monkeypatch):
    def boom(query):
        raise OSError("disk full")

    monkeypatch.setattr(tools.store, "watch_add", boom)
    payload = json.loads(tools.ad_watch({"action": "add", "query": "nike"}))
    assert payload["error"].startswith("watch_failed")


def test_ad_check_detects_then_settles(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [AD])

    first = json.loads(tools.ad_check({}))
    assert first["results"][0]["new_ads"] == 1
    assert first["results"][0]["new"][0]["id"] == "1"

    second = json.loads(tools.ad_check({}))
    row = second["results"][0]
    assert (row["new_ads"], row["ended_ads"], row["changed_ads"]) == (0, 0, 0)


def test_ad_check_empty_fetch_keeps_snapshot(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    tools.store.save_snapshot("nike", {"ads": {"1": AD}})
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [])

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["skipped"] is True
    assert row["reason"] == "fetch_empty"
    assert "new_ads" not in row
    assert tools.store.load_snapshot("nike")["ads"]["1"]["id"] == "1"


def test_ad_check_fetch_error_keeps_snapshot(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    tools.store.save_snapshot("nike", {"ads": {"1": AD}})

    def boom(q, **kw):
        raise tools.sources.FetchError("blocked")

    monkeypatch.setattr(tools.sources, "fetch_ads", boom)
    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["skipped"] is True
    assert tools.store.load_snapshot("nike")["ads"]["1"]["id"] == "1"


def test_check_labels_parse_failure_and_preserves_snapshot(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    tools.store.save_snapshot("nike", {"ads": {"1": AD}})
    snap_path = tools.store._snapshot_path("nike")
    before = snap_path.read_bytes()

    def broken(q, **kw):
        raise tools.sources.ParseError("no cards parsed", cards_seen=3)

    monkeypatch.setattr(tools.sources, "fetch_ads", broken)
    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["skipped"] is True
    assert row["reason"] == "parse_failed"
    assert "new_ads" not in row
    assert snap_path.read_bytes() == before
    assert tools.store.load_snapshot("nike")["ads"]["1"]["id"] == "1"


def test_ad_check_empty_watchlist(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [])
    payload = json.loads(tools.ad_check({}))
    assert payload["results"] == []
    assert payload["checked_at"]
