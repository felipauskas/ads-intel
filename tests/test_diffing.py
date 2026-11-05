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
