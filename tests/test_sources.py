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
    # The ad-library page is ~49k chars; the host default truncates at 15k.
    assert calls[0][1]["char_limit"] >= 45000


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
    assert sources.fetch_ads("nike", dispatch=lambda n, a: "no cards here") == []


def test_fetch_ads_missing_dispatch_or_result_raises():
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike")
    with pytest.raises(sources.FetchError):
        sources.fetch_ads("nike", dispatch=lambda n, a: None)


def test_parse_library_markdown_none_is_empty():
    assert sources.parse_library_markdown(None) == []
