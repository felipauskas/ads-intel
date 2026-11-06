import json
from pathlib import Path

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
