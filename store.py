"""Watchlist + snapshot persistence under the plugin data dir."""

import json
import os
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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


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
    items = [x for x in watch_list() if x != q]
    _write_json(_watch_path(), items)
    return items


def _snapshot_path(query: str) -> Path:
    safe = _norm(query).replace("/", "_")
    return _data_dir() / "snapshots" / f"{safe}.json"


def save_snapshot(query: str, snap: dict) -> None:
    _write_json(_snapshot_path(query), snap)


def load_snapshot(query: str) -> dict:
    path = _snapshot_path(query)
    if not path.exists():
        return {"ads": {}}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"ads": {}}
    return data if isinstance(data, dict) else {"ads": {}}
