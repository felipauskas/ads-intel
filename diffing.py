"""Pure functions diffing two ad snapshots. No I/O.

An ad whose status flips to ended counts as `ended` even though its id is still
present, and one that flips back to active counts as `new`: the watch's point is
which ads started or stopped running, not merely which ids appeared.

Two honesty caveats about what a diff can prove:

* **Window-scoped.** The fetch has no pagination: even a `complete` listing is
  only the top-N window Meta rendered (see ``sources.COMPLETENESS_SCOPE``). So
  an id missing from the new page is not proof its ad ended, and a newly
  appearing ad may merely have entered the visible window rather than launched.
  These are observations about the rendered window, not about Meta's full
  result set.
* **Volatile render fields.** ``link_title`` can carry the live
  "N people like this" counter from the Like-Page block. The counter moves
  between identical renders, so it is normalised away before comparison; a
  counter-only difference is not a creative change.
"""

import re

_ENDED_STATUSES = {"ended", "inactive", "stopped"}

#: Live counters that move between renders of byte-identical creative. Stripped
#: before comparison so page-engagement churn is not reported as a change.
_LIKE_COUNTER_RE = re.compile(
    r"\b[\d.,]+\s*[KMB]?\s+(?:people|followers)\s+(?:like this|follow this)\b\.?",
    re.IGNORECASE,
)

#: Snapshot fields that need volatile normalisation, mapping field -> pattern.
_VOLATILE_FIELD_RES = {"link_title": _LIKE_COUNTER_RE}


def _norm_status(ad: dict) -> str:
    return str(ad.get("status") or "").strip().lower()


def _is_ended(ad: dict) -> bool:
    return _norm_status(ad) in _ENDED_STATUSES


def _norm_field(key: str, value) -> str:
    """Comparable text for one creative field, volatile counters removed.

    The public render mixes stable creative copy with live engagement lines in
    the same string (``link_title`` can carry "19,720,345 people like this").
    Comparing the raw bytes turned counter churn into a reported creative
    change, so the volatile span is stripped and whitespace re-collapsed. A
    genuine title edit still differs after normalisation.
    """
    text = str(value or "").strip()
    pattern = _VOLATILE_FIELD_RES.get(key)
    if pattern is not None:
        text = " ".join(pattern.sub(" ", text).split())
    return text


def _sig(ad: dict, keys: tuple[str, ...] = ()) -> tuple:
    """Comparable ad signature: status plus the creative keys ``keys``.

    Only keys named by the caller are included, so a field that a stored
    baseline predates is not compared at all: an upgrade must not report every
    ad as changed just because it now carries ``link_url``/``cta_text``.
    """
    return (_norm_status(ad),) + tuple(
        _norm_field(key, ad.get(key)) for key in keys
    )


#: Creative fields whose change is worth reporting, beyond creative text.
#:
#: Deliberately excludes ``same_creative_count`` and ``multiple_versions``:
#: both are render-derived engagement/grouping signals that move without the
#: creative changing. ``link_title`` is included but normalised, because the
#: Like-Page block appends a live like counter to it.
_CREATIVE_KEYS = ("creative_text", "link_url", "link_title", "cta_text")


def _same_creative(before: dict, after: dict) -> bool:
    keys = tuple(k for k in _CREATIVE_KEYS if k in before and k in after)
    return _sig(before, keys) == _sig(after, keys)


def _ads_map(snapshot) -> dict:
    """The ``ads`` mapping of a snapshot; anything malformed is empty.

    A corrupt snapshot file (``null``, a list, or ``{"ads": "notadict"}``)
    must degrade to "no ads" instead of raising on ``.items()``: the caller
    then sees a clean baseline rather than losing the whole check.
    """
    if not isinstance(snapshot, dict):
        return {}
    ads = snapshot.get("ads")
    return ads if isinstance(ads, dict) else {}


def diff_snapshots(old, new) -> dict:
    """Classify two snapshots into `new`, `ended` and `changed` buckets.

    Status strings are compared case- and whitespace-insensitively; volatile
    render counters (the Like-Page "N people like this" line in
    ``link_title``) are stripped before creative comparison.

    **The buckets are window-scoped.** Both snapshots are single fetches of
    Meta's rendered listing, and the fetch has no pagination: even a fetch
    marked ``complete`` holds only the top-N window Meta rendered. So
    `ended` means "absent from this rendered window", not "proven stopped",
    and `new` means "appeared in this rendered window", not "proven
    launched". Callers must word their reports accordingly.

    An id absent from *a clipped* new snapshot is weaker still. The buckets
    above are the honest reading only for unclipped renders; when a render may
    be clipped, the caller must either pass an old snapshot restricted to ids
    the fetch actually returned, or drop the `ended` bucket. (Passing a clipped
    render unfiltered would report every id past the clip as `ended`.)
    :func:`tools.ad_check` does the former for partial renders.
    """
    old_ads = _ads_map(old)
    new_ads = _ads_map(new)

    new_ads_list = [
        ad for ad_id, ad in new_ads.items()
        if ad_id not in old_ads and isinstance(ad, dict)
    ]
    ended = [
        ad for ad_id, ad in old_ads.items()
        if ad_id not in new_ads and isinstance(ad, dict)
    ]
    changed = []

    for ad_id, after in new_ads.items():
        if not isinstance(after, dict):
            continue
        before = old_ads.get(ad_id)
        if not isinstance(before, dict):
            continue
        if _is_ended(before) != _is_ended(after):
            (ended if _is_ended(after) else new_ads_list).append(after)
        elif not _same_creative(before, after):
            changed.append(after)

    return {"new": new_ads_list, "ended": ended, "changed": changed}
