"""Tool handlers for ads-intel, wired to the host context for dispatch."""

import json
import logging
from datetime import datetime

try:
    from . import diffing, sources, store
except ImportError:  # imported as a bare module in tests
    import diffing
    import sources
    import store

logger = logging.getLogger(__name__)

_CTX = None

_SUMMARY_KEYS = ("id", "page_name", "status", "first_seen", "library_url")


def set_ctx(ctx) -> None:
    global _CTX
    _CTX = ctx


def _dispatch(name, args):
    if _CTX is None:
        return None
    return _CTX.dispatch_tool(name, args)


def _summary(ad: dict) -> dict:
    return {key: ad.get(key) for key in _SUMMARY_KEYS}


def ad_search(args, **kwargs):
    query = args.get("query") or ""
    try:
        ads = sources.fetch_ads(
            query,
            limit=int(args.get("limit", 20)),
            dispatch=_dispatch,
        )
        return json.dumps({"count": len(ads), "ads": ads}, ensure_ascii=False)
    except Exception as exc:
        logger.warning("ad_search failed for %r: %s", query, exc)
        return json.dumps({"error": f"fetch_failed: {exc}"}, ensure_ascii=False)


def ad_watch(args, **kwargs):
    action = (args.get("action") or "").strip()
    query = args.get("query", "")
    if action == "add":
        if not str(query).strip():
            return json.dumps({"error": "query required"})
        items = store.watch_add(query)
    elif action == "remove":
        items = store.watch_remove(query)
    elif action == "list":
        items = store.watch_list()
    else:
        return json.dumps({"error": f"unknown action: {action}"})
    return json.dumps({"action": action, "watchlist": items}, ensure_ascii=False)


def ad_check(args, **kwargs):
    results = []
    for query in store.watch_list():
        try:
            ads = sources.fetch_ads(query, dispatch=_dispatch)
            by_id = {ad["id"]: ad for ad in ads}
            diff = diffing.diff_snapshots(store.load_snapshot(query), {"ads": by_id})
            store.save_snapshot(query, {"ads": by_id})
            results.append(
                {
                    "query": query,
                    "new_ads": len(diff["new"]),
                    "ended_ads": len(diff["ended"]),
                    "changed_ads": len(diff["changed"]),
                    "new": [_summary(ad) for ad in diff["new"]],
                    "ended": [_summary(ad) for ad in diff["ended"]],
                    "changed": [_summary(ad) for ad in diff["changed"]],
                }
            )
        except Exception as exc:
            logger.warning("ad_check failed for %r: %s", query, exc)
            results.append({"query": query, "error": str(exc)})

    checked_at = datetime.now().isoformat(timespec="seconds")
    return json.dumps({"checked_at": checked_at, "results": results}, ensure_ascii=False)
