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


def test_fetch_ads_empty_results():
    assert sources.fetch_ads("nike", dispatch=lambda n, a: "no cards here") == []
    assert sources.fetch_ads("nike", dispatch=lambda n, a: None) == []
    assert sources.fetch_ads("nike") == []
