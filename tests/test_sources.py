import json
from pathlib import Path

import pytest

import sources

FIXTURE = Path(__file__).parent / "fixtures" / "library_page.md"


@pytest.fixture(scope="module")
def ads():
    return sources.parse_library_markdown(FIXTURE.read_text())


def test_build_url_encodes_query():
    url = sources.build_url("nike shoes", country="GB")
    assert "facebook.com/ads/library" in url
    assert "q=nike+shoes" in url
    assert "country=GB" in url


def test_fixture_parses_all_cards(ads):
    assert len(ads) == 28
    assert len({ad["id"] for ad in ads}) == 28
    for ad in ads:
        assert ad["id"]
        assert ad["page_name"]
        assert ad["status"] in {"active", "ended"}
        assert ad["library_url"] == (
            f"https://www.facebook.com/ads/library/?id={ad['id']}"
        )


def test_fixture_has_both_statuses(ads):
    statuses = {ad["status"] for ad in ads}
    assert statuses == {"active", "ended"}


def test_card_fields_are_normalized(ads):
    ad = next(a for a in ads if a["id"] == "1785179045778580")
    assert ad["page_name"] == "Nike"
    assert ad["status"] == "ended"
    assert ad["first_seen"] == "May 7, 2026"
    assert ad["last_seen"] == "Jun 29, 2026"
    assert ad["creative_text"].startswith("Entra a Nike.com")
    # CTA / image markdown is not creative copy.
    assert "doubleclick" not in ad["creative_text"].lower()
    assert "![" not in ad["creative_text"]


def test_active_ad_with_single_date(ads):
    ad = next(a for a in ads if a["id"] == "1550534860016399")
    assert ad["status"] == "active"
    assert ad["first_seen"] == "May 19, 2026"
    assert ad["last_seen"] == ""


def test_build_url_uses_country_param():
    url = sources.build_url("KFC", country="AE")
    assert "country=AE" in url
    assert "country=US" not in url
    assert "country=US" in sources.build_url("KFC")

    # The country is threaded through the fetcher, not just the URL builder.
    calls = []

    def fake_dispatch(name, args):
        calls.append(args)
        return "no cards here. No ads match your search."

    sources.fetch_ads("KFC", country="AE", dispatch=fake_dispatch)
    assert calls[0]["urls"] == [sources.build_url("KFC", country="AE")]


def test_fetch_ads_uses_dispatch_and_limit():
    text = FIXTURE.read_text()
    calls = []

    def fake_dispatch(name, args):
        calls.append((name, args))
        return text

    ads = sources.fetch_ads("nike", limit=5, dispatch=fake_dispatch)
    assert len(ads) == 5
    assert calls[0][0] == "web_extract"
    assert calls[0][1]["urls"] == [sources.build_url("nike")]
    # The ad-library page renders to ~58k chars; the host default truncates at 15k.
    assert calls[0][1]["char_limit"] >= 45000


def test_char_limit_exceeds_largest_fixture():
    # The real page renders ~50k+ chars; a budget at or below the render size
    # makes the host return a truncated prefix and silently loses cards.
    assert sources._CHAR_LIMIT > len(FIXTURE.read_text())


def test_fetch_marks_truncated_when_render_hits_budget():
    text = FIXTURE.read_text()
    budget = 8000
    # A render that fills the whole budget is a truncated prefix, so the
    # listing is not complete even though parsing succeeds.
    ads, meta = sources.fetch_ads_with_meta(
        "nike",
        limit=50,
        dispatch=lambda n, a: text[:budget],
        char_limit=budget,
    )
    assert ads
    assert meta == {
        "complete": False,
        "complete_scope": "rendered_window",
        "fetched": 2,
        "total_returned": 2,
        "fetched_chars": budget,
        "char_limit": budget,
    }

    # A short render fits inside the budget: the listing is complete.
    short_ads, short_meta = sources.fetch_ads_with_meta(
        "nike",
        limit=50,
        dispatch=lambda n, a: text,
        char_limit=sources._CHAR_LIMIT,
    )
    assert len(short_ads) == 28
    assert short_meta["complete"] is True
    assert short_meta["fetched_chars"] == len(text)


def test_fetch_marks_partial_when_result_limit_hits():
    """A render with more ads than `limit` is partial: the tail was sliced off."""
    text = FIXTURE.read_text()
    assert len(sources.parse_library_markdown(text)) == 28

    ads, meta = sources.fetch_ads_with_meta(
        "nike",
        limit=20,
        dispatch=lambda n, a: text,
        char_limit=sources._CHAR_LIMIT,
    )
    assert len(ads) == 20
    assert meta["complete"] is False
    assert meta["fetched_chars"] == len(text)

    # The whole render fits under the limit: complete.
    all_ads, all_meta = sources.fetch_ads_with_meta(
        "nike",
        limit=50,
        dispatch=lambda n, a: text,
        char_limit=sources._CHAR_LIMIT,
    )
    assert len(all_ads) == 28
    assert all_meta["complete"] is True


def test_fetch_with_limit_none_returns_full_parse():
    """`limit=None` means no result slicing; only clipping makes it partial."""
    text = FIXTURE.read_text()

    ads, meta = sources.fetch_ads_with_meta(
        "nike", limit=None, dispatch=lambda n, a: text, char_limit=sources._CHAR_LIMIT
    )
    assert len(ads) == 28
    assert meta["complete"] is True

    # The char-budget signal still applies: a clipped prefix is partial.
    budget = 8000
    clipped, clipped_meta = sources.fetch_ads_with_meta(
        "nike", limit=None, dispatch=lambda n, a: text[:budget], char_limit=budget
    )
    assert clipped
    assert clipped_meta["complete"] is False

    # A JSON array is returned whole, and nothing was sliced off it.
    payload = json.dumps([{"id": str(i), "page_name": "Nike"} for i in range(1, 30)])
    json_ads, json_meta = sources.fetch_ads_with_meta(
        "nike", limit=None, dispatch=lambda n, a: payload
    )
    assert len(json_ads) == 29
    assert json_meta["complete"] is True
    # The compat wrapper passes `limit=None` through too.
    assert len(sources.fetch_ads("nike", limit=None, dispatch=lambda n, a: text)) == 28


def test_json_array_exactly_limit_is_complete():
    """A JSON array whose length equals `limit` was not sliced: complete."""
    payload = json.dumps([{"id": str(i), "page_name": "Nike"} for i in range(1, 6)])
    ads, meta = sources.fetch_ads_with_meta("nike", limit=5, dispatch=lambda n, a: payload)
    assert len(ads) == 5
    assert meta["total_returned"] == 5
    assert meta["fetched"] == 5
    assert meta["complete"] is True

    # One more ad than the limit: the tail was sliced off, so partial.
    wider = json.dumps([{"id": str(i), "page_name": "Nike"} for i in range(1, 7)])
    ads, meta = sources.fetch_ads_with_meta("nike", limit=5, dispatch=lambda n, a: wider)
    assert len(ads) == 5
    assert meta["total_returned"] == 6
    assert meta["complete"] is False


def test_completeness_is_scoped_to_the_rendered_window():
    """``complete`` means the render was not clipped, not "all results got".

    There is no pagination: a complete listing is still only the top-N window
    Meta rendered. The machine-readable scope marker makes that explicit so a
    caller cannot read ``complete`` as "the whole result set was retrieved".
    """
    text = FIXTURE.read_text()
    assert sources.COMPLETENESS_SCOPE == "rendered_window"
    _, meta = sources.fetch_ads_with_meta(
        "nike", limit=50, dispatch=lambda n, a: text, char_limit=sources._CHAR_LIMIT
    )
    assert meta["complete"] is True
    assert meta["complete_scope"] == sources.COMPLETENESS_SCOPE

    # The scope marker is present on the partial side too: clipping changes
    # only the boolean, never the meaning of what it is a completeness of.
    _, clipped = sources.fetch_ads_with_meta(
        "nike", limit=20, dispatch=lambda n, a: text, char_limit=sources._CHAR_LIMIT
    )
    assert clipped["complete"] is False
    assert clipped["complete_scope"] == sources.COMPLETENESS_SCOPE


def test_fetch_marks_partial_on_truncation_footer_marker():
    """The host's head+tail footer means cards were dropped from the middle."""
    text = FIXTURE.read_text()
    clipped = text[: len(text) // 2] + (
        "\n\n[... middle omitted — see footer ...]\n\n"
        "──────── [TRUNCATED] ────────\n"
        "Showing 40,000 chars (head) + 13,000 chars (tail) of 90,000 total clean characters.\n"
    )

    ads, meta = sources.fetch_ads_with_meta(
        "nike",
        limit=50,
        dispatch=lambda n, a: clipped,
        char_limit=sources._CHAR_LIMIT,
    )
    assert ads
    assert meta["complete"] is False


def test_fetch_ads_decodes_json_envelope():
    text = FIXTURE.read_text()
    envelope = json.dumps(
        {
            "results": [
                {"url": "u", "title": "t", "content": text, "error": None}
            ],
            "has_more": False,
        }
    )
    ads = sources.fetch_ads("nike", limit=40, dispatch=lambda n, a: envelope)
    assert len(ads) == 28

    # A dict result with the same shape (no JSON encoding) also decodes.
    ads_dict = sources.fetch_ads(
        "nike", limit=40, dispatch=lambda n, a: json.loads(envelope)
    )
    assert len(ads_dict) == 28


def test_fetch_ads_envelope_result_error_raises():
    envelope = json.dumps(
        {"results": [{"url": "u", "content": None, "error": "blocked"}]}
    )
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike", dispatch=lambda n, a: envelope)


def test_fetch_ads_error_payload_raises():
    with pytest.raises(sources.FetchError):
        sources.fetch_ads(
            "nike", dispatch=lambda n, a: json.dumps({"error": "boom"})
        )
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike", dispatch=lambda n, a: {"error": "boom"})


def test_fetch_ads_empty_envelope_results_raises():
    with pytest.raises(sources.FetchError):
        sources.fetch_ads(
            "nike", dispatch=lambda n, a: json.dumps({"results": []})
        )


def test_fetch_ads_no_cards_is_empty():
    assert sources.fetch_ads("nike", dispatch=lambda n, a: "No ads match your search.") == []


def test_fetch_ads_missing_dispatch_or_result_raises():
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike")
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike", dispatch=lambda n, a: None)


def test_parse_library_markdown_none_is_empty():
    assert sources.parse_library_markdown(None) == []


def test_json_array_payload_is_parsed_not_silently_zero():
    text = FIXTURE.read_text()

    # The host envelope may arrive as a JSON array of result objects.
    envelope = json.dumps(
        [{"url": "u", "title": "t", "content": text, "error": None}]
    )
    ads = sources.fetch_ads("nike", limit=40, dispatch=lambda n, a: envelope)
    assert ads
    assert all(ad["id"] for ad in ads)

    # A bare array of ad objects is decoded too.
    bare = json.dumps(
        [
            {
                "id": "123",
                "page_name": "Nike",
                "status": "active",
                "first_seen": "May 1, 2026",
                "last_seen": "",
                "creative_text": "v1",
            }
        ]
    )
    assert [ad["id"] for ad in sources.fetch_ads("nike", dispatch=lambda n, a: bare)] == [
        "123"
    ]

    # An array we cannot interpret must never come back as a silent [].
    with pytest.raises(sources.ParseError):
        sources.fetch_ads(
            "nike", dispatch=lambda n, a: json.dumps([{"weird": True}])
        )


def test_nonempty_render_without_cards_raises_parse_error():
    # A markup change: the card markers are still there but nothing parses.
    page = (
        "Ad Library\n\n**Sponsored**\n\nBuy shoes now.\n\nActive\n\n"
        "Library ID 1046730950862281\n"
    )
    with pytest.raises(sources.ParseError):
        sources.parse_library_markdown(page)
    with pytest.raises(sources.ParseError):
        sources.fetch_ads("nike", dispatch=lambda n, a: page)

    # A genuinely empty results page has no card markers and stays empty.
    empty = (
        "Ad Library\n\nNo ads match your search.\n\n"
        "* * *\n\nFilters\n\n* * *\n\nPrivacy\n"
    )
    assert sources.parse_library_markdown(empty) == []


def test_chrome_shell_render_is_parse_error_not_silent_zero():
    # A pre-hydration shell (nav + country list, no cards, no empty-state
    # wording) must never be reported as a confident empty listing, at ANY
    # size. Live Meta renders hit both variants: ~2k and ~5.1k chars.
    shell = Path("evals/raw/web_extract-KFC-AE.md").read_text()
    assert "Library ID" not in shell and "**Sponsored**" not in shell
    with pytest.raises(sources.ParseError):
        sources.parse_library_markdown(shell)
    short_shell = "Ad Library\n\nSelect country\n\n* * *\n\nPrivacy\n"
    assert len(short_shell) < 5000
    with pytest.raises(sources.ParseError):
        sources.parse_library_markdown(short_shell)


def test_fetch_retries_once_with_cache_bust_on_parse_error():
    text = FIXTURE.read_text()
    calls = []

    def dispatch(name, args):
        calls.append(args["urls"][0])
        if len(calls) == 1:
            return {"results": [{"content": "Ad Library\n\nSelect country\n\n"}]}
        return {"results": [{"content": text}]}

    ads = sources.fetch_ads("nike", limit=5, dispatch=dispatch)
    assert len(ads) == 5
    assert len(calls) == 2
    assert calls[1] != calls[0] and "cache_bust" in calls[1]


def test_lowercase_country_is_normalized_not_rejected():
    import tools

    assert tools.ad_watch(
        {"action": "list"}  # warm path; country logic tested below
    ) is not None
    # tools._requested_country uppercases before validating.
    assert tools._requested_country({"country": "ae"}) == "AE"
    assert tools._requested_country({"country": "sa"}) == "SA"
    assert tools._requested_country({"country": "eg"}) == "EG"


def test_long_render_without_markers_raises_parse_error():
    # A render far longer than an empty results page that still carries no card
    # markers is drift: pagination/JS chrome rendered without the card markup.
    page = "Ad Library\n\n" + ("Some unrelated chrome line.\n\n" * 400)
    assert len(page) > 5000
    assert "* * *" not in page and "**Sponsored**" not in page
    with pytest.raises(sources.ParseError):
        sources.parse_library_markdown(page)


# --- Task 1: free field enrichment (page/link/cta/media/creative grouping) ---

NEW_KEYS = (
    "page_url",
    "page_id",
    "link_url",
    "link_title",
    "cta_text",
    "images",
    "has_video",
    "same_creative_count",
    "multiple_versions",
)


def test_every_ad_carries_new_fields_with_safe_defaults(ads):
    for ad in ads:
        for key in NEW_KEYS:
            assert key in ad, key
        assert isinstance(ad["page_url"], str)
        assert isinstance(ad["page_id"], str)
        assert isinstance(ad["link_url"], str)
        assert isinstance(ad["link_title"], str)
        assert isinstance(ad["cta_text"], str)
        assert isinstance(ad["images"], list)
        assert isinstance(ad["has_video"], bool)
        assert isinstance(ad["same_creative_count"], int)
        assert isinstance(ad["multiple_versions"], bool)
        # Existing seven keys still intact.
        assert ad["library_url"] == (
            f"https://www.facebook.com/ads/library/?id={ad['id']}"
        )


def test_page_url_and_numeric_page_id(ads):
    nike = next(a for a in ads if a["id"] == "1785179045778580")
    assert nike["page_url"] == "https://www.facebook.com/nike/"
    assert nike["page_id"] == ""  # vanity handle, not numeric

    sukeban = next(a for a in ads if a["id"] == "161966936869658")
    assert sukeban["page_url"] == "https://www.facebook.com/61551864263186/"
    assert sukeban["page_id"] == "61551864263186"


def test_numeric_page_ids_are_digits_only(ads):
    for ad in ads:
        if ad["page_id"]:
            assert ad["page_id"].isdigit()


def test_cta_block_extracts_link_title_and_cta(ads):
    nike = next(a for a in ads if a["id"] == "1785179045778580")
    assert nike["link_url"].startswith("https://www.nike.com/mx/t/")
    assert nike["link_title"] == (
        "Calzado de entrenamiento para hombre Nike MC Trainer 2 - Azul"
    )
    assert nike["cta_text"] == "Shop Now"
    assert nike["link_url"] not in nike["creative_text"]


def test_single_line_cta_block(ads):
    # "[Nike Rose Gold Pack: Only at JD\\ Shop Now](https://...)"
    ad = next(a for a in ads if a["id"] == "2016127759183309")
    assert ad["link_url"] == "https://www.jdsports.com/plp/only-at-jd/brand=nike"
    assert ad["link_title"] == "Nike Rose Gold Pack: Only at JD"
    assert ad["cta_text"] == "Shop Now"


def test_help_link_never_becomes_link_url(ads):
    # This card's only link block is "[Learn more](facebook.com/help/...)".
    ad = next(a for a in ads if a["id"] == "950739567707496")
    assert ad["link_url"] == ""
    assert "facebook.com/help" not in ad["link_url"]
    # The real CTA block is still found when a help link precedes it.
    jd = next(a for a in ads if a["id"] == "1528069365362900")
    assert jd["link_url"].startswith("https://www.jdsports.com/pdp/")
    assert "help" not in jd["link_url"]


def test_images_exclude_profile_pic_and_keep_creative_media(ads):
    nike = next(a for a in ads if a["id"] == "1785179045778580")
    assert len(nike["images"]) == 1
    assert "600x600" in nike["images"][0]
    assert all("60x60" not in url for url in nike["images"])

    supersports = next(a for a in ads if a["id"] == "950739567707496")
    assert len(supersports["images"]) == 16
    assert all("scontent" in url for url in supersports["images"])


def test_has_video_flag_and_no_invented_url(ads):
    video = next(a for a in ads if a["id"] == "161966936869658")
    assert video["has_video"] is True
    assert not any("video" in url for url in video["images"])

    static = next(a for a in ads if a["id"] == "1785179045778580")
    assert static["has_video"] is False


def test_same_creative_count_and_multiple_versions(ads):
    ad = next(a for a in ads if a["id"] == "1213554506948614")
    assert ad["same_creative_count"] == 4
    assert ad["multiple_versions"] is False

    ad = next(a for a in ads if a["id"] == "1007351262282618")
    assert ad["same_creative_count"] == 2
    assert ad["multiple_versions"] is True

    ad = next(a for a in ads if a["id"] == "1785179045778580")
    assert ad["same_creative_count"] == 0
    assert ad["multiple_versions"] is False


def test_json_payload_backward_compatible_defaults():
    """Old snapshots (only the original seven keys) keep working."""
    payload = json.dumps(
        [
            {
                "id": "123",
                "page_name": "Acme",
                "status": "active",
                "first_seen": "May 1, 2026",
                "last_seen": "",
                "creative_text": "hi",
                "library_url": "https://www.facebook.com/ads/library/?id=123",
            }
        ]
    )
    ad = sources.fetch_ads("acme", dispatch=lambda n, a: payload)[0]
    assert ad["page_url"] == ""
    assert ad["page_id"] == ""
    assert ad["link_url"] == ""
    assert ad["link_title"] == ""
    assert ad["cta_text"] == ""
    assert ad["images"] == []
    assert ad["has_video"] is False
    assert ad["same_creative_count"] == 0
    assert ad["multiple_versions"] is False


def test_json_payload_preserves_supplied_new_fields():
    payload = json.dumps(
        [
            {
                "id": "9",
                "page_name": "Acme",
                "page_url": "https://www.facebook.com/acme/",
                "page_id": "42",
                "link_url": "https://acme.test/x",
                "link_title": "X",
                "cta_text": "Shop Now",
                "images": ["https://cdn.test/a.jpg"],
                "has_video": True,
                "same_creative_count": 3,
                "multiple_versions": True,
            }
        ]
    )
    ad = sources.fetch_ads("acme", dispatch=lambda n, a: payload)[0]
    assert ad["page_url"] == "https://www.facebook.com/acme/"
    assert ad["page_id"] == "42"
    assert ad["link_url"] == "https://acme.test/x"
    assert ad["images"] == ["https://cdn.test/a.jpg"]
    assert ad["has_video"] is True
    assert ad["same_creative_count"] == 3
    assert ad["multiple_versions"] is True


def test_json_payload_rejects_non_http_link_url():
    """A stored payload must never hand a javascript:/data: URL to a report."""
    payload = json.dumps(
        [
            {"id": "1", "page_name": "Acme", "link_url": "javascript:alert(1)"},
            {"id": "2", "page_name": "Acme", "link_url": "data:text/html,x"},
            {"id": "3", "page_name": "Acme", "link_url": "ftp://acme.test/x"},
            {"id": "4", "page_name": "Acme", "link_url": "https://acme.test/ok"},
            {"id": "5", "page_name": "Acme", "link_url": "http://acme.test/ok"},
        ]
    )
    by_id = {
        ad["id"]: ad
        for ad in sources.fetch_ads("acme", dispatch=lambda n, a: payload)
    }
    for rejected in ("1", "2", "3"):
        assert by_id[rejected]["link_url"] == ""
    assert by_id["4"]["link_url"] == "https://acme.test/ok"
    assert by_id["5"]["link_url"] == "http://acme.test/ok"


def test_json_payload_filters_non_http_image_urls():
    payload = json.dumps(
        [
            {
                "id": "1",
                "page_name": "Acme",
                "images": [
                    "https://cdn.test/a.jpg",
                    "http://cdn.test/b.jpg",
                    "javascript:alert(1)",
                    "data:image/png;base64,AAAA",
                    123,
                    None,
                ],
            }
        ]
    )
    ad = sources.fetch_ads("acme", dispatch=lambda n, a: payload)[0]
    assert ad["images"] == ["https://cdn.test/a.jpg", "http://cdn.test/b.jpg"]


def test_json_payload_rejects_non_http_library_url():
    """`library_url` is rendered as an href: only http(s) or the id fallback."""
    payload = json.dumps(
        [
            {"id": "1", "library_url": "javascript:alert(document.cookie)"},
            {"id": "2", "library_url": "data:text/html,x"},
            {"id": "3", "library_url": "https://www.facebook.com/ads/library/?id=3"},
            {"id": "4", "library_url": None},
        ]
    )
    by_id = {
        ad["id"]: ad
        for ad in sources.fetch_ads("acme", dispatch=lambda n, a: payload)
    }
    for rejected in ("1", "2", "4"):
        assert by_id[rejected]["library_url"] == (
            f"{sources._LIBRARY_BASE}?id={rejected}"
        ), rejected
    assert by_id["3"]["library_url"] == (
        "https://www.facebook.com/ads/library/?id=3"
    )


def test_json_payload_page_id_must_be_digits_only():
    payload = json.dumps(
        [
            {"id": "1", "page_name": "Acme", "page_id": "12ab"},
            {"id": "2", "page_name": "Acme", "page_id": "https://facebook.com/99"},
            {"id": "3", "page_name": "Acme", "page_id": " 42 "},
            {"id": "4", "page_name": "Acme", "page_id": 77},
            {"id": "5", "page_name": "Acme", "page_id": None},
        ]
    )
    by_id = {
        ad["id"]: ad
        for ad in sources.fetch_ads("acme", dispatch=lambda n, a: payload)
    }
    assert by_id["1"]["page_id"] == ""
    assert by_id["2"]["page_id"] == ""
    assert by_id["3"]["page_id"] == "42"
    assert by_id["4"]["page_id"] == "77"
    assert by_id["5"]["page_id"] == ""


def test_json_payload_bools_are_strictly_coerced():
    """The string "false" is truthy in Python; it must not become True."""
    payload = json.dumps(
        [
            {
                "id": "1",
                "page_name": "Acme",
                "has_video": "false",
                "multiple_versions": "false",
            },
            {
                "id": "2",
                "page_name": "Acme",
                "has_video": "true",
                "multiple_versions": "TRUE",
            },
            {
                "id": "3",
                "page_name": "Acme",
                "has_video": 0,
                "multiple_versions": 1,
            },
        ]
    )
    by_id = {
        ad["id"]: ad
        for ad in sources.fetch_ads("acme", dispatch=lambda n, a: payload)
    }
    assert by_id["1"]["has_video"] is False
    assert by_id["1"]["multiple_versions"] is False
    assert by_id["2"]["has_video"] is True
    assert by_id["2"]["multiple_versions"] is True
    assert by_id["3"]["has_video"] is False
    assert by_id["3"]["multiple_versions"] is True


def test_json_payload_same_creative_count_is_non_negative_int():
    payload = json.dumps(
        [
            {"id": "1", "page_name": "Acme", "same_creative_count": -3},
            {"id": "2", "page_name": "Acme", "same_creative_count": "2"},
            {"id": "3", "page_name": "Acme", "same_creative_count": "nope"},
            {"id": "4", "page_name": "Acme", "same_creative_count": None},
        ]
    )
    by_id = {
        ad["id"]: ad
        for ad in sources.fetch_ads("acme", dispatch=lambda n, a: payload)
    }
    assert by_id["1"]["same_creative_count"] == 0
    assert by_id["2"]["same_creative_count"] == 2
    assert by_id["3"]["same_creative_count"] == 0
    assert by_id["4"]["same_creative_count"] == 0


SPLIT_CARD = """![Nike](https://cdn.test/pic_60x60.jpg)

[Nike](https://www.facebook.com/61551864263186/)

**Sponsored**

Fresh trainers are here.

![creative](https://cdn.test/creative_600x600.jpg)

Sorry, we're having trouble playing this video.

**4 ads** use this creative and text

This ad has multiple versions

[AD.DOUBLECLICK.NET\\\\
\\\\
Fresh trainers for every run\\\\
\\\\
Shop Now](https://shop.test/trainers)

* * *

Active

Library ID: 987654321

May 1, 2026 - Jun 1, 2026
"""


def test_orphan_header_merge_carries_creative_fields():
    """A card split at a capture boundary must keep its whole creative."""
    ads = sources.parse_library_markdown(SPLIT_CARD)
    assert len(ads) == 1
    ad = ads[0]
    assert ad["id"] == "987654321"
    assert ad["page_name"] == "Nike"
    assert ad["page_url"] == "https://www.facebook.com/61551864263186/"
    assert ad["page_id"] == "61551864263186"
    assert ad["creative_text"] == "Fresh trainers are here."
    assert ad["images"] == ["https://cdn.test/creative_600x600.jpg"]
    assert ad["link_url"] == "https://shop.test/trainers"
    assert ad["link_title"] == "Fresh trainers for every run"
    assert ad["cta_text"] == "Shop Now"
    assert ad["has_video"] is True
    assert ad["same_creative_count"] == 4
    assert ad["multiple_versions"] is True

def test_build_url_defaults_to_all_filters():
    url = sources.build_url("nike")
    assert "active_status=all" in url
    assert "media_type=all" in url


def test_build_url_applies_filters():
    url = sources.build_url("nike", country="GB", active_status="inactive", media_type="video")
    assert "active_status=inactive" in url
    assert "media_type=video" in url
    assert "country=GB" in url
    assert "q=nike" in url
    # Still the single free public library URL: no API key or token params.
    assert url.startswith("https://www.facebook.com/ads/library/")
    assert "access_token" not in url


def test_build_url_rejects_invalid_filters():
    with pytest.raises(ValueError):
        sources.build_url("nike", active_status="paused")
    with pytest.raises(ValueError):
        sources.build_url("nike", media_type="carousel")


def test_build_url_rejects_invalid_country():
    """The country is interpolated into the URL: validate before any network use."""
    for bad in ("us", "USA", "", "A1", "U", "US\n", None, 123):
        with pytest.raises(ValueError, match="invalid_country"):
            sources.build_url("nike", country=bad)


def test_fetch_threads_filters_into_the_url():
    calls = []

    def fake_dispatch(name, args):
        calls.append(args)
        return "no cards here. No ads match your search."

    sources.fetch_ads(
        "nike", dispatch=fake_dispatch, active_status="active", media_type="image"
    )
    assert calls[0]["urls"] == [
        sources.build_url("nike", active_status="active", media_type="image")
    ]

    calls.clear()
    sources.fetch_ads_with_meta(
        "nike", dispatch=fake_dispatch, active_status="inactive", media_type="video"
    )
    assert "active_status=inactive" in calls[0]["urls"][0]
    assert "media_type=video" in calls[0]["urls"][0]


def test_fetch_rejects_invalid_filters():
    def fake_dispatch(name, args):
        return "no cards here. No ads match your search."

    with pytest.raises(ValueError):
        sources.fetch_ads("nike", dispatch=fake_dispatch, active_status="paused")
    with pytest.raises(ValueError):
        sources.fetch_ads("nike", dispatch=fake_dispatch, media_type="carousel")


def test_meta_reports_fetched_and_total_returned():
    """Meta names how many ads were returned and how many the render held."""
    text = FIXTURE.read_text()

    ads, meta = sources.fetch_ads_with_meta(
        "nike",
        limit=5,
        dispatch=lambda n, a: text,
        char_limit=sources._CHAR_LIMIT,
    )
    assert len(ads) == 5
    assert meta["complete"] is False
    assert meta["fetched"] == 5
    assert meta["total_returned"] == 28

    full_ads, full_meta = sources.fetch_ads_with_meta(
        "nike",
        limit=None,
        dispatch=lambda n, a: text,
        char_limit=sources._CHAR_LIMIT,
    )
    assert len(full_ads) == 28
    assert full_meta["complete"] is True
    assert full_meta["fetched"] == 28
    assert full_meta["total_returned"] == 28


def test_json_meta_reports_fetched_and_total_returned():
    payload = json.dumps([{"id": str(i), "page_name": "Nike"} for i in range(1, 30)])
    ads, meta = sources.fetch_ads_with_meta(
        "nike", limit=5, dispatch=lambda n, a: payload
    )
    assert len(ads) == 5
    assert meta == {
        "complete": False,
        "complete_scope": "rendered_window",
        "fetched": 5,
        "total_returned": 29,
        "fetched_chars": 0,
        "char_limit": sources._CHAR_LIMIT,
    }


@pytest.mark.parametrize(
    "body",
    [
        "{not json",
        '{"results": [{"content":',
        '"just a string"',
        "null",
        "true",
        "12345",
    ],
)
def test_short_malformed_json_body_raises_fetch_error(body):
    """A body that is JSON-shaped but unusable must fail, not read as 0 ads.

    With no prior snapshot a silent empty page seeds an empty baseline and
    reports a successful zero-ad check, masking a transport failure.
    """
    with pytest.raises(sources.FetchError):
        sources.fetch_ads_with_meta("nike", dispatch=lambda n, a: body)
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike", dispatch=lambda n, a: body)


@pytest.mark.parametrize("payload", [None, 123, "a string", [], [1, 2]])
def test_content_from_payload_rejects_non_object_payload(payload):
    with pytest.raises(sources.FetchError):
        sources._content_from_payload(payload)


@pytest.mark.parametrize("payload", [{}, {"foo": "bar"}, {"results": [{"content": None}]}])
def test_content_from_payload_object_without_results_raises(payload):
    with pytest.raises(sources.FetchError):
        sources._content_from_payload(payload)


@pytest.mark.parametrize("items", ["a string", 12345, None])
def test_ads_from_payload_list_rejects_non_list_payload(items):
    with pytest.raises(sources.FetchError):
        sources._ads_from_payload_list(items, None)


# --- page / host footers ---------------------------------------------------
#
# A render ends with the ad library's own page footer (``System status`` plus
# the Ad Library API / About / Privacy / Terms / Cookies links). When the page
# is clipped, the host appends a truncation footer naming an absolute cache
# path. Neither is creative copy, and the cache path differs between two
# renders of the same ad, which used to make ``diff_snapshots`` report a
# spurious "changed".

_FOOTER_LINKS = [
    "- [Ad Library API](https://www.facebook.com/ads/library/api/?source=archive-landing-page)",
    "- [About ads and data use](https://www.facebook.com/ads/about/?entry_product=ad_library)",
    "- [Privacy](https://www.facebook.com/privacy/center/?entry_point=privacy_basics_redirect)",
    "- [Terms](https://www.facebook.com/policies/)",
    "- [Cookies](https://www.facebook.com/policies/cookies/)",
]


def _card(creative: str, *, status: str = "Active", library_id: str = "1234567890") -> str:
    """One parseable card: page label, creative body, then the status block."""
    return "\n\n".join(
        [
            "[Nike](https://www.facebook.com/nike/)",
            "**Sponsored**",
            creative,
            status,
            f"Library ID: {library_id}",
            "Jul 1, 2026",
            "Platforms",
            "See ad details",
        ]
    )


def _host_footer(cache_name: str) -> str:
    return "\n\n".join(
        [
            "──────── [TRUNCATED] ────────",
            "Showing 89,984 chars (head) + 29,896 chars (tail) of 283,270 total clean characters.",
            f"Full text saved to: /Users/someone/.hermes/profiles/partner/cache/web/{cache_name}.md",
            (
                'To read the omitted middle: read_file path="/Users/someone/.hermes/'
                f'profiles/partner/cache/web/{cache_name}.md" offset=3547 limit=200  '
                "(the file is the complete page; raise/lower offset to page through it)."
            ),
            "─────────────────────────────",
        ]
    )


def test_golden_fixture_creative_has_no_page_footer(ads):
    """Ad 1046730950862281 is header-only (an image creative): the paired
    status block must not contribute the page footer as "creative text"."""
    ad = next(a for a in ads if a["id"] == "1046730950862281")
    assert ad["creative_text"] == ""
    assert "System status" not in ad["creative_text"]
    assert "Ad Library API" not in ad["creative_text"]
    assert "Cookies" not in ad["creative_text"]


def test_page_footer_is_stripped_from_creative():
    page = _card("\n\n".join(["Ad copy line one.", "Ad copy line two.", "System status", *_FOOTER_LINKS]))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == "Ad copy line one.\nAd copy line two."


def test_page_footer_with_backslash_wraps_is_stripped():
    """Some renders escape the footer's wrapped markdown lines with ``\\``."""
    footer = ["See more\\", "\\"] + [f"{line}\\" for line in _FOOTER_LINKS] + ["\\"]
    page = _card("\n\n".join(["Ad copy.", *footer]))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == "Ad copy."


def test_host_truncation_footer_is_stripped_from_creative():
    page = _card("\n\n".join(["Ad copy before the footer.", *_FOOTER_LINKS, _host_footer("www.facebook.com-dcfa2890c9")]))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    creative = ads[0]["creative_text"]
    assert creative == "Ad copy before the footer."
    assert "Full text saved to:" not in creative
    assert "/Users/" not in creative
    assert "TRUNCATED" not in creative


def test_footer_cache_path_does_not_change_creative():
    """Two renders of the same ad differ only in the host's cache filename."""
    first = sources.parse_library_markdown(
        _card("\n\n".join(["Ad copy.", *_FOOTER_LINKS, _host_footer("www.facebook.com-aaaaaaaa")]))
    )
    second = sources.parse_library_markdown(
        _card("\n\n".join(["Ad copy.", *_FOOTER_LINKS, _host_footer("www.facebook.com-bbbbbbbb")]))
    )
    assert first[0]["creative_text"] == second[0]["creative_text"] == "Ad copy."


def test_footer_only_creative_becomes_empty():
    page = _card("\n\n".join(_FOOTER_LINKS))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == ""


def test_host_footer_unstored_variant_is_stripped():
    """When the host cache write fails, its footer says so instead of naming
    a path; that sentence is chrome too and must not leak into creative_text."""
    footer = "\n\n".join(
        [
            "──────── [TRUNCATED] ────────",
            "Showing 89,984 chars (head) + 29,896 chars (tail) of 283,270 total clean characters.",
            (
                "Full text could not be stored; re-run web_extract on a more "
                "specific URL or open it in the browser for the complete page."
            ),
            "─────────────────────────────",
        ]
    )
    page = _card("\n\n".join(["Ad copy before the footer.", footer]))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    creative = ads[0]["creative_text"]
    assert creative == "Ad copy before the footer."
    assert "could not be stored" not in creative
    assert "TRUNCATED" not in creative


def test_trailing_box_drawing_divider_is_creative_copy():
    """A lone box-drawing line inside a creative is a divider, not a footer."""
    page = _card("Copy line\n\n──────────")
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == "Copy line\n──────────"

    # Same for a divider drawn with a different run length.
    page = _card("Copy line\n\n────────────")
    ads = sources.parse_library_markdown(page)
    assert ads[0]["creative_text"] == "Copy line\n────────────"


def test_host_footer_divider_still_stripped_after_tightening():
    """The banner/divider pair around a host footer is still removed whole."""
    page = _card("\n\n".join(["Ad copy.", _host_footer("www.facebook.com-cccccccc")]))
    ads = sources.parse_library_markdown(page)
    assert ads[0]["creative_text"] == "Ad copy."


def test_doubled_backslash_escaped_footer_is_stripped():
    """Some renders escape a wrapped footer line with two trailing backslashes."""
    footer = [
        "System status\\\\",
        *[f"{line}\\\\" for line in _FOOTER_LINKS],
        "─────────────────────────────\\\\",
    ]
    page = _card("\n\n".join(["Ad copy.", *footer]))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == "Ad copy."
    assert "facebook.com" not in ads[0]["creative_text"]


def test_host_footer_cache_path_with_spaces_is_stripped():
    """Cache directories can contain spaces; the path line is still chrome."""
    footer = "\n\n".join(
        [
            "──────── [TRUNCATED] ────────",
            "Showing 10,000 chars (head) + 5,000 chars (tail) of 40,000 total clean characters.",
            "Full text saved to: /Users/Some User/Library/Application Support/cache/web/page.md",
            (
                "To read the omitted middle: read_file path=\"/Users/Some User/"
                "Library/Application Support/cache/web/page.md\" offset=100 limit=200  "
                "(the file is the complete page; raise/lower offset to page through it)."
            ),
            "─────────────────────────────",
        ]
    )
    page = _card("\n\n".join(["Ad copy.", footer]))
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == "Ad copy."
    assert "Full text saved to:" not in ads[0]["creative_text"]
    assert "/Users/" not in ads[0]["creative_text"]


def test_mid_copy_system_status_is_preserved():
    """Only a *trailing* ``System status`` chrome label is stripped."""
    page = _card("System status\nis what our customers care about.")
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == (
        "System status\nis what our customers care about."
    )


def test_mid_copy_policy_url_is_preserved():
    """A facebook policy link inside the copy is not the page footer."""
    creative = "\n\n".join(
        [
            "Read our privacy notes:",
            "- [Privacy](https://www.facebook.com/privacy/center/?entry_point=x)",
            "Questions? Contact us.",
        ]
    )
    page = _card(creative)
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert "facebook.com/privacy/center" in ads[0]["creative_text"]
    assert ads[0]["creative_text"].startswith("Read our privacy notes:")
    assert ads[0]["creative_text"].endswith("Questions? Contact us.")


def test_escaped_bare_link_does_not_swallow_copy():
    """A wrapped-render ``\\`` after a complete link must not open a CTA block.

    The link is a full ``[title](url)`` on one line; the trailing escape is
    only a markdown line-wrap artifact. Treating it as an unclosed CTA block
    dropped every following line of real copy.
    """
    creative = "\n\n".join(
        [
            "Real copy.",
            "[English (US)](https://www.facebook.com/ads/library/?locale=es_LA&id=123#)",
            "More real copy…",
            "and this too",
        ]
    )
    # Simulate the render's trailing backslash on the bare-link line.
    creative = creative.replace("#)", "#)\\", 1)
    page = _card(creative)
    ads = sources.parse_library_markdown(page)
    assert len(ads) == 1
    assert ads[0]["creative_text"] == "Real copy.\nMore real copy…\nand this too"
    assert "English (US)" not in ads[0]["creative_text"]


# --- branch coverage: date fallback, payload edge cases ---------------------


def test_dates_returns_empty_when_status_or_id_precedes_a_date():
    """A status/id line before a date stops the scan: no dates.

    The date after the status line is what makes this test bite: without the
    early return, the scan would walk on and pick up "Jul 1, 2026".
    """
    assert sources._dates(["Library ID: 1", "Active"], 0) == ("", "")
    assert sources._dates(["Library ID: 1", "Library ID: 2"], 0) == ("", "")
    assert (
        sources._dates(
            ["Library ID: 1", "Active", "Started running on Jul 1, 2026"], 0
        )
        == ("", "")
    )


def test_dates_returns_empty_when_no_date_within_window():
    assert sources._dates(["Library ID: 1", "", "", "", "", ""], 0) == ("", "")


def test_normalise_ad_wraps_scalar_images_in_a_list():
    """A payload that stores one image URL as a bare string still loads."""
    ad = sources._normalise_ad({"id": "1", "images": "https://cdn.test/a.png"})
    assert ad is not None
    assert ad["images"] == ["https://cdn.test/a.png"]


def test_ads_from_payload_list_rejects_empty_list():
    with pytest.raises(sources.FetchError, match="empty results"):
        sources._ads_from_payload_list([], None)


@pytest.mark.parametrize("body", ["123abc", "-not json", "null-ish", "truex"])
def test_looks_like_json_scalar_returns_false_when_undecodable(body):
    """A scalar-looking prefix that will not decode is not a corrupt scalar."""
    assert sources._looks_like_json_scalar(body) is False


def test_string_body_whitespace_only_raises_empty_content():
    with pytest.raises(sources.FetchError, match="empty content"):
        sources.fetch_ads_with_meta("nike", dispatch=lambda n, a: "   \n")


@pytest.mark.parametrize("value", [None, [], {}, object()])
def test_as_bool_treats_non_scalar_values_as_false(value):
    assert sources._as_bool(value) is False
