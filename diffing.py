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


def _sig(ad: dict) -> tuple:
    return (_norm_status(ad), ad.get("creative_text"))


def diff_snapshots(old: dict, new: dict) -> dict:
    """Classify two snapshots into `new`, `ended` and `changed` buckets.

    Status strings are compared case- and whitespace-insensitively. An id absent
    from the new snapshot is reported as `ended`, so callers must pass complete
    listings — a partial fetch will produce false `ended` reports. When a
    listing may be truncated, the caller must either pass an old snapshot
    restricted to ids the fetch actually returned, or drop the `ended` bucket.
    :func:`tools.ad_check` does the former for partial renders.
    """
    old_ads = old.get("ads") or {}
    new_ads = new.get("ads") or {}

    new_ads_list = [ad for ad_id, ad in new_ads.items() if ad_id not in old_ads]
    ended = [ad for ad_id, ad in old_ads.items() if ad_id not in new_ads]
    changed = []

    for ad_id, after in new_ads.items():
        before = old_ads.get(ad_id)
        if before is None:
            continue
        if _is_ended(before) != _is_ended(after):
            (ended if _is_ended(after) else new_ads_list).append(after)
        elif _sig(before) != _sig(after):
            changed.append(after)

    return {"new": new_ads_list, "ended": ended, "changed": changed}
