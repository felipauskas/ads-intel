import json

import pytest

import tools


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.store, "_data_dir", lambda: tmp_path)
    return tmp_path


def test_ad_search_returns_count_and_ads(monkeypatch):
    ad = {
        "id": "1",
        "page_name": "Nike",
        "status": "active",
        "first_seen": "May 1, 2026",
        "last_seen": "",
        "creative_text": "v1",
        "library_url": "https://www.facebook.com/ads/library/?id=1",
    }
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [ad])
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["count"] == 1
    assert payload["ads"][0]["id"] == "1"


def test_ad_search_fetch_failure(monkeypatch):
    def boom(query, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(tools.sources, "fetch_ads", boom)
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["error"].startswith("fetch_failed")


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


def test_ad_check_detects_then_settles(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    ad = {
        "id": "1",
        "page_name": "Nike",
        "status": "active",
        "first_seen": "May 1, 2026",
        "last_seen": "",
        "creative_text": "v1",
        "library_url": "https://www.facebook.com/ads/library/?id=1",
    }
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [ad])

    first = json.loads(tools.ad_check({}))
    assert first["results"][0]["new_ads"] == 1
    assert first["results"][0]["new"][0]["id"] == "1"

    second = json.loads(tools.ad_check({}))
    row = second["results"][0]
    assert (row["new_ads"], row["ended_ads"], row["changed_ads"]) == (0, 0, 0)


def test_ad_check_empty_watchlist(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: [])
    payload = json.loads(tools.ad_check({}))
    assert payload["results"] == []
    assert payload["checked_at"]
