import hashlib
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


def test_legacy_snapshot_fallback_us_only(data_dir):
    """Pre-country files (sha1 of the query alone) are read for US only."""
    query = "KFC"
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
    legacy = data_dir / "snapshots" / f"{digest}.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"query": query, "ads": {"1": {"id": "1"}}}))

    assert store.load_snapshot(query, "US") == {"ads": {"1": {"id": "1"}}}
    assert store.load_snapshot(query, "AE") == {"ads": {}}


def test_snapshot_paths_differ_by_advertiser(tmp_path):
    """An advertiser-filtered watch must never share an unfiltered one's file."""
    plain = store._snapshot_path("KFC", "US")
    kfc = store._snapshot_path("KFC", "US", "KFC")
    assert plain != kfc
    assert store._snapshot_path("KFC", "US", "KFC") == kfc
    assert store.report_paths("KFC", "US")["html"] != store.report_paths(
        "KFC", "US", "KFC"
    )["html"]
    # The unfiltered key is unchanged, so existing baselines stay readable.
    assert plain.name == hashlib.sha1("KFC\x00US".encode("utf-8")).hexdigest()[:16] + ".json"


def test_advertiser_snapshot_falls_back_to_legacy_unstamped_baseline(data_dir):
    """Adding an advertiser to a pre-fix watch keeps reading its baseline."""
    snap = {"ads": {"1": {"id": "1"}}}
    legacy = store._snapshot_path("KFC", "US")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"query": "KFC", **snap}))
    assert store.load_snapshot("KFC", "US", "KFC") == snap

    # But a baseline written now by the unfiltered watch is stamped, and the
    # filtered watch must not adopt it.
    store.save_snapshot("KFC", {"ads": {"2": {"id": "2"}}}, "US")
    assert store.load_snapshot("KFC", "US", "KFC") == {"ads": {}}


def test_watch_remove_absent_does_not_rewrite(monkeypatch):
    store.watch_add("nike")
    writes = []
    real = store._write_json
    monkeypatch.setattr(
        store, "_write_json", lambda p, d: (writes.append(p), real(p, d))[1]
    )
    assert store.watch_remove("absent") == [{"query": "nike", "country": "US"}]
    assert writes == []

def test_watch_add_persists_filters_and_dedupes():
    items = store.watch_add(
        "nike", active_status="active", media_type="image"
    )
    assert items == [
        {
            "query": "nike",
            "country": "US",
            "active_status": "active",
            "media_type": "image",
        }
    ]
    # Same filters: no duplicate. Different filters: a separate watch.
    assert store.watch_add("nike", active_status="active", media_type="image") == items
    items = store.watch_add("nike")
    assert items == [
        {
            "query": "nike",
            "country": "US",
            "active_status": "active",
            "media_type": "image",
        },
        {"query": "nike", "country": "US"},
    ]


def test_snapshot_and_report_keys_differ_by_filters():
    plain = store._snapshot_path("KFC", "US")
    filtered = store._snapshot_path("KFC", "US", None, "active", "video")
    assert plain != filtered
    # The default key is unchanged, so existing baselines stay readable.
    assert plain.name == (
        hashlib.sha1("KFC\x00US".encode("utf-8")).hexdigest()[:16] + ".json"
    )
    assert store.report_paths("KFC", "US", None, "active")["html"] != (
        store.report_paths("KFC", "US")["html"]
    )


def test_filtered_watch_does_not_adopt_unfiltered_baseline(data_dir):
    store.save_snapshot("KFC", {"ads": {"1": {"id": "1"}}}, "US")
    # A pre-country legacy file (sha1 of the query alone) has no filter stamps,
    # so the load guard cannot reject it: the path itself must not be offered
    # to a filtered watch.
    digest = hashlib.sha1("KFC".encode("utf-8")).hexdigest()[:16]
    legacy = data_dir / "snapshots" / f"{digest}.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"ads": {"9": {"id": "9"}}}))
    for filters in (
        ("active", "all"),
        ("all", "video"),
        ("inactive", "image"),
    ):
        assert store.load_snapshot("KFC", "US", None, *filters) == {"ads": {}}, filters
    # A plain US watch still upgrades from the legacy file when no newer
    # keyed baseline exists.
    old_digest = hashlib.sha1("OLD".encode("utf-8")).hexdigest()[:16]
    (data_dir / "snapshots" / f"{old_digest}.json").write_text(
        json.dumps({"ads": {"8": {"id": "8"}}})
    )
    assert store.load_snapshot("OLD", "US") == {"ads": {"8": {"id": "8"}}}
    # Its own baseline round-trips, with metadata kept out of the payload.
    store.save_snapshot(
        "KFC", {"ads": {"2": {"id": "2"}}}, "US", None, "active", "all"
    )
    assert store.load_snapshot("KFC", "US", None, "active", "all") == {
        "ads": {"2": {"id": "2"}}
    }
