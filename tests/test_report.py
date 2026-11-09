import json
from pathlib import Path

import pytest

import report
import store


def _ad(i, **over):
    ad = {
        "id": str(i),
        "page_name": "Nike <script>alert(1)</script>",
        "status": "active",
        "first_seen": "May 1, 2026",
        "last_seen": "Jun 1, 2026",
        "creative_text": "Just do it & <b>run</b>",
        "library_url": f"https://www.facebook.com/ads/library/?id={i}",
    }
    ad.update(over)
    return ad


META = {"checked_at": "2026-11-06T12:00:00", "partial": False}


def test_report_contains_every_ad_id(tmp_path):
    ads = {str(i): _ad(i) for i in range(1, 6)}
    ads["9"] = _ad(9, status="ended")
    diff = {"new": [ads["5"]], "ended": [ads["9"]], "changed": [ads["2"]]}

    paths = report.write_report("nike", diff, ads, META, tmp_path)
    html = Path(paths["html"]).read_text()

    for ad_id in ads:
        assert f'data-ad-id="{ad_id}"' in html
    assert "1 new / 1 ended / 1 changed" in html
    # Creative text and page names are escaped, never injected raw.
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_report_is_single_file_without_external_assets(tmp_path):
    ads = {"1": _ad(1)}
    paths = report.write_report("nike", {"new": [ads["1"]], "ended": [], "changed": []}, ads, META, tmp_path)
    html = Path(paths["html"]).read_text()

    assert '<script src' not in html
    assert '<link' not in html
    assert 'src="http' not in html
    assert "@import" not in html
    assert "<style>" in html
    # The library link is a plain anchor, which is allowed.
    assert '<a href="https://www.facebook.com/ads/library/?id=1"' in html
    # One file only: nothing else in the output dir besides the digest.
    files = sorted(p.name for p in Path(tmp_path).rglob("*") if p.is_file())
    assert len(files) == 2


def test_report_drops_non_https_library_url(tmp_path):
    """A javascript:/data: library_url must never become an anchor href."""
    ads = {"1": _ad(1, library_url="javascript:alert(document.cookie)")}
    paths = report.write_report("nike", {"new": [ads["1"]]}, ads, META, tmp_path)
    html = Path(paths["html"]).read_text()

    assert "javascript:" not in html
    assert "href=" not in html


def test_report_title_escapes_once():
    """An `&` in query/advertiser renders as `&amp;`, never `&amp;amp;`.

    The advertiser was escaped, folded into the title, then the whole title was
    escaped again, so "A&B" showed up in the page heading as "A&amp;amp;B".
    """
    ads = {"1": _ad(1, page_name="A&B")}
    document = report.build_html(
        "A&B",
        {"new": [ads["1"]], "ended": [], "changed": []},
        ads,
        META,
        advertiser="A&B",
    )

    assert "Ad check — A&amp;B (US · A&amp;B)" in document
    assert "A&amp;amp;B" not in document


def test_digest_counts_match_diff(tmp_path):
    ads = {str(i): _ad(i) for i in range(1, 8)}
    diff = {
        "new": [ads["6"], ads["7"]],
        "ended": [ads["1"]],
        "changed": [ads["3"], ads["4"], ads["5"]],
    }
    paths = report.write_report("nike", diff, ads, {**META, "partial": True}, tmp_path)
    digest = json.loads(Path(paths["digest"]).read_text())

    assert digest["new"] == len(diff["new"]) == 2
    assert digest["ended"] == len(diff["ended"]) == 1
    assert digest["changed"] == len(diff["changed"]) == 3
    assert digest["total"] == len(ads) == 7
    assert digest["partial"] is True
    assert digest["checked_at"] == META["checked_at"]
    assert digest["query"] == "nike"


def test_card_shows_cta_link_creative_count_versions_and_images(tmp_path):
    """Task-1 fields render as text/metadata, never as external assets."""
    ad = _ad(
        1,
        cta_text="Shop Now",
        link_url="https://www.nike.com/sale?x=1&y=2",
        link_title="Nike Sale",
        same_creative_count=42,
        multiple_versions=True,
        images=["https://scontent.example/a.jpg", "https://scontent.example/b.jpg"],
    )
    paths = report.write_report("nike", {"new": [ad]}, {"1": ad}, META, tmp_path)
    html = Path(paths["html"]).read_text()

    assert (
        '<a href="https://www.nike.com/sale?x=1&amp;y=2" target="_blank" '
        'rel="noopener noreferrer"' in html
    )
    assert ">Shop Now</a>" in html
    assert "Nike Sale" in html
    assert "42 use this creative" in html
    assert "Multiple versions" in html
    assert "2 images" in html
    # Offline-safe: no image elements, no external subresources.
    assert "<img" not in html.lower()
    assert 'src="http' not in html


def test_card_keeps_non_http_destination_inert(tmp_path):
    """A javascript:/data:/relative link_url must stay text, not an href."""
    ads = {
        "1": _ad(1, cta_text="Click me", link_url="javascript:alert(1)"),
        "2": _ad(2, cta_text="Relative", link_url="/account/settings"),
        "3": _ad(3, cta_text="Data", link_url="data:text/html;base64,PHNjcmlwdD4="),
    }
    paths = report.write_report("nike", {"new": list(ads.values())}, ads, META, tmp_path)
    html = Path(paths["html"]).read_text()

    assert "javascript:" not in html
    assert "data:text/html" not in html
    assert 'href="javascript' not in html
    assert 'href="data:' not in html
    assert 'href="/account' not in html
    # CTA copy still shows, just inert.
    for text in ("Click me", "Relative", "Data"):
        assert text in html


def test_card_escapes_xss_in_cta_and_link_title(tmp_path):
    ad = _ad(
        1,
        cta_text='<img src=x onerror="alert(1)">Buy',
        link_url="https://evil.example/x",
        link_title='"><script>alert(2)</script>',
        same_creative_count=1,
    )
    paths = report.write_report("nike", {"new": [ad]}, {"1": ad}, META, tmp_path)
    html = Path(paths["html"]).read_text()

    assert "<img src=x" not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;Buy" in html
    assert "&quot;&gt;&lt;script&gt;" in html


def test_digest_enrichment_counts(tmp_path):
    ads = {
        "1": _ad(
            1,
            cta_text="Shop",
            link_url="https://ok.example/a",
            images=["https://img.example/a.jpg"],
            same_creative_count=3,
            multiple_versions=True,
        ),
        "2": _ad(2, cta_text="Bad", link_url="javascript:alert(1)", same_creative_count=0),
        "3": _ad(3, images=["https://img.example/b.jpg"], multiple_versions=True),
        "4": _ad(4),
    }
    paths = report.write_report("nike", {"new": [ads["1"]]}, ads, META, tmp_path)
    digest = json.loads(Path(paths["digest"]).read_text())

    assert digest["with_link"] == 1
    assert digest["with_cta"] == 2
    assert digest["with_images"] == 2
    assert digest["with_same_creative"] == 1
    assert digest["with_multiple_versions"] == 2
    assert digest["total"] == 4


def test_report_paths_differ_by_country(tmp_path, monkeypatch):
    """The same query in two markets must never share report artifacts."""
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)

    us = store.report_paths("KFC", "US")
    ae = store.report_paths("KFC", "AE")

    assert us["html"] != ae["html"]
    assert us["digest"] != ae["digest"]
    assert str(us["html"]).endswith(".html")
    assert str(ae["html"]).endswith(".html")
    # Country is part of the key exactly like the snapshot filename.
    assert us["html"].parent == tmp_path / "reports"
    assert us["html"].name == store._snapshot_path("KFC", "US").stem + ".html"


def test_report_paths_differ_by_page_identity(tmp_path, monkeypatch):
    """A page watch and a keyword watch must not share artifacts."""
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)

    keyword = store.report_paths("KFC", "GB")
    page = store.report_paths("KFC", "GB", page_id="209644529058679")

    assert keyword["html"] != page["html"]
    assert keyword["digest"] != page["digest"]


def test_write_report_accepts_page_id_and_keys_its_artifacts(tmp_path, monkeypatch):
    """`write_report` must accept what the check forwards, and honour it.

    The page-watch branch forwards the watch's page_id; a signature without
    that keyword turned every page-watch artifacts row into an error and
    wrote no HTML or digest.
    """
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    ad = _ad(1)
    diff = {"new": [ad], "ended": [], "changed": []}

    keyword = report.write_report("kfc", diff, {"1": ad}, META, country="GB")
    page = report.write_report(
        "kfc", diff, {"1": ad}, META, country="GB", page_id="209644529058679"
    )

    assert page["html"] != keyword["html"]
    expected = store.report_paths("kfc", "GB", page_id="209644529058679")
    assert page["html"] == str(expected["html"])
    assert page["digest"] == str(expected["digest"])
    assert 'data-ad-id="1"' in Path(page["html"]).read_text()
    assert json.loads(Path(page["digest"]).read_text())["total"] == 1


def test_build_html_skips_non_dict_ads_by_id(tmp_path):
    """A junk value in ads_by_id must not crash the card renderer."""
    ads = {"1": _ad(1), "2": "not-an-ad", "3": None, "4": ["list"]}
    paths = report.write_report(
        "nike", {"new": [ads["1"]], "ended": [], "changed": []}, ads, META, tmp_path
    )
    html = Path(paths["html"]).read_text()
    digest = json.loads(Path(paths["digest"]).read_text())

    assert 'data-ad-id="1"' in html
    # Only dicts are ads; junk entries are neither cards nor counted.
    assert html.count('class="card"') == 1
    assert digest["total"] == 1


def test_build_html_skips_non_dict_entries_in_diff_buckets(tmp_path):
    """Non-dict entries inside diff buckets are ignored, not rendered."""
    ad = _ad(1)
    diff = {
        "new": [ad, "junk", None, 7],
        "changed": [{"id": "2"}, {}],
        "ended": [42],
    }
    paths = report.write_report("nike", diff, {"1": ad}, META, tmp_path)
    html = Path(paths["html"]).read_text()

    assert 'data-ad-id="1"' in html
    assert 'data-ad-id="2"' in html
    # {"id": "2"} is a dict and still renders; its data-ad-id is present.
    assert html.count('class="card"') <= 2


def test_build_html_coerces_mismatched_bucket_types(tmp_path):
    """A bucket that is not a list (dict/str/int/None) must not crash counts."""
    ad = _ad(1)
    diff = {"new": "not-a-list", "changed": {"id": "1"}, "ended": 5}
    document = report.build_html("nike", diff, {"1": ad}, META)

    assert "0 new / 0 ended / 0 changed" in document
    assert 'data-ad-id="1"' in document
    # A non-dict ads_by_id container degrades to "no ads" instead of raising.
    empty = report.build_html("nike", {}, ["not-a-mapping"], META)  # type: ignore[arg-type]
    assert "No ads in this check." in empty
    assert "0 ads tracked" in empty


@pytest.mark.parametrize("bad", [None, [], "str", 5])
@pytest.mark.parametrize("bad_meta", [None, [], "meta"])
def test_build_html_and_digest_tolerate_non_mapping_payloads(bad, bad_meta):
    """The public builder API degrades junk to empty, never AttributeError.

    ``write_report`` normalises, but ``build_html``/``build_digest`` are called
    directly by embedders; a None/list/str diff or metadata object is a no-op,
    not a crash.
    """
    ad = _ad(1)
    document = report.build_html("nike", bad, {"1": ad}, bad_meta)
    digest = report.build_digest("nike", bad, {"1": ad}, bad_meta)

    assert "0 new / 0 ended / 0 changed" in document
    assert 'data-ad-id="1"' in document
    assert digest["new"] == digest["ended"] == digest["changed"] == 0
    assert digest["total"] == 1
    assert digest["checked_at"] is None
    assert digest["partial"] is False


def test_same_creative_count_clamps_numeric_extremes(tmp_path):
    """inf/1e999 and 5000-digit counts render a safe int, never crash.

    JSON ``1e999`` decodes to ``inf`` (whose ``int()`` raises OverflowError),
    and a hand-edited snapshot can carry ``10**5000``; both must stay printable.
    """
    assert report._same_creative_count({"same_creative_count": float("inf")}) == 0
    assert report._same_creative_count({"same_creative_count": 1e999}) == 0
    assert report._same_creative_count({"same_creative_count": "1e999"}) == 0
    assert report._same_creative_count({"same_creative_count": "junk"}) == 0
    assert report._same_creative_count({"same_creative_count": -4}) == 0
    assert report._same_creative_count({"same_creative_count": 10**5000}) == report._MAX_SAME_CREATIVE

    ad = _ad(1, same_creative_count=10**5000)
    html = report.build_html("nike", {"new": [ad]}, {"1": ad}, META)
    assert f"{report._MAX_SAME_CREATIVE} use this creative" in html
    assert len(html) < 200_000  # no 5000-digit badge
