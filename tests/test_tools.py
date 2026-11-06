import json
from pathlib import Path

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
    ] == [{"query": "nike", "country": "US"}]
    assert json.loads(tools.ad_watch({"action": "list"}))["watchlist"] == [
        {"query": "nike", "country": "US"}
    ]
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


def test_search_rejects_malformed_country(monkeypatch):
    dispatched = []

    def fake_fetch(*args, **kwargs):
        dispatched.append((args, kwargs))
        return []

    monkeypatch.setattr(tools.sources, "fetch_ads", fake_fetch)
    for bad in ("ae", "AEX", "", "A1", "U", 123, ["AE"], {"country": "AE"}):
        payload = json.loads(tools.ad_search({"query": "KFC", "country": bad}))
        assert payload == {"error": "invalid_country"}, bad
    assert dispatched == []

    # An absent country defaults to US rather than erroring.
    payload = json.loads(tools.ad_search({"query": "KFC"}))
    assert "error" not in payload
    assert dispatched[-1][1]["country"] == "US"

    # A host that sends an optional field as JSON null means "not provided".
    payload = json.loads(tools.ad_search({"query": "KFC", "country": None}))
    assert "error" not in payload
    assert dispatched[-1][1]["country"] == "US"


def test_search_with_advertiser_filters_keyword_noise(monkeypatch):
    """`advertiser` keeps only the winning page, not every page mentioning it.

    The recorded library fixture holds a Nike render, so the Burger King noise
    from the live run (entel, Soundlines Group) is synthesised here.
    """
    noise = [
        {**AD, "id": "bk", "page_name": "Burger King"},
        {**AD, "id": "entel", "page_name": "entel"},
        {**AD, "id": "sound", "page_name": "Soundlines Group"},
    ]
    monkeypatch.setattr(tools.sources, "fetch_ads", lambda q, **kw: list(noise))

    payload = json.loads(
        tools.ad_search({"query": "Burger King", "advertiser": "Burger King"})
    )
    assert payload["count"] == 1
    assert [ad["id"] for ad in payload["ads"]] == ["bk"]
    assert payload["resolved"] == {"page_name": "Burger King", "score": 0.80}

    # A target no page matches reports the mismatch instead of pretending the
    # keyword hits are the advertiser.
    missed = json.loads(
        tools.ad_search({"query": "Burger King", "advertiser": "KFC"})
    )
    assert missed["error"] == "name_not_matched"
    assert missed["threshold"] == 0.80
    assert "ads" not in missed


def _stub_fetch(ads=None, complete=True):
    """Patch target for ad_check's meta-aware fetch seam."""
    meta = {"complete": complete, "fetched_chars": 100, "char_limit": 120000}
    return lambda q, **kw: (list(ads or []), dict(meta))


def test_ad_check_detects_then_settles(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    first = json.loads(tools.ad_check({}))
    assert first["results"][0]["new_ads"] == 1
    assert first["results"][0]["partial"] is False
    assert first["results"][0]["new"][0]["id"] == "1"

    second = json.loads(tools.ad_check({}))
    row = second["results"][0]
    assert (row["new_ads"], row["ended_ads"], row["changed_ads"]) == (0, 0, 0)


def test_ad_check_empty_fetch_keeps_snapshot(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    tools.store.save_snapshot("nike", {"ads": {"1": AD}})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([]))

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

    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", boom)
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

    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", broken)
    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["skipped"] is True
    assert row["reason"] == "parse_failed"
    assert "new_ads" not in row
    assert snap_path.read_bytes() == before
    assert tools.store.load_snapshot("nike")["ads"]["1"]["id"] == "1"


def test_truncated_fetch_reports_no_ended_ads(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    # A full prior listing of 29 ads.
    prior = {
        str(i): {**AD, "id": str(i)} for i in range(1, 30)
    }
    tools.store.save_snapshot("nike", {"ads": prior})

    # The new render was truncated: only 21 of them came back, one changed and
    # one genuinely new ad. The 8 missing ids are not evidence of anything.
    fetched = [
        {**AD, "id": str(i), "creative_text": "v2" if i == 1 else "v1"}
        for i in range(1, 22)
    ]
    fetched.append({**AD, "id": "99", "creative_text": "brand new"})
    monkeypatch.setattr(
        tools.sources,
        "fetch_ads_with_meta",
        lambda q, **kw: (
            fetched,
            {
                "complete": False,
                "fetched_chars": 120000,
                "char_limit": 120000,
            },
        ),
    )

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["partial"] is True
    assert row["ended_ads"] == 0
    assert row["ended"] == []
    assert row["new_ads"] == 1
    assert [ad["id"] for ad in row["new"]] == ["99"]
    assert row["changed_ads"] == 1
    assert [ad["id"] for ad in row["changed"]] == ["1"]

    # The partial baseline is merged with the prior one: ads that the render
    # never reached stay in the snapshot, and the one truly-new ad is added.
    snap = tools.store.load_snapshot("nike")["ads"]
    assert len(snap) == 30
    assert "1" in snap and "99" in snap
    assert all(str(i) in snap for i in range(1, 30))


def test_partial_run_then_complete_reports_no_new_ads(monkeypatch):
    """A partial run must not shrink the baseline into a false-new next run."""
    tools.ad_watch({"action": "add", "query": "nike"})
    prior = {str(i): {**AD, "id": str(i), "creative_text": "v1"} for i in range(1, 30)}
    tools.store.save_snapshot("nike", {"ads": prior})

    # First run: the render only reached the first 20 of the 29 known ads.
    partial_ads = [{**AD, "id": str(i), "creative_text": "v1"} for i in range(1, 21)]
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch(partial_ads, complete=False))

    first = json.loads(tools.ad_check({}))["results"][0]
    assert first["partial"] is True
    assert first["new_ads"] == 0
    assert first["ended_ads"] == 0
    snap = tools.store.load_snapshot("nike")["ads"]
    assert len(snap) == 29
    assert all(str(i) in snap for i in range(1, 30))

    # Second run: a complete render returns all 29. Nothing is new or ended.
    complete_ads = [{**AD, "id": str(i), "creative_text": "v1"} for i in range(1, 30)]
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch(complete_ads))

    second = json.loads(tools.ad_check({}))["results"][0]
    assert second["partial"] is False
    assert second["new_ads"] == 0
    assert second["ended_ads"] == 0
    assert second["changed_ads"] == 0


def test_check_partial_when_limit_truncates(monkeypatch):
    """Unknown completeness (no `complete` key) fails safe to partial."""
    tools.ad_watch({"action": "add", "query": "nike"})
    prior = {str(i): {**AD, "id": str(i), "creative_text": "v1"} for i in range(1, 30)}
    tools.store.save_snapshot("nike", {"ads": prior})

    truncated = [{**AD, "id": str(i), "creative_text": "v1"} for i in range(1, 21)]
    monkeypatch.setattr(
        tools.sources,
        "fetch_ads_with_meta",
        lambda q, **kw: (truncated, {"fetched_chars": 50000, "char_limit": 120000}),
    )

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["partial"] is True
    assert row["ended_ads"] == 0
    assert len(tools.store.load_snapshot("nike")["ads"]) == 29


def test_check_uses_watch_entry_country(monkeypatch, data_dir):
    (data_dir / tools.store.WATCH).write_text(
        json.dumps([{"query": "KFC", "country": "AE"}])
    )
    seen = []

    def fake_fetch(query, **kwargs):
        seen.append((query, kwargs.get("country")))
        return ([AD], {"complete": True, "fetched_chars": 100, "char_limit": 120000})

    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", fake_fetch)
    row = json.loads(tools.ad_check({}))["results"][0]
    assert seen == [("KFC", "AE")]
    assert row["query"] == "KFC"
    assert row["new_ads"] == 1


def test_check_artifacts_differ_by_country(monkeypatch, data_dir):
    """Same query in US and AE: separate artifacts, each with its own market's ads."""
    (data_dir / tools.store.WATCH).write_text(
        json.dumps(
            [
                {"query": "KFC", "country": "US"},
                {"query": "KFC", "country": "AE"},
            ]
        )
    )

    def fake_fetch(query, **kwargs):
        country = kwargs.get("country")
        ad = {**AD, "id": f"ad-{country}", "page_name": f"KFC {country}"}
        return ([ad], {"complete": True, "fetched_chars": 100, "char_limit": 120000})

    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", fake_fetch)
    rows = json.loads(tools.ad_check({}))["results"]
    assert [row["country"] for row in rows] == ["US", "AE"]

    us_row, ae_row = rows
    assert us_row["artifacts"]["html"] != ae_row["artifacts"]["html"]
    assert us_row["artifacts"]["digest"] != ae_row["artifacts"]["digest"]

    us_html = Path(us_row["artifacts"]["html"]).read_text()
    ae_html = Path(ae_row["artifacts"]["html"]).read_text()
    assert 'data-ad-id="ad-US"' in us_html
    assert 'data-ad-id="ad-AE"' not in us_html
    assert 'data-ad-id="ad-AE"' in ae_html
    assert 'data-ad-id="ad-US"' not in ae_html
    # The market is visible on the page, not only in the filename.
    assert "KFC (US)" in us_html
    assert "KFC (AE)" in ae_html

    assert json.loads(Path(us_row["artifacts"]["digest"]).read_text())["country"] == "US"
    assert json.loads(Path(ae_row["artifacts"]["digest"]).read_text())["country"] == "AE"


def test_ad_check_empty_watchlist(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([]))
    payload = json.loads(tools.ad_check({}))
    assert payload["results"] == []
    assert payload["checked_at"]


def test_check_returns_artifact_paths(monkeypatch, tmp_path):
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    row = json.loads(tools.ad_check({}))["results"][0]
    artifacts = row["artifacts"]
    assert set(artifacts) == {"html", "digest"}

    html_path = Path(artifacts["html"])
    digest_path = Path(artifacts["digest"])
    assert html_path.is_file() and html_path.suffix == ".html"
    assert digest_path.is_file() and digest_path.suffix == ".json"
    assert str(html_path).startswith(str(tmp_path))
    assert "html" in html_path.read_text().lower()
    digest = json.loads(digest_path.read_text())
    assert digest["query"] == "nike"
    assert digest["new"] == row["new_ads"] == 1


def test_check_survives_report_failure(monkeypatch):
    """A report write failure must degrade `artifacts`, never fail the check."""
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(tools.report, "write_report", boom)
    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["artifacts"] == {"error": "disk full"}
    assert row["new_ads"] == 1
    assert row["new"][0]["id"] == "1"
    assert row["ended_ads"] == 0
    assert row["changed_ads"] == 0
    assert "error" not in row

