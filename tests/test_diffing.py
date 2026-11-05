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
