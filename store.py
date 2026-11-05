"""Watchlist + snapshot persistence under the plugin data dir."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

try:
    from plugins.plugin_storage import plugin_data_dir

    def _data_dir() -> Path:
        return Path(plugin_data_dir("ads-intel"))

except ImportError:

    def _data_dir() -> Path:
        return Path.home() / ".ads-intel-dev"


WATCH = "watchlist.json"


def _watch_path() -> Path:
    return _data_dir() / WATCH


def _write_json(path: Path, payload) -> None:
    """Write JSON atomically: temp file in the same dir, fsync, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _norm(query) -> str:
    return str(query or "").strip()


def watch_list() -> list[str]:
    path = _watch_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [q for q in (_norm(x) for x in data) if q]


def watch_add(query: str) -> list[str]:
    q = _norm(query)
    items = watch_list()
    if q and q not in items:
        items.append(q)
        _write_json(_watch_path(), items)
    return items


def watch_remove(query: str) -> list[str]:
    q = _norm(query)
    items = watch_list()
    if q not in items:
        return items
    items = [x for x in items if x != q]
    _write_json(_watch_path(), items)
    return items


def _snapshot_path(query: str) -> Path:
    """Stable, collision-free, length-bounded filename for a query."""
    digest = hashlib.sha1(_norm(query).encode("utf-8")).hexdigest()[:16]
    return _data_dir() / "snapshots" / f"{digest}.json"


def save_snapshot(query: str, snap: dict) -> None:
    payload = dict(snap or {})
    payload["query"] = _norm(query)
    payload.setdefault("ads", {})
    _write_json(_snapshot_path(query), payload)


def load_snapshot(query: str) -> dict:
    path = _snapshot_path(query)
    if not path.exists():
        return {"ads": {}}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"ads": {}}
    if not isinstance(data, dict):
        return {"ads": {}}
    # ``query`` is file metadata; keep the public payload shape stable and
    # tolerate payloads written before it existed.
    data.pop("query", None)
    return data
