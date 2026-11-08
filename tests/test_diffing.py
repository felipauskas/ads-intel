import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from diffing import diff_snapshots

OLD = {"ads": {"A1": {"id": "A1", "status": "active", "creative_text": "buy shoes"},
               "A2": {"id": "A2", "status": "active", "creative_text": "old copy"}}}
NEW = {"ads": {"A1": {"id": "A1", "status": "ended", "creative_text": "buy shoes"},
               "A2": {"id": "A2", "status": "active", "creative_text": "new copy"},
               "A3": {"id": "A3", "status": "active", "creative_text": "hello"}}}


def test_diff_classifies_all_changes():
    d = diff_snapshots(OLD, NEW)
    assert [a["id"] for a in d["new"]] == ["A3"]
    assert [a["id"] for a in d["ended"]] == ["A1"]
    assert [a["id"] for a in d["changed"]] == ["A2"]


def test_diff_empty_old_is_all_new():
    d = diff_snapshots({"ads": {}}, NEW)
    assert len(d["new"]) == 3 and not d["ended"] and not d["changed"]


def test_diff_no_changes():
    d = diff_snapshots(NEW, NEW)
    assert d == {"new": [], "ended": [], "changed": []}


def test_diff_revived_ad_is_new_not_changed():
    """An ad flipping ended -> active is `new`, never `changed`; a status that
    differs only by case/whitespace is not a change at all."""
    old = {"ads": {"R1": {"id": "R1", "status": "ended", "creative_text": "back again"},
                   "Q1": {"id": "Q1", "status": "active", "creative_text": "steady"}}}
    new = {"ads": {"R1": {"id": "R1", "status": "active", "creative_text": "back again"},
                   "Q1": {"id": "Q1", "status": "Active ", "creative_text": "steady"}}}
    d = diff_snapshots(old, new)
    assert [a["id"] for a in d["new"]] == ["R1"]
    assert d["changed"] == []
    assert d["ended"] == []


def test_diff_all_ads_ended():
    """Every ad present in old and absent from new is reported as ended."""
    d = diff_snapshots(OLD, {"ads": {}})
    assert sorted(a["id"] for a in d["ended"]) == ["A1", "A2"]
    assert d["new"] == [] and d["changed"] == []

def test_diff_detects_destination_and_cta_changes():
    old = {"ads": {"D1": {"id": "D1", "status": "active", "creative_text": "x",
                          "link_url": "https://a.example/", "link_title": "A",
                          "cta_text": "Shop Now"}}}
    for key, value in (
        ("link_url", "https://b.example/"),
        ("link_title", "B"),
        ("cta_text", "Learn More"),
    ):
        new = {"ads": {"D1": {**old["ads"]["D1"], key: value}}}
        d = diff_snapshots(old, new)
        assert [a["id"] for a in d["changed"]] == ["D1"], key
        assert d["new"] == [] and d["ended"] == []


def test_diff_ignores_fields_absent_from_old_snapshot():
    """Enriched fields added after a baseline was written must not make every
    ad look changed on the first run after the upgrade."""
    old = {"ads": {"L1": {"id": "L1", "status": "active", "creative_text": "x"}}}
    new = {"ads": {"L1": {"id": "L1", "status": "active", "creative_text": "x",
                          "link_url": "https://a.example/", "link_title": "A",
                          "cta_text": "Shop Now"}}}
    assert diff_snapshots(old, new) == {"new": [], "ended": [], "changed": []}


def test_diff_compares_enriched_fields_when_both_sides_have_them():
    old = {"ads": {"E1": {"id": "E1", "status": "active", "creative_text": "x",
                          "link_url": "", "link_title": "", "cta_text": ""}}}
    new = {"ads": {"E1": {"id": "E1", "status": "active", "creative_text": "x",
                          "link_url": "", "link_title": "", "cta_text": ""}}}
    assert diff_snapshots(old, new)["changed"] == []


def test_diff_tolerates_malformed_snapshot_payloads():
    """A corrupt snapshot (None, or {"ads": "notadict"}) is empty, not a crash.

    On-disk JSON is hand-editable; a bad ``ads`` value must degrade to "no ads"
    so the check still runs instead of being lost to AttributeError.
    """
    assert diff_snapshots(None, {"ads": {}}) == {"new": [], "ended": [], "changed": []}
    assert diff_snapshots({"ads": "notadict"}, {"ads": {}}) == {
        "new": [], "ended": [], "changed": []
    }
    assert diff_snapshots([], {"ads": {}}) == {"new": [], "ended": [], "changed": []}
    # A corrupt *new* side means every old id is absent: the same "all ended"
    # result an explicit empty listing gives.
    d = diff_snapshots(OLD, {"ads": "notadict"})
    assert sorted(a["id"] for a in d["ended"]) == ["A1", "A2"]
    assert d["new"] == [] and d["changed"] == []


def test_diff_skips_non_dict_ad_values():
    """Junk values inside an otherwise valid ads map are ignored, not compared."""
    old = {"ads": {"A1": {"id": "A1", "status": "active"},
                   "J": "not-an-ad", "N": None}}
    new = {"ads": {"A1": {"id": "A1", "status": "active"},
                   "J2": ["junk"]}}
    assert diff_snapshots(old, new) == {"new": [], "ended": [], "changed": []}
