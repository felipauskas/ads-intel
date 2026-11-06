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

#: Filter defaults. Kept as literal tuples (not imported from sources) so the
#: persistence layer stays independent of the fetch layer.
DEFAULT_ACTIVE_STATUS = "all"
DEFAULT_MEDIA_TYPE = "all"
_ACTIVE_STATUSES = ("all", "active", "inactive")
_MEDIA_TYPES = ("all", "image", "video")


def _norm_filter(value, default: str, allowed: tuple[str, ...]) -> str:
    """Validate a stored/derived filter value; unusable means the default."""
    text = str(value or "").strip()
    return text if text in allowed else default


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
    """One watch entry as ``{query, country[, advertiser][, filters]}``.

    Legacy strings migrate to US; entries written before advertiser
    resolution existed simply have no ``advertiser`` key. Filters are stored
    only when they differ from the default, so an unfiltered watch keeps the
    exact shape (and snapshot key) it had before filters existed.
    """
    if isinstance(item, str):
        query = _norm(item)
        return {"query": query, "country": DEFAULT_COUNTRY} if query else None
    if isinstance(item, dict):
        query = _norm(item.get("query"))
        if not query:
            return None
        entry = {"query": query, "country": _norm_country(item.get("country"))}
        advertiser = _norm(item.get("advertiser"))
        if advertiser:
            entry["advertiser"] = advertiser
        active_status = _norm_filter(
            item.get("active_status"), DEFAULT_ACTIVE_STATUS, _ACTIVE_STATUSES
        )
        media_type = _norm_filter(
            item.get("media_type"), DEFAULT_MEDIA_TYPE, _MEDIA_TYPES
        )
        if active_status != DEFAULT_ACTIVE_STATUS:
            entry["active_status"] = active_status
        if media_type != DEFAULT_MEDIA_TYPE:
            entry["media_type"] = media_type
        return entry
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


def watch_add(
    query: str,
    country: str = DEFAULT_COUNTRY,
    advertiser: str | None = None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> list[dict]:
    entry = _entry(
        {
            "query": query,
            "country": country,
            "advertiser": advertiser,
            "active_status": active_status,
            "media_type": media_type,
        }
    )
    if entry is None:
        return watch_list()
    items = watch_list()
    if entry not in items:
        items.append(entry)
        _write_json(_watch_path(), items)
    return items


def watch_remove(query: str) -> list[dict]:
    """Remove every entry for ``query``, regardless of country or filters."""
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


def _artifact_key(
    query: str,
    country: str,
    advertiser: str | None = None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> str:
    """Key for query + market (+ advertiser, + filters).

    Without an advertiser or non-default filters the key is the pre-existing
    ``query\\x00country`` string, so every baseline written before
    advertiser- or filter-keyed watches keeps its filename. Each narrowed
    variant gets its own key: two watches for the same query, one filtered
    and one not, must never share a snapshot or report. Sharing one would
    make a filtered fetch look like the whole listing and report the ads it
    excludes as ended.
    """
    base = f"{_norm(query)}\x00{_norm_country(country)}"
    adv = _norm(advertiser)
    if adv:
        base = f"{base}\x00{adv}"
    active_status = _norm_filter(
        active_status, DEFAULT_ACTIVE_STATUS, _ACTIVE_STATUSES
    )
    media_type = _norm_filter(media_type, DEFAULT_MEDIA_TYPE, _MEDIA_TYPES)
    if active_status != DEFAULT_ACTIVE_STATUS:
        base = f"{base}\x00active_status={active_status}"
    if media_type != DEFAULT_MEDIA_TYPE:
        base = f"{base}\x00media_type={media_type}"
    return base


def _snapshot_path(
    query: str,
    country: str = DEFAULT_COUNTRY,
    advertiser: str | None = None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> Path:
    """Stable, collision-free, length-bounded filename for query + market."""
    digest = hashlib.sha1(
        _artifact_key(query, country, advertiser, active_status, media_type).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
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


def report_paths(
    query: str,
    country: str = DEFAULT_COUNTRY,
    advertiser: str | None = None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> dict:
    """Where the HTML report and its digest live for query + market.

    The filename hashes the same key as the snapshot: the same query watched
    in two markets, or once unfiltered and once for one advertiser, must never
    share an artifact.
    """
    digest = hashlib.sha1(
        _artifact_key(query, country, advertiser, active_status, media_type).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    base = _data_dir() / "reports"
    return {
        "html": base / f"{digest}.html",
        "digest": base / f"{digest}.digest.json",
    }


def save_snapshot(
    query: str,
    snap: dict,
    country: str = DEFAULT_COUNTRY,
    advertiser: str | None = None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> None:
    payload = dict(snap or {})
    payload["query"] = _norm(query)
    # Stamped on every write: a file written by an unfiltered watch is marked
    # advertiser "", so a filtered watch cannot mistake it for its own baseline.
    payload["advertiser"] = _norm(advertiser)
    # Filters are stamped only when non-default: an unfiltered payload keeps
    # the exact shape older versions wrote.
    active_status = _norm_filter(
        active_status, DEFAULT_ACTIVE_STATUS, _ACTIVE_STATUSES
    )
    media_type = _norm_filter(media_type, DEFAULT_MEDIA_TYPE, _MEDIA_TYPES)
    if active_status != DEFAULT_ACTIVE_STATUS:
        payload["active_status"] = active_status
    if media_type != DEFAULT_MEDIA_TYPE:
        payload["media_type"] = media_type
    payload.setdefault("ads", {})
    _write_json(
        _snapshot_path(query, country, advertiser, active_status, media_type),
        payload,
    )


def _read_snapshot_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _snapshot_candidates(
    query: str,
    country: str,
    advertiser: str | None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> list[Path]:
    """Paths to try, most specific first.

    * the advertiser-/filter-keyed file (when a target or filter is set)
    * the unfiltered ``query + country`` file, which is also the exact key for
      entries without an advertiser
    * the pre-country ``sha1(query)`` file, US only, and only for a watch with
      neither an advertiser nor a filter

    A watch with a non-default filter never falls back to the unfiltered file:
    that baseline holds ads the filter excludes, so endings computed against
    it would be wrong. It starts from an empty baseline instead. The same
    applies to the pre-country legacy file: it predates metadata stamps, so
    the load guard cannot tell it apart from an unfiltered baseline.
    """
    paths = [
        _snapshot_path(query, country, advertiser, active_status, media_type)
    ]
    filtered = (
        _norm_filter(active_status, DEFAULT_ACTIVE_STATUS, _ACTIVE_STATUSES)
        != DEFAULT_ACTIVE_STATUS
        or _norm_filter(media_type, DEFAULT_MEDIA_TYPE, _MEDIA_TYPES)
        != DEFAULT_MEDIA_TYPE
    )
    if not filtered:
        unfiltered = _snapshot_path(query, country)
        if unfiltered not in paths:
            paths.append(unfiltered)
    if not filtered and not _norm(advertiser) and (
        _norm_country(country) == DEFAULT_COUNTRY
    ):
        legacy = _legacy_snapshot_path(query)
        if legacy not in paths:
            paths.append(legacy)
    return paths


def load_snapshot(
    query: str,
    country: str = DEFAULT_COUNTRY,
    advertiser: str | None = None,
    active_status: str = DEFAULT_ACTIVE_STATUS,
    media_type: str = DEFAULT_MEDIA_TYPE,
) -> dict:
    """Load the snapshot for query + market (+ advertiser).

    Fallbacks keep old baselines alive: an advertiser watch added to a watch
    that predates it reads that watch's unfiltered file, and pre-country
    snapshots (hash of the query alone) are still read for US. A fallback file
    is only accepted when it carries no ``advertiser`` stamp — files written
    by this version under another key belong to another watch, and adopting
    one would report its ads as ended.
    """
    for index, path in enumerate(
        _snapshot_candidates(
            query, country, advertiser, active_status, media_type
        )
    ):
        data = _read_snapshot_file(path)
        if data is None:
            continue
        if index and any(
            key in data for key in ("advertiser", "active_status", "media_type")
        ):
            continue
        # ``query``/``advertiser``/filters are file metadata; keep the public
        # payload shape stable and tolerate payloads written before they existed.
        for key in ("query", "advertiser", "active_status", "media_type"):
            data.pop(key, None)
        return data
    return {"ads": {}}
