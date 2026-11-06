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
    query = str(args.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "query required"})
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        return json.dumps({"error": "invalid limit"})
    try:
        ads = sources.fetch_ads(query, limit=limit, dispatch=_dispatch)
        return json.dumps({"count": len(ads), "ads": ads}, ensure_ascii=False)
    except sources.ParseError as exc:
        logger.warning("ad_search parse failed for %r: %s", query, exc)
        return json.dumps(
            {
                "error": f"parse_failed: {exc}",
                "cards_seen": getattr(exc, "cards_seen", 0),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.warning("ad_search failed for %r: %s", query, exc)
        return json.dumps({"error": f"fetch_failed: {exc}"}, ensure_ascii=False)


def ad_watch(args, **kwargs):
    try:
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
        return json.dumps(
            {"action": action, "watchlist": items}, ensure_ascii=False
        )
    except Exception as exc:
        logger.warning("ad_watch failed for %r: %s", args, exc)
        return json.dumps({"error": f"watch_failed: {exc}"}, ensure_ascii=False)


def _prior_ads(query: str) -> dict:
    try:
        return (store.load_snapshot(query) or {}).get("ads") or {}
    except Exception:
        return {}


def ad_check(args, **kwargs):
    results = []
    for query in store.watch_list():
        try:
            # Meta-aware fetch: a render clipped at the char budget is a
            # partial listing, and ids missing from it are not "ended".
            ads, meta = sources.fetch_ads_with_meta(query, dispatch=_dispatch)
            complete = bool(meta.get("complete", True))
        except sources.ParseError as exc:
            # Markup changed: do not treat it as "every ad ended" and do not
            # overwrite the snapshot with an empty baseline.
            logger.warning("ad_check parse failed for %r: %s", query, exc)
            results.append(
                {"query": query, "skipped": True, "reason": "parse_failed"}
            )
            continue
        except Exception as exc:
            logger.warning("ad_check fetch failed for %r: %s", query, exc)
            if _prior_ads(query):
                results.append(
                    {"query": query, "skipped": True, "reason": "fetch_empty"}
                )
            else:
                results.append({"query": query, "error": str(exc)})
            continue

        if not ads and _prior_ads(query):
            # A blank page must not be read as "every ad ended".
            results.append(
                {"query": query, "skipped": True, "reason": "fetch_empty"}
            )
            continue

        try:
            by_id = {ad["id"]: ad for ad in ads}
            prior = store.load_snapshot(query)
            if complete:
                diff_old = prior
            else:
                # Partial listing: mask out prior ads the render never reached,
                # so an absent id is not counted as ended. Status flips on ads
                # that did render are still reported.
                prior_ads = prior.get("ads") or {}
                diff_old = {"ads": {k: v for k, v in prior_ads.items() if k in by_id}}
            diff = diffing.diff_snapshots(diff_old, {"ads": by_id})
            store.save_snapshot(query, {"ads": by_id})
            results.append(
                {
                    "query": query,
                    "partial": not complete,
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
