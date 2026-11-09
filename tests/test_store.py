import hashlib
import json
import threading
import time

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


def test_advertiser_watch_does_not_adopt_unstamped_unfiltered_baseline(data_dir):
    """An advertiser watch must never diff against an unfiltered baseline.

    The 24 non-brand ads in that baseline would be reported as `ended` on the
    first advertiser-filtered run. The old leniency was a documented upgrade
    exception; it contradicts the blanket "filtered watches never adopt
    unfiltered baselines" rule.
    """
    snap = {"ads": {"1": {"id": "1"}}}
    legacy = store._snapshot_path("KFC", "US")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"query": "KFC", **snap}))
    assert store.load_snapshot("KFC", "US", "KFC") == {"ads": {}}

    # The unfiltered watch itself still reads its own baseline.
    assert store.load_snapshot("KFC", "US") == snap


def test_advertiser_watch_does_not_adopt_pre_country_legacy_baseline(data_dir):
    """The sha1(query) fallback is unfiltered too, so an advertiser watch skips it."""
    digest = hashlib.sha1("KFC".encode("utf-8")).hexdigest()[:16]
    legacy = data_dir / "snapshots" / f"{digest}.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"ads": {"9": {"id": "9"}}}))

    assert store.load_snapshot("KFC", "US", "KFC") == {"ads": {}}
    # The same file is still the upgrade path for the unfiltered US watch.
    assert store.load_snapshot("KFC", "US") == {"ads": {"9": {"id": "9"}}}



def test_artifact_key_rejects_nul_in_query_and_advertiser():
    """NUL is the field separator; a component carrying one must be refused.

    Pre-fix, `advertiser="b\\x00active_status=active"` hashed exactly like
    advertiser "b" watched with the active filter, so two watches shared one
    snapshot/report.
    """
    with pytest.raises(ValueError):
        store._artifact_key("KFC\x00US", "US")
    with pytest.raises(ValueError):
        store._artifact_key("KFC", "US", "b\x00active_status=active")
    with pytest.raises(ValueError):
        store._snapshot_path("KFC", "US", "b\x00active_status=active")
    with pytest.raises(ValueError):
        store.report_paths("KFC", "US", "b\x00active_status=active")

    # The legitimate keys those NUL strings used to alias remain distinct.
    assert store._snapshot_path("KFC", "US", "b") != store._snapshot_path("KFC", "US")
    assert (
        store._snapshot_path("KFC", "US", "b", "active")
        != store._snapshot_path("KFC", "US", "b")
    )


def test_advertisers_differing_only_by_nul_never_collide():
    """Neither variant gets hashed, so neither can alias the other."""
    for adv in ("a\x00b", "\x00ab"):
        with pytest.raises(ValueError):
            store._snapshot_path("KFC", "US", adv)


def test_watch_add_drops_nul_advertiser_entry():
    items = store.watch_add("KFC", advertiser="KFC\x00US")
    assert items == []


# --- branch coverage: atomic-write cleanup and corrupt reads -----------------


def test_write_json_cleans_temp_file_when_replace_fails(monkeypatch, data_dir):
    """A failed write must not leave a half-written temp file behind."""
    target = data_dir / "out.json"

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        store._write_json(target, {"a": 1})
    assert not target.exists()
    assert list(data_dir.glob("*.tmp")) == []


def test_write_text_cleans_temp_file_when_replace_fails(monkeypatch, data_dir):
    target = data_dir / "out.txt"

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        store._write_text(target, "data")
    assert not target.exists()
    assert list(data_dir.glob("*.tmp")) == []


def test_write_json_survives_unlink_failure_while_cleaning_up(monkeypatch, data_dir):
    """If the temp file cannot be unlinked, the original error still wins."""
    target = data_dir / "out.json"
    unlinked = []

    def boom(src, dst):
        raise OSError("disk full")

    def no_unlink(path):
        unlinked.append(path)
        raise OSError("busy")

    monkeypatch.setattr(store.os, "replace", boom)
    monkeypatch.setattr(store.os, "unlink", no_unlink)
    with pytest.raises(OSError, match="disk full"):
        store._write_json(target, {"a": 1})
    assert len(unlinked) == 1


def test_write_text_survives_unlink_failure_while_cleaning_up(monkeypatch, data_dir):
    target = data_dir / "out.txt"
    unlinked = []

    def boom(src, dst):
        raise OSError("disk full")

    def no_unlink(path):
        unlinked.append(path)
        raise OSError("busy")

    monkeypatch.setattr(store.os, "replace", boom)
    monkeypatch.setattr(store.os, "unlink", no_unlink)
    with pytest.raises(OSError, match="disk full"):
        store._write_text(target, "data")
    assert len(unlinked) == 1


def test_watch_list_tolerates_corrupt_json(data_dir):
    (data_dir / store.WATCH).write_text("{not json")
    assert store.watch_list() == []


def test_watch_list_tolerates_non_list_json(data_dir):
    (data_dir / store.WATCH).write_text(json.dumps({"query": "nike"}))
    assert store.watch_list() == []


def test_watch_list_drops_unusable_entries(data_dir):
    """Junk entries are skipped, not carried into the persisted list."""
    (data_dir / store.WATCH).write_text(
        json.dumps(
            [
                123,
                None,
                "   ",
                "bad\x00query",
                {"query": "  "},
                {"query": "ok", "advertiser": "a\x00b"},
                "good",
            ]
        )
    )
    assert store.watch_list() == [{"query": "good", "country": "US"}]


def test_load_snapshot_tolerates_corrupt_json(data_dir):
    path = store._snapshot_path("KFC", "US")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert store.load_snapshot("KFC") == {"ads": {}}


def test_load_snapshot_tolerates_non_object_json(data_dir):
    path = store._snapshot_path("KFC", "US")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{"id": "1"}]))
    assert store.load_snapshot("KFC") == {"ads": {}}


def test_load_snapshot_skips_stamped_legacy_fallback(data_dir):
    """A fallback file stamped with metadata belongs to another watch."""
    legacy = store._legacy_snapshot_path("KFC")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"advertiser": "KFC", "ads": {"1": {"id": "1"}}}))
    assert store.load_snapshot("KFC") == {"ads": {}}


# --- concurrency: watchlist / snapshot read-modify-write (F6) ---------------


def _slow_writes(monkeypatch, seconds: float = 0.02):
    """Widen the read-modify-write window like the audit's 50 ms delay.

    The sleep sits inside the write call, i.e. between the read and the
    replace, which is exactly where an unguarded writer loses its peer's
    update.  It runs while the lock is held, so a correct implementation
    serialises and the delay only costs wall-clock time.
    """
    real = store._write_json

    def slow(path, payload):
        time.sleep(seconds)
        real(path, payload)

    monkeypatch.setattr(store, "_write_json", slow)


def test_concurrent_watch_add_keeps_every_entry(data_dir, monkeypatch):
    """Ten racing watch_add calls must all land; last-writer-wins is the bug."""
    count = 10
    _slow_writes(monkeypatch)
    barrier = threading.Barrier(count)
    errors: list[str] = []

    def worker(n: int) -> None:
        try:
            barrier.wait()
            store.watch_add(f"brand-{n}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{n}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert [t.name for t in threads if t.is_alive()] == []
    queries = {e["query"] for e in store.watch_list()}
    assert queries == {f"brand-{n}" for n in range(count)}


def test_concurrent_watch_remove_and_add_never_lose_entries(data_dir, monkeypatch):
    """Remove must not resurrect entries read before another thread's add."""
    _slow_writes(monkeypatch, 0.01)
    store.watch_add("keep")
    store.watch_add("drop")
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def remover() -> None:
        try:
            barrier.wait()
            store.watch_remove("drop")
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"remove: {type(exc).__name__}: {exc}")

    def adder() -> None:
        try:
            barrier.wait()
            store.watch_add("new")
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"add: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=remover), threading.Thread(target=adder)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    queries = {e["query"] for e in store.watch_list()}
    assert queries == {"keep", "new"}


def test_concurrent_snapshot_read_modify_write_accumulates(data_dir, monkeypatch):
    """The ad_check shape: load -> diff/merge -> save must be one critical section.

    Without the lock two overlapping checks both read the same prior, each
    writes prior+its own ad, and the later save erases the other's ad.
    """
    count = 10
    _slow_writes(monkeypatch, 0.01)
    barrier = threading.Barrier(count)
    errors: list[str] = []

    def worker(n: int) -> None:
        try:
            barrier.wait()
            with store.data_lock():
                ads = store.load_snapshot("shared").get("ads") or {}
                time.sleep(0.005)  # rendering/diff time inside the section
                ads[f"{n}"] = {"id": str(n)}
                store.save_snapshot("shared", {"ads": ads})
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{n}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert set(store.load_snapshot("shared")["ads"]) == {str(n) for n in range(count)}


def test_concurrent_saves_of_distinct_keys_all_roundtrip(data_dir, monkeypatch):
    """Parallel saves of different artifacts leave every file valid."""
    count = 10
    _slow_writes(monkeypatch, 0.005)
    barrier = threading.Barrier(count)

    def worker(n: int) -> None:
        barrier.wait()
        store.save_snapshot(f"q-{n}", {"ads": {str(n): {"id": str(n)}}})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    for n in range(count):
        assert store.load_snapshot(f"q-{n}")["ads"] == {str(n): {"id": str(n)}}


def test_data_lock_creates_a_lock_file_and_is_reentrant(data_dir):
    """The lock lives in the data dir, so separate processes contend on it."""
    with store.data_lock():
        with store.data_lock():
            store.watch_add("nested")
    assert (data_dir / ".lock").exists()
    assert store.watch_list() == [{"query": "nested", "country": "US"}]
