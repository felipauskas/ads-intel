import json

import pytest

import store


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    return tmp_path


def test_watchlist_roundtrip():
    assert store.watch_add("nike") == ["nike"]
    assert store.watch_add("nike") == ["nike"]
    assert store.watch_add("allbirds") == ["nike", "allbirds"]
    assert store.watch_remove("nike") == ["allbirds"]
    assert store.watch_list() == ["allbirds"]


def test_watchlist_is_file_backed(data_dir):
    store.watch_add("nike")
    on_disk = json.loads((data_dir / store.WATCH).read_text())
    assert on_disk == ["nike"]


def test_snapshot_roundtrip(data_dir):
    snap = {"ads": {"1": {"id": "1", "status": "active"}}}
    store.save_snapshot("nike", snap)
    assert store.load_snapshot("nike") == snap
    assert store.load_snapshot("never") == {"ads": {}}
    assert (data_dir / "snapshots" / "nike.json").exists()


def test_snapshot_query_with_slash(tmp_path):
    store.save_snapshot("nike/air", {"ads": {}})
    assert (tmp_path / "snapshots" / "nike_air.json").exists()
    assert store.load_snapshot("nike/air") == {"ads": {}}
