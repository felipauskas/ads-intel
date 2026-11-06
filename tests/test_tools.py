import json
from pathlib import Path

import pytest

import tools

FIXTURE = Path(__file__).parent / "fixtures" / "library_page.md"

# Facts from the recorded render, asserted here so a fixture edit that moves
# them is caught by the regression tests below rather than silently weakening.
HEPSIBURADA_ID = "8932462163548008"
NIKE_IDS = {
    "1785179045778580",
    "962050096457659",
    "1700063364126216",
    "1841713136987087",
}

AD = {
    "id": "1",
    "page_name": "Nike",
    "status": "active",
    "first_seen": "May 1, 2026",
    "last_seen": "",
    "creative_text": "v1",
    "library_url": "https://www.facebook.com/ads/library/?id=1",
}


def _patch_fetch(monkeypatch, fn):
    """Adapt an ads-returning stub to ad_search's meta-aware fetch seam."""
    def wrapper(*args, **kwargs):
        ads = fn(*args, **kwargs)
        return list(ads), {
            "complete": True,
            "fetched": len(ads),
            "total_returned": len(ads),
            "fetched_chars": 100,
            "char_limit": 120000,
        }

    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", wrapper)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.store, "_data_dir", lambda: tmp_path)
    return tmp_path


def test_ad_search_returns_count_and_ads(monkeypatch):
    _patch_fetch(monkeypatch, lambda q, **kw: [AD])
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["count"] == 1
    assert payload["ads"][0]["id"] == "1"


def test_ad_search_fetch_failure(monkeypatch):
    def boom(query, **kwargs):
        raise RuntimeError("network down")

    _patch_fetch(monkeypatch, boom)
    payload = json.loads(tools.ad_search({"query": "nike"}))
    assert payload["error"].startswith("fetch_failed")


def test_search_labels_parse_failure(monkeypatch):
    def boom(query, **kwargs):
        raise tools.sources.ParseError("3 card markers but no parseable ad", cards_seen=3)

    _patch_fetch(monkeypatch, boom)
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
    _patch_fetch(monkeypatch, lambda q, **kw: [AD])
    payload = json.loads(tools.ad_search({"query": "nike", "limit": "many"}))
    assert payload == {"error": "invalid limit"}


def test_ad_search_accepts_host_kwargs(monkeypatch):
    _patch_fetch(monkeypatch, lambda q, **kw: [])
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

    _patch_fetch(monkeypatch, fake_fetch)
    for bad in ("ae", "AEX", "", "A1", "U", "US\n", 123, ["AE"], {"country": "AE"}):
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
    _patch_fetch(monkeypatch, lambda q, **kw: list(noise))

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
    # Skipped rows keep the result contract: completeness and an artifact slot.
    assert row["partial"] is True
    assert row["artifacts"] == {"error": "fetch_empty"}
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
    assert row["partial"] is True
    assert row["artifacts"] == {"error": "fetch_failed"}
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
    assert row["partial"] is True
    assert row["artifacts"] == {"error": "parse_failed"}
    assert "new_ads" not in row
    assert snap_path.read_bytes() == before
    assert tools.store.load_snapshot("nike")["ads"]["1"]["id"] == "1"


def test_ad_check_name_not_matched_keeps_result_contract(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike", "advertiser": "KFC"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["error"] == "name_not_matched"
    assert row["partial"] is False
    assert row["artifacts"] == {"error": "name_not_matched"}
    assert "new_ads" not in row


def test_ad_check_unexpected_failure_row_keeps_result_contract(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(tools.store, "save_snapshot", explode)
    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["error"] == "disk full"
    assert row["partial"] is True
    assert row["artifacts"] == {"error": "disk full"}


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


def test_duplicate_watch_variants_do_not_clobber(monkeypatch, data_dir):
    """Same query+country, one unfiltered watch and one KFC watch.

    They used to share one snapshot/report key, so each run rewrote the other's
    baseline and every check reported spurious new/ended ads.
    """
    (data_dir / tools.store.WATCH).write_text(
        json.dumps(
            [
                {"query": "KFC", "country": "US"},
                {"query": "KFC", "country": "US", "advertiser": "KFC"},
            ]
        )
    )
    ads = [
        {**AD, "id": "k1", "page_name": "KFC"},
        {**AD, "id": "o1", "page_name": "Other"},
    ]
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch(ads))

    first = json.loads(tools.ad_check({}))["results"]
    second = json.loads(tools.ad_check({}))["results"]

    assert len(first) == len(second) == 2
    assert (first[0]["new_ads"], first[0]["ended_ads"]) == (2, 0)
    assert (first[1]["new_ads"], first[1]["ended_ads"]) == (1, 0)
    for rows in (first, second):
        assert rows[0]["artifacts"]["html"] != rows[1]["artifacts"]["html"]
    for row in second:
        assert (row["new_ads"], row["ended_ads"], row["changed_ads"]) == (0, 0, 0)


def test_watch_add_persists_advertiser(data_dir):
    items = json.loads(
        tools.ad_watch({"action": "add", "query": "KFC", "advertiser": "KFC"})
    )["watchlist"]
    assert items == [{"query": "KFC", "country": "US", "advertiser": "KFC"}]
    # Legacy entries without the field still load untouched.
    assert json.loads(tools.ad_watch({"action": "list"}))["watchlist"] == items


def test_ad_check_empty_watchlist(monkeypatch):
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([]))
    payload = json.loads(tools.ad_check({}))
    assert payload["results"] == []
    assert payload["checked_at"]


def test_check_returns_artifact_paths(monkeypatch, tmp_path):
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    payload = json.loads(tools.ad_check({}))
    row = payload["results"][0]
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
    # One stamp per run: the digest and the response agree.
    assert digest["checked_at"] == payload["checked_at"]


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


class _FixtureCtx:
    """Host context stub: every web_extract returns the recorded render."""

    def __init__(self, content):
        self.content = content

    def dispatch_tool(self, name, args):
        return {"results": [{"url": args["urls"][0], "content": self.content}]}


def _serve_fixture(monkeypatch):
    """Drive the real fetch/parse path off the recorded library page."""
    text = FIXTURE.read_text()
    # Guard the fixture facts the assertions below depend on.
    parsed = tools.sources.parse_library_markdown(text)
    assert len(parsed) == 28
    assert [ad["id"] for ad in parsed].index(HEPSIBURADA_ID) > 20
    assert {ad["id"] for ad in parsed if ad["page_name"] == "Nike"} == NIKE_IDS

    monkeypatch.setattr(tools, "_CTX", _FixtureCtx(text))


def test_check_advertiser_resolves_beyond_first_twenty(monkeypatch):
    """A page that only appears past position 20 must still resolve.

    Resolution used to run on the first 20 keyword hits, so Hepsiburada (index
    24 of 28 in the recorded render) reported `name_not_matched` even though
    the page was on the page.
    """
    tools.ad_watch({"action": "add", "query": "nike", "advertiser": "Hepsiburada"})
    _serve_fixture(monkeypatch)

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row.get("error") != "name_not_matched"
    assert row["resolved"]["page_name"] == "Hepsiburada"
    assert row["new_ads"] >= 1
    assert HEPSIBURADA_ID in [ad["id"] for ad in row["new"]]
    # The snapshot is keyed by advertiser and seeded with the resolved ad.
    snap = tools.store.load_snapshot("nike", advertiser="Hepsiburada")["ads"]
    assert list(snap) == [HEPSIBURADA_ID]


def test_name_not_matched_marks_partial_on_clipped_render(monkeypatch):
    """A clipped render that hides the brand page is a partial miss, not a fact.

    The row used to report `name_not_matched` with no `partial` at all, so a
    caller could not tell "the page is absent" from "the render stopped early".
    """
    tools.ad_watch({"action": "add", "query": "nike", "advertiser": "Nike"})
    noise = [{**AD, "id": "entel", "page_name": "entel"}]
    monkeypatch.setattr(
        tools.sources, "fetch_ads_with_meta", _stub_fetch(noise, complete=False)
    )

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["error"] == "name_not_matched"
    assert row["partial"] is True


def test_check_advertiser_keeps_all_brand_ads(monkeypatch):
    """Nike has 4 ads; only 3 sit inside the first 20 hits.

    The 4th used to be invisible to the diff, so the snapshot stalled at 3 and
    the complete render still looked complete.
    """
    tools.ad_watch({"action": "add", "query": "nike", "advertiser": "Nike"})
    _serve_fixture(monkeypatch)

    first = json.loads(tools.ad_check({}))["results"][0]
    # The advertiser path fetches the full parse: nothing was sliced, so the
    # row must not be flagged partial.
    assert first["partial"] is False
    assert sorted(ad["id"] for ad in first["new"]) == sorted(NIKE_IDS)
    assert first["new_ads"] == 4
    assert len(tools.store.load_snapshot("nike", advertiser="Nike")["ads"]) == 4

    second = json.loads(tools.ad_check({}))["results"][0]
    assert (second["new_ads"], second["ended_ads"], second["changed_ads"]) == (0, 0, 0)
    assert set(tools.store.load_snapshot("nike", advertiser="Nike")["ads"]) == NIKE_IDS


def test_search_advertiser_resolves_beyond_limit(monkeypatch):
    """`advertiser` resolves against the full parse, then applies `limit`."""
    _serve_fixture(monkeypatch)

    payload = json.loads(
        tools.ad_search({"query": "nike", "advertiser": "Hepsiburada", "limit": 10})
    )
    assert payload["resolved"]["page_name"] == "Hepsiburada"
    assert payload["count"] == 1
    assert [ad["id"] for ad in payload["ads"]] == [HEPSIBURADA_ID]


def test_search_advertiser_exactly_limit_is_complete(monkeypatch):
    """An advertiser page with exactly `limit` ads was not sliced: complete."""
    _serve_fixture(monkeypatch)

    payload = json.loads(
        tools.ad_search({"query": "nike", "advertiser": "Nike", "limit": len(NIKE_IDS)})
    )
    assert payload["count"] == len(NIKE_IDS)
    assert payload["complete"] is True

    # One fewer: the requested limit clipped the brand's ads, so partial.
    payload = json.loads(
        tools.ad_search({"query": "nike", "advertiser": "Nike", "limit": len(NIKE_IDS) - 1})
    )
    assert payload["count"] == len(NIKE_IDS) - 1
    assert payload["complete"] is False


def test_search_rejects_invalid_filters(monkeypatch):
    dispatched = []

    def fake_fetch(*args, **kwargs):
        dispatched.append(kwargs)
        return []

    _patch_fetch(monkeypatch, fake_fetch)
    for bad in ("paused", "", "ALL", 1, ["active"]):
        payload = json.loads(
            tools.ad_search({"query": "nike", "active_status": bad})
        )
        assert payload == {"error": "invalid_active_status"}, bad
    for bad in ("carousel", "", "VIDEO", 1, ["image"]):
        payload = json.loads(tools.ad_search({"query": "nike", "media_type": bad}))
        assert payload == {"error": "invalid_media_type"}, bad
    assert dispatched == []


def test_search_passes_filters_to_fetch(monkeypatch):
    seen = {}

    def fake_fetch(query, **kwargs):
        seen.update(kwargs)
        return [AD]

    _patch_fetch(monkeypatch, fake_fetch)
    payload = json.loads(
        tools.ad_search(
            {"query": "nike", "active_status": "active", "media_type": "image"}
        )
    )
    assert "error" not in payload
    assert seen["active_status"] == "active"
    assert seen["media_type"] == "image"

    # Omitted or JSON-null filters mean "all", never an error.
    json.loads(tools.ad_search({"query": "nike"}))
    assert seen["active_status"] == "all" and seen["media_type"] == "all"
    json.loads(
        tools.ad_search({"query": "nike", "active_status": None, "media_type": None})
    )
    assert seen["active_status"] == "all" and seen["media_type"] == "all"


def test_watch_add_persists_filters():
    json.loads(
        tools.ad_watch(
            {
                "action": "add",
                "query": "nike",
                "active_status": "active",
                "media_type": "video",
            }
        )
    )
    assert json.loads(tools.ad_watch({"action": "list"}))["watchlist"] == [
        {
            "query": "nike",
            "country": "US",
            "active_status": "active",
            "media_type": "video",
        }
    ]


def test_watch_add_rejects_invalid_filters():
    payload = json.loads(
        tools.ad_watch({"action": "add", "query": "nike", "active_status": "paused"})
    )
    assert payload == {"error": "invalid_active_status"}
    payload = json.loads(
        tools.ad_watch({"action": "add", "query": "nike", "media_type": "carousel"})
    )
    assert payload == {"error": "invalid_media_type"}
    assert json.loads(tools.ad_watch({"action": "list"}))["watchlist"] == []


def test_check_uses_entry_filters_and_isolates_snapshots(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    tools.ad_watch(
        {"action": "add", "query": "nike", "active_status": "active", "media_type": "image"}
    )
    seen = []

    def fake_fetch(query, **kwargs):
        seen.append(kwargs)
        return [AD], {"complete": True, "fetched_chars": 10, "char_limit": 120000}

    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", fake_fetch)
    payload = json.loads(tools.ad_check({}))
    assert "error" not in payload
    filters = sorted(
        (kw.get("active_status"), kw.get("media_type")) for kw in seen
    )
    assert filters == [("active", "image"), ("all", "all")]
    # Each variant keeps its own baseline and artifacts.
    htmls = {r["artifacts"]["html"] for r in payload["results"]}
    assert len(htmls) == 2


def test_check_summaries_surface_enriched_fields(monkeypatch):
    ad = {
        **AD,
        "page_url": "https://www.facebook.com/nike/",
        "page_id": "15087023444",
        "link_url": "https://nike.com/shoes",
        "link_title": "Air Max",
        "cta_text": "Shop Now",
        "images": ["https://scontent.xx.fbcdn.net/600x600/a.jpg"],
        "has_video": False,
        "same_creative_count": 4,
        "multiple_versions": True,
    }
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([ad]))
    payload = json.loads(tools.ad_check({}))
    row = payload["results"][0]["new"][0]
    for key in (
        "page_url",
        "page_id",
        "link_url",
        "link_title",
        "cta_text",
        "images",
        "has_video",
        "same_creative_count",
        "multiple_versions",
    ):
        assert key in row, key
    assert row["cta_text"] == "Shop Now"
    assert row["same_creative_count"] == 4


def test_summary_never_null_for_missing_fields():
    """A pre-upgrade 7-key snapshot must summarize with typed defaults."""
    old = {
        key: AD[key]
        for key in (
            "id",
            "page_name",
            "status",
            "first_seen",
            "last_seen",
            "creative_text",
            "library_url",
        )
    }
    # Every summarized key must have an explicit typed default; the two
    # declarations are maintained by hand and drift silently otherwise.
    assert tuple(tools._SUMMARY_KEYS) == tuple(tools._SUMMARY_DEFAULTS)
    summary = tools._summary(old)
    assert summary["page_url"] == ""
    assert summary["page_id"] == ""
    assert summary["link_url"] == ""
    assert summary["link_title"] == ""
    assert summary["cta_text"] == ""
    assert summary["images"] == []
    assert summary["has_video"] is False
    assert summary["same_creative_count"] == 0
    assert summary["multiple_versions"] is False
    assert all(value is not None for value in summary.values())
    # Caller-owned lists must not share one mutable default.
    summary["images"].append("x")
    assert tools._summary(old)["images"] == []


def test_check_row_echoes_filters_only_when_non_default(monkeypatch):
    tools.ad_watch(
        {"action": "add", "query": "nike", "active_status": "active", "media_type": "video"}
    )
    tools.ad_watch({"action": "add", "query": "kfc"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    rows = json.loads(tools.ad_check({}))["results"]
    assert rows[0]["active_status"] == "active"
    assert rows[0]["media_type"] == "video"
    assert "active_status" not in rows[1]
    assert "media_type" not in rows[1]


def test_search_reports_complete_and_fetched(monkeypatch):
    _serve_fixture(monkeypatch)

    sliced = json.loads(tools.ad_search({"query": "nike", "limit": 5}))
    assert sliced["count"] == 5
    assert sliced["complete"] is False
    assert sliced["fetched"] == 5

    whole = json.loads(tools.ad_search({"query": "nike", "limit": 50}))
    assert whole["count"] == 28
    assert whole["complete"] is True
    assert whole["fetched"] == 28


def test_search_rejects_infinite_and_nan_limit(monkeypatch):
    """JSON `1e309` decodes to inf; `int(inf)` must not escape as a crash."""
    dispatched = []

    def fake_fetch(*args, **kwargs):
        dispatched.append((args, kwargs))
        return [], {}

    _patch_fetch(monkeypatch, fake_fetch)
    for bad in (float("inf"), float("-inf"), float("nan")):
        payload = json.loads(tools.ad_search({"query": "x", "limit": bad}))
        assert payload == {"error": "invalid limit"}, bad
    assert dispatched == []


def test_check_advertiser_ignores_unstamped_unfiltered_baseline(monkeypatch):
    """Regression: advertiser watch on a pre-stamp unfiltered baseline.

    The baseline holds all 28 keyword-hit ads; only Nike's 4 may be reported
    new, and the 24 non-Nike ones must never be reported `ended`.
    """
    tools.ad_watch({"action": "add", "query": "nike", "advertiser": "Nike"})
    text = FIXTURE.read_text()
    baseline = {
        ad["id"]: ad for ad in tools.sources.parse_library_markdown(text)
    }
    path = tools.store._snapshot_path("nike", "US")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"query": "nike", "ads": baseline}))
    _serve_fixture(monkeypatch)

    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["new_ads"] == 4
    assert row["ended_ads"] == 0
    assert sorted(ad["id"] for ad in row["new"]) == sorted(NIKE_IDS)


def test_summary_carries_last_seen_and_creative_text():
    assert "last_seen" in tools._SUMMARY_KEYS
    assert "creative_text" in tools._SUMMARY_KEYS
    summary = tools._summary(AD)
    assert len(summary) == 16
    assert summary["last_seen"] == AD["last_seen"]
    assert summary["creative_text"] == AD["creative_text"]

    old = {"id": "1", "page_name": "Nike", "status": "active"}
    defaults = tools._summary(old)
    assert defaults["last_seen"] == ""
    assert defaults["creative_text"] == ""


def test_check_bucket_items_are_sixteen_fields(monkeypatch):
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools.sources, "fetch_ads_with_meta", _stub_fetch([AD]))

    row = json.loads(tools.ad_check({}))["results"][0]
    item = row["new"][0]
    assert set(item) == set(tools._SUMMARY_KEYS)
    assert len(item) == 16
    assert all(value is not None for value in item.values())


def test_check_malformed_body_does_not_seed_empty_snapshot(monkeypatch):
    """A short corrupt body must be a fetch failure, not a 0-ad success."""
    tools.ad_watch({"action": "add", "query": "nike"})
    monkeypatch.setattr(tools, "_CTX", _StringCtx("{not json"))

    row = json.loads(tools.ad_check({}))["results"][0]
    assert "error" in row
    assert row["artifacts"] == {"error": row["error"]}
    assert tools.store.load_snapshot("nike") == {"ads": {}}

    # With a prior baseline the run skips and keeps the snapshot untouched.
    tools.store.save_snapshot("nike", {"ads": {"1": AD}})
    row = json.loads(tools.ad_check({}))["results"][0]
    assert row["skipped"] is True
    assert row["reason"] == "fetch_empty"
    assert row["artifacts"] == {"error": "fetch_failed"}
    assert tools.store.load_snapshot("nike")["ads"]["1"]["id"] == "1"


class _StringCtx:
    """Host context stub returning a raw string body from web_extract."""

    def __init__(self, body):
        self.body = body

    def dispatch_tool(self, name, args):
        return self.body
