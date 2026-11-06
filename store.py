"""Watchlist + snapshot persistence under the plugin data dir."""

import hashlib
import json
import os
import re
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

DEFAULT_COUNTRY = "US"
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


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


def _norm_country(country) -> str:
    """Normalise a market code; anything unusable falls back to US."""
    code = str(country or "").strip().upper()
    return code if _COUNTRY_RE.match(code) else DEFAULT_COUNTRY


def _entry(item) -> dict | None:
    """One watch entry as ``{query, country}``; legacy strings migrate to US."""
    if isinstance(item, str):
        query = _norm(item)
        return {"query": query, "country": DEFAULT_COUNTRY} if query else None
    if isinstance(item, dict):
        query = _norm(item.get("query"))
        if not query:
            return None
        return {"query": query, "country": _norm_country(item.get("country"))}
    return None


def watch_list() -> list[dict]:
    path = _watch_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in (_entry(x) for x in data) if e]


def watch_add(query: str, country: str = DEFAULT_COUNTRY) -> list[dict]:
    entry = _entry({"query": query, "country": country})
    if entry is None:
        return watch_list()
    items = watch_list()
    if entry not in items:
        items.append(entry)
        _write_json(_watch_path(), items)
    return items


def watch_remove(query: str) -> list[dict]:
    """Remove every entry for ``query``, regardless of country."""
    q = _norm(query)
    items = watch_list()
    kept = [x for x in items if x["query"] != q]
    if kept == items:
        return items
    _write_json(_watch_path(), kept)
    return kept


def _legacy_snapshot_path(query: str) -> Path:
    """Pre-country snapshot filename, kept for US upgrades."""
    digest = hashlib.sha1(_norm(query).encode("utf-8")).hexdigest()[:16]
    return _data_dir() / "snapshots" / f"{digest}.json"


def _snapshot_path(query: str, country: str = DEFAULT_COUNTRY) -> Path:
    """Stable, collision-free, length-bounded filename for query + market."""
    key = f"{_norm(query)}\x00{_norm_country(country)}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return _data_dir() / "snapshots" / f"{digest}.json"


def _write_text(path: Path, data: str) -> None:
    """Write UTF-8 text atomically: temp file in the same dir, fsync, replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
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


def report_paths(query: str, country: str = DEFAULT_COUNTRY) -> dict:
    """Where the HTML report and its digest live for query + market.

    The filename hashes ``query\\x00country`` exactly like the snapshot key:
    the same query watched in two markets must never share an artifact.
    """
    key = f"{_norm(query)}\x00{_norm_country(country)}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    base = _data_dir() / "reports"
    return {
        "html": base / f"{digest}.html",
        "digest": base / f"{digest}.digest.json",
    }


def save_snapshot(query: str, snap: dict, country: str = DEFAULT_COUNTRY) -> None:
    payload = dict(snap or {})
    payload["query"] = _norm(query)
    payload.setdefault("ads", {})
    _write_json(_snapshot_path(query, country), payload)


def load_snapshot(query: str, country: str = DEFAULT_COUNTRY) -> dict:
    """Load the snapshot for query + market.

    Snapshots written before the country parameter lived under a hash of the
    query alone; for US those are still read so an upgrade does not lose a
    baseline.
    """
    path = _snapshot_path(query, country)
    if not path.exists() and _norm_country(country) == DEFAULT_COUNTRY:
        path = _legacy_snapshot_path(query)
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
