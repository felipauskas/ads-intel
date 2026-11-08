"""Pure functions diffing two ad snapshots. No I/O.

An ad whose status flips to ended counts as `ended` even though its id is still
present, and one that flips back to active counts as `new`: the watch's point is
which ads started or stopped running, not merely which ids appeared.
"""

_ENDED_STATUSES = {"ended", "inactive", "stopped"}


def _norm_status(ad: dict) -> str:
    return str(ad.get("status") or "").strip().lower()


def _is_ended(ad: dict) -> bool:
    return _norm_status(ad) in _ENDED_STATUSES


def _sig(ad: dict, keys: tuple[str, ...] = ()) -> tuple:
    """Comparable ad signature: status plus the creative keys ``keys``.

    Only keys named by the caller are included, so a field that a stored
    baseline predates is not compared at all: an upgrade must not report every
    ad as changed just because it now carries ``link_url``/``cta_text``.
    """
    return (_norm_status(ad),) + tuple(
        str(ad.get(key) or "").strip() for key in keys
    )


#: Creative fields whose change is worth reporting, beyond creative text.
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

    Status strings are compared case- and whitespace-insensitively. An id absent
    from the new snapshot is reported as `ended`, so callers must pass complete
    listings — a partial fetch will produce false `ended` reports. When a
    listing may be truncated, the caller must either pass an old snapshot
    restricted to ids the fetch actually returned, or drop the `ended` bucket.
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
