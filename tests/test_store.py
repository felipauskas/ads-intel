import json

import pytest

import store


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    return tmp_path


def test_watchlist_migrates_legacy_strings(data_dir):
    (data_dir / store.WATCH).write_text(json.dumps(["KFC"]))
    assert store.watch_list() == [{"query": "KFC", "country": "US"}]
    # Card view stays compatible: remove by query still works on legacy data.
    assert store.watch_remove("KFC") == []


def test_watchlist_roundtrip():
    assert store.watch_add("nike") == [{"query": "nike", "country": "US"}]
    assert store.watch_add("nike") == [{"query": "nike", "country": "US"}]
    assert store.watch_add("allbirds") == [
        {"query": "nike", "country": "US"},
        {"query": "allbirds", "country": "US"},
    ]
    assert store.watch_remove("nike") == [{"query": "allbirds", "country": "US"}]
    assert store.watch_list() == [{"query": "allbirds", "country": "US"}]


def test_watchlist_is_file_backed(data_dir):
    store.watch_add("nike")
    on_disk = json.loads((data_dir / store.WATCH).read_text())
    assert on_disk == [{"query": "nike", "country": "US"}]


def test_snapshot_roundtrip(data_dir):
    snap = {"ads": {"1": {"id": "1", "status": "active"}}}
    store.save_snapshot("nike", snap)
    assert store.load_snapshot("nike") == snap
    assert store.load_snapshot("never") == {"ads": {}}
    files = list((data_dir / "snapshots").glob("*.json"))
    assert len(files) == 1
    # The query is kept inside the payload for debugging.
    assert json.loads(files[0].read_text())["query"] == "nike"


def test_snapshot_filenames_are_hashed_and_collision_free(tmp_path):
    store.save_snapshot("nike/air", {"ads": {}})
    store.save_snapshot("nike_air", {"ads": {}})
    files = sorted((tmp_path / "snapshots").glob("*.json"))
    assert len(files) == 2
    assert store.load_snapshot("nike/air") == {"ads": {}}
    assert store.load_snapshot("nike_air") == {"ads": {}}


def test_snapshot_long_query_roundtrips(tmp_path):
    query = "n" * 300
    assert len(query) == 300
    snap = {"ads": {"1": {"id": "1"}}}
    store.save_snapshot(query, snap)
    assert store.load_snapshot(query) == snap
    names = [p.name for p in (tmp_path / "snapshots").glob("*.json")]
    assert len(names) == 1
    assert len(names[0]) <= 21  # 16 hex chars + ".json"


def test_consecutive_saves_both_load(tmp_path):
    store.save_snapshot("nike", {"ads": {"1": {"id": "1"}}})
    store.save_snapshot("nike", {"ads": {"2": {"id": "2"}}})
    assert store.load_snapshot("nike") == {"ads": {"2": {"id": "2"}}}


def test_watch_remove_absent_does_not_rewrite(monkeypatch):
    store.watch_add("nike")
    writes = []
    real = store._write_json
    monkeypatch.setattr(
        store, "_write_json", lambda p, d: (writes.append(p), real(p, d))[1]
    )
    assert store.watch_remove("absent") == [{"query": "nike", "country": "US"}]
    assert writes == []
