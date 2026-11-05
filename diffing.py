"""Pure functions diffing two ad snapshots. No I/O.

An ad whose status flips to ended counts as `ended` even though its id is still
present, and one that flips back to active counts as `new`: the watch's point is
which ads started or stopped running, not merely which ids appeared.
"""

_ENDED_STATUSES = {"ended", "inactive", "stopped"}


def _is_ended(ad: dict) -> bool:
    return str(ad.get("status") or "").strip().lower() in _ENDED_STATUSES


def _sig(ad: dict) -> tuple:
    return (ad.get("status"), ad.get("creative_text"))


def diff_snapshots(old: dict, new: dict) -> dict:
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
