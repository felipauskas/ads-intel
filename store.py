"""Watchlist + snapshot persistence under the plugin data dir."""

import hashlib
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

try:  # POSIX only; a Windows dev box degrades to in-process locking.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on Windows
    fcntl = None

try:
    from plugins.plugin_storage import plugin_data_dir

    def _data_dir() -> Path:
        return Path(plugin_data_dir("ads-intel"))

except ImportError:

    def _data_dir() -> Path:
        return Path.home() / ".ads-intel-dev"


WATCH = "watchlist.json"
LOCK = ".lock"

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


def _strict_filter(value, name: str, allowed: tuple[str, ...]) -> str:
    """Validate a caller-supplied filter for a destructive narrowing.

    Unlike :func:`_norm_filter`, an unusable value is refused instead of
    silently falling back to the default: widening a removal would delete an
    entry the caller did not name.
    """
    text = str(value or "").strip()
    if text not in allowed:
        raise ValueError(f"invalid {name}: {value!r}")
    return text


def _strict_country(country) -> str:
    """Validate a caller-supplied market code for a destructive narrowing."""
    code = str(country or "").strip().upper()
    if not _COUNTRY_RE.match(code):
        raise ValueError(f"invalid country: {country!r}")
    return code


def _strict_page_id(value) -> str:
    """Validate a Meta Page ID: an ASCII decimal run, nothing else.

    ``str.isdigit`` alone accepts other scripts' digits (``"١٢٣"`` is all
    digits), and those are not Meta Page IDs, so both checks apply. Used both
    for stored entries and for artifact-key components: an ID that cannot be
    keyed unambiguously must never be treated as "no page".
    """
    text = str(value if value is not None else "").strip()
    if not (text.isascii() and text.isdigit()):
        raise ValueError(f"invalid page_id: {value!r}")
    return text


def _watch_path() -> Path:
    return _data_dir() / WATCH


#: Serialises read-modify-write cycles on the files in the data dir.
#:
#: ``flock`` is advisory, which is enough here: every writer — in this process
#: or in any other ads-intel process — goes through :func:`data_lock`. It also
#: handles crashes for free: the kernel drops the lock when the holder dies, so
#: there is no lock file to stale out and no timeout to tune.
#:
#: Re-entrancy matters: ``ad_check`` holds the lock across load → diff → save,
#: and ``save_snapshot`` takes it again. A second ``flock`` on a *different*
#: descriptor of the same file would block forever, so the depth counter keeps
#: only the outermost call holding the fd; intra-process threads queue on the
#: RLock instead of on ``flock``.
_PROC_LOCK = threading.RLock()
_LOCK_DEPTH = 0


@contextmanager
def data_lock():
    """Hold the data-dir write lock (re-entrant within a thread).

    Hold this around a whole read-modify-write cycle, never around network
    I/O: the lock is exclusive across processes, so a fetch inside it would
    serialise every check behind the slowest one.
    """
    global _LOCK_DEPTH
    with _PROC_LOCK:
        if _LOCK_DEPTH:
            _LOCK_DEPTH += 1
            try:
                yield
            finally:
                _LOCK_DEPTH -= 1
            return
        fd = None
        if fcntl is not None:
            directory = _data_dir()
            directory.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(directory / LOCK), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except BaseException:
                os.close(fd)
                raise
        # No fcntl (Windows dev): the RLock still serialises this process's
        # threads, but two processes could interleave. Accepted; production
        # runs on POSIX.
        _LOCK_DEPTH = 1
        try:
            yield
        finally:
            _LOCK_DEPTH = 0
            if fd is not None and fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)


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


def has_nul(value) -> bool:
    """True when a component carries NUL, the artifact-key field separator.

    NUL is not printable in a query or a page name, and allowing it lets one
    component impersonate the separator between two others (an advertiser
    ``"b\\x00active_status=active"`` used to hash like advertiser ``"b"``
    watched with the active filter). Callers reject such input; the key
    builder refuses it rather than minting an ambiguous key.
    """
    return "\x00" in _norm(value)


def _norm_country(country) -> str:
    """Normalise a market code; anything unusable falls back to US."""
    code = str(country or "").strip().upper()
    return code if _COUNTRY_RE.match(code) else DEFAULT_COUNTRY


def _entry(item) -> dict | None:
    """One watch entry as ``{query, country[, advertiser][, page_id][, filters]}``.

    Legacy strings migrate to US; entries written before advertiser
    resolution existed simply have no ``advertiser`` key. Filters are stored
    only when they differ from the default, so an unfiltered watch keeps the
    exact shape (and snapshot key) it had before filters existed.

    ``page_id`` marks a page watch. An unusable ID drops the whole entry
    rather than the field: an entry that silently lost its ID would be a
    keyword watch wearing a page label, and would diff against the keyword
    listing. An empty/absent ID means "no page" and stays out of the entry.
    """
    if isinstance(item, str):
        query = _norm(item)
        if not query or has_nul(query):
            return None
        return {"query": query, "country": DEFAULT_COUNTRY}
    if isinstance(item, dict):
        query = _norm(item.get("query"))
        # An entry whose query or advertiser carries NUL cannot be keyed
        # unambiguously, so it is dropped instead of persisted.
        if not query or has_nul(query):
            return None
        entry = {"query": query, "country": _norm_country(item.get("country"))}
        advertiser = _norm(item.get("advertiser"))
        if has_nul(advertiser):
            return None
        if advertiser:
            entry["advertiser"] = advertiser
        page_id = _norm(item.get("page_id"))
        if page_id:
            try:
                entry["page_id"] = _strict_page_id(page_id)
            except ValueError:
                return None
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
    page_id: str | None = None,
) -> list[dict]:
    entry = _entry(
        {
            "query": query,
            "country": country,
            "advertiser": advertiser,
            "active_status": active_status,
            "media_type": media_type,
            "page_id": page_id,
        }
    )
    if entry is None:
        return watch_list()
    with data_lock():
        items = watch_list()
        if entry not in items:
            items.append(entry)
            _write_json(_watch_path(), items)
    return items


def watch_remove(
    query: str,
    *,
    advertiser: str | None = None,
    country: str | None = None,
    active_status: str | None = None,
    media_type: str | None = None,
    page_id: str | None = None,
) -> list[dict]:
    """Remove watch entries for ``query``.

    Without the narrowing keywords this drops every entry for ``query``,
    regardless of country, advertiser, page or filters — the historical
    behaviour. Passing any of them restricts the removal to entries that
    match: a watch for the same query but another advertiser, market, page or
    filter survives, so two brand watches on one keyword can be removed one
    at a time, and a page watch can be dropped without touching the keyword
    watch beside it. An invalid narrower raises ``ValueError`` rather than
    falling back to a default, because widening a removal would delete an
    entry the caller did not name.
    """
    q = _norm(query)
    adv = _norm(advertiser)
    # A narrower is a filter, not a fallback: an invalid value must refuse the
    # removal, never widen it to a different market or filter.
    cc = _strict_country(country) if country else None
    active = (
        _strict_filter(active_status, "active_status", _ACTIVE_STATUSES)
        if active_status is not None
        else None
    )
    media = (
        _strict_filter(media_type, "media_type", _MEDIA_TYPES)
        if media_type is not None
        else None
    )
    # ``None`` means "not narrowed on page"; an empty or malformed string is a
    # caller error, because treating it as absent would remove the keyword
    # watch and every page watch with it.
    pid = _strict_page_id(page_id) if page_id is not None else None

    def matches(entry: dict) -> bool:
        if entry["query"] != q:
            return False
        if adv and _norm(entry.get("advertiser")) != adv:
            return False
        if cc and entry["country"] != cc:
            return False
        if pid and _norm(entry.get("page_id")) != pid:
            return False
        if active is not None and (
            _norm_filter(
                entry.get("active_status"),
                DEFAULT_ACTIVE_STATUS,
                _ACTIVE_STATUSES,
            )
            != active
        ):
            return False
        if media is not None and (
            _norm_filter(
                entry.get("media_type"), DEFAULT_MEDIA_TYPE, _MEDIA_TYPES
            )
            != media
        ):
            return False
        return True

    with data_lock():
        items = watch_list()
        kept = [x for x in items if not matches(x)]
        if kept != items:
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
    page_id: str | None = None,
) -> str:
    """Key for query + market (+ advertiser, + page, + filters).

    Without an advertiser, page or non-default filters the key is the
    pre-existing ``query\\x00country`` string, so every baseline written before
    advertiser-, page- or filter-keyed watches keeps its filename. Each
    narrowed variant gets its own key: two watches for the same query, one
    filtered and one not, must never share a snapshot or report. Sharing one
    would make a filtered fetch look like the whole listing and report the ads
    it excludes as ended. The same holds for page identity, which is a
    separate axis from the delivery market: a page watch and a keyword watch
    on one query in one market are different listings.
    """
    base = f"{_norm(query)}\x00{_norm_country(country)}"
    adv = _norm(advertiser)
    # NUL is what separates the fields above: a component carrying one could
    # alias another watch's key (advertiser "b\x00active_status=active" and
    # advertiser "b" + active filter used to hash the same file). Refuse to
    # mint such a key instead of hashing an ambiguous string.
    if has_nul(query) or has_nul(adv):
        raise ValueError("NUL not allowed in snapshot-key components")
    if adv:
        base = f"{base}\x00{adv}"
    # A malformed ID is refused outright: folding it into "no page" would let a
    # page watch share the keyword watch's baseline.
    pid = _strict_page_id(page_id) if _norm(page_id) else ""
    if pid:
        base = f"{base}\x00page_id={pid}"
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
    page_id: str | None = None,
) -> Path:
    """Stable, collision-free, length-bounded filename for query + market."""
    digest = hashlib.sha1(
        _artifact_key(
            query, country, advertiser, active_status, media_type, page_id
        ).encode("utf-8")
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
    page_id: str | None = None,
) -> dict:
    """Where the HTML report and its digest live for query + market.

    The filename hashes the same key as the snapshot: the same query watched
    in two markets, once unfiltered and once for one advertiser, or once as a
    keyword and once as a page, must never share an artifact.
    """
    digest = hashlib.sha1(
        _artifact_key(
            query, country, advertiser, active_status, media_type, page_id
        ).encode("utf-8")
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
    page_id: str | None = None,
) -> None:
    payload = dict(snap or {})
    payload["query"] = _norm(query)
    # Stamped on every write: a file written by an unfiltered watch is marked
    # advertiser "", so a filtered watch cannot mistake it for its own baseline.
    payload["advertiser"] = _norm(advertiser)
    # A page watch stamps its identity too: the file then says which listing it
    # holds, and the snapshot key is not the only record of it.
    pid = _strict_page_id(page_id) if _norm(page_id) else ""
    if pid:
        payload["page_id"] = pid
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
    with data_lock():
        _write_json(
            _snapshot_path(
                query, country, advertiser, active_status, media_type, pid or None
            ),
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
    page_id: str | None = None,
) -> list[Path]:
    """Paths to try, most specific first.

    * the advertiser-/page-/filter-keyed file (when a target, page or filter
      is set)
    * the unfiltered ``query + country`` file, which is also the exact key for
      entries without an advertiser, page or filter
    * the pre-country ``sha1(query)`` file, US only, and only for a watch with
      neither an advertiser, a page nor a filter

    A watch with an advertiser, a page, or a non-default filter never falls
    back to the unfiltered file: that baseline holds ads the target/page/filter
    excludes, so endings computed against it would be wrong (a page watch
    would report the whole keyword listing's ads as ended). It starts from an
    empty baseline instead. The same applies to the pre-country legacy file:
    it predates metadata stamps, so the load guard cannot tell it apart from
    an unfiltered baseline.
    """
    paths = [
        _snapshot_path(
            query, country, advertiser, active_status, media_type, page_id
        )
    ]
    filtered = (
        _norm_filter(active_status, DEFAULT_ACTIVE_STATUS, _ACTIVE_STATUSES)
        != DEFAULT_ACTIVE_STATUS
        or _norm_filter(media_type, DEFAULT_MEDIA_TYPE, _MEDIA_TYPES)
        != DEFAULT_MEDIA_TYPE
    )
    scoped = filtered or bool(_norm(advertiser)) or bool(_norm(page_id))
    if not scoped:
        unfiltered = _snapshot_path(query, country)
        if unfiltered not in paths:
            paths.append(unfiltered)
    if not scoped and (_norm_country(country) == DEFAULT_COUNTRY):
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
    page_id: str | None = None,
) -> dict:
    """Load the snapshot for query + market (+ advertiser, + page).

    Fallbacks keep old *unfiltered* baselines alive: pre-country snapshots
    (hash of the query alone) are still read for US. An advertiser, page or
    filtered watch never reads an unfiltered or unscoped file; its key is its
    own. A fallback file is only accepted when it carries no identity/filter
    stamp — files written by this version under another key belong to another
    watch, and adopting one would report its ads as ended.
    """
    for index, path in enumerate(
        _snapshot_candidates(
            query, country, advertiser, active_status, media_type, page_id
        )
    ):
        data = _read_snapshot_file(path)
        if data is None:
            continue
        if index and any(
            key in data
            for key in ("advertiser", "page_id", "active_status", "media_type")
        ):
            continue
        # ``query``/``advertiser``/``page_id``/filters are file metadata; keep
        # the public payload shape stable and tolerate payloads written before
        # they existed.
        for key in ("query", "advertiser", "page_id", "active_status", "media_type"):
            data.pop(key, None)
        return data
    return {"ads": {}}
