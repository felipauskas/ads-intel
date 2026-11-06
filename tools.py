"""Tool handlers for ads-intel, wired to the host context for dispatch."""

import json
import logging
import re
from datetime import datetime

try:
    from . import diffing, report, resolve, sources, store
except ImportError:  # imported as a bare module in tests
    import diffing
    import report
    import resolve
    import sources
    import store

logger = logging.getLogger(__name__)

_CTX = None

_SUMMARY_KEYS = ("id", "page_name", "status", "first_seen", "library_url")

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def _requested_country(args) -> str | None:
    """Market code from tool args: absent/null means US, present must be XX."""
    raw = args.get("country")
    # Hosts routinely send missing optional fields as JSON null; treat that
    # exactly like an omitted field.
    if raw is None:
        return store.DEFAULT_COUNTRY
    if isinstance(raw, str) and _COUNTRY_RE.match(raw):
        return raw
    return None


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
    country = _requested_country(args)
    if country is None:
        return json.dumps({"error": "invalid_country"})
    advertiser = str(args.get("advertiser") or "").strip()
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        return json.dumps({"error": "invalid limit"})
    try:
        if not advertiser:
            ads = sources.fetch_ads(
                query, limit=limit, dispatch=_dispatch, country=country
            )
            return json.dumps(
                {"count": len(ads), "country": country, "ads": ads}, ensure_ascii=False
            )
        # Keyword hits are not a brand filter: resolve the advertiser to one
        # page name, or say so instead of passing noise off as the brand.
        # Resolve against the FULL parse — the brand's page can sit anywhere
        # in the listing — and only then apply the caller's `limit`.
        ads = sources.fetch_ads(
            query, limit=None, dispatch=_dispatch, country=country
        )
        resolution, kept = resolve.filter_ads(ads, advertiser)
        if "error" in resolution:
            return json.dumps(
                {**resolution, "country": country, "query": query},
                ensure_ascii=False,
            )
        kept = kept[: max(limit, 0)]
        return json.dumps(
            {
                "count": len(kept),
                "country": country,
                "advertiser": advertiser,
                "resolved": resolution,
                "ads": kept,
            },
            ensure_ascii=False,
        )
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
            country = _requested_country(args)
            if country is None:
                return json.dumps({"error": "invalid_country"})
            advertiser = str(args.get("advertiser") or "").strip()
            items = store.watch_add(query, country=country, advertiser=advertiser or None)
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


def _prior_ads(
    query: str, country: str = store.DEFAULT_COUNTRY, advertiser: str | None = None
) -> dict:
    try:
        return (
            store.load_snapshot(query, country=country, advertiser=advertiser) or {}
        ).get("ads") or {}
    except Exception:
        return {}


def ad_check(args, **kwargs):
    results = []
    checked_at = datetime.now().isoformat(timespec="seconds")
    for entry in store.watch_list():
        query = entry["query"]
        country = entry["country"]
        # Entries written before advertiser resolution existed have no target.
        advertiser = entry.get("advertiser") or ""
        try:
            # Meta-aware fetch: a render clipped at the char budget, carrying a
            # truncation footer, or sliced by the result limit is a partial
            # listing, and ids missing from it are not "ended". An advertiser
            # watch resolves the page name first, so it fetches the FULL parse:
            # the brand's page can appear anywhere in the keyword hits, and a
            # slice taken before resolution hides both the page and its tail
            # ads. No advertiser: the default 20-ad limit applies.
            ads, meta = sources.fetch_ads_with_meta(
                query,
                limit=None if advertiser else 20,
                dispatch=_dispatch,
                country=country,
            )
            # Fail safe: an unknown completeness is treated as partial.
            complete = bool(meta.get("complete", False))
        except sources.ParseError as exc:
            # Markup changed: do not treat it as "every ad ended" and do not
            # overwrite the snapshot with an empty baseline.
            logger.warning("ad_check parse failed for %r: %s", query, exc)
            results.append(
                {"query": query, "country": country, "skipped": True, "reason": "parse_failed"}
            )
            continue
        except Exception as exc:
            logger.warning("ad_check fetch failed for %r: %s", query, exc)
            if _prior_ads(query, country, advertiser):
                results.append(
                    {"query": query, "country": country, "skipped": True, "reason": "fetch_empty"}
                )
            else:
                results.append({"query": query, "country": country, "error": str(exc)})
            continue

        if not ads and _prior_ads(query, country, advertiser):
            # A blank page must not be read as "every ad ended".
            results.append(
                {"query": query, "country": country, "skipped": True, "reason": "fetch_empty"}
            )
            continue

        resolution = None
        if advertiser:
            # Filter to the resolved page before diffing, so a keyword watch
            # tracks the advertiser's ads only. No match: report it and leave
            # the snapshot untouched.
            resolution, ads = resolve.filter_ads(ads, advertiser)
            if "error" in resolution:
                logger.warning(
                    "ad_check advertiser %r not matched for %r", advertiser, query
                )
                results.append(
                    {
                        "query": query,
                        "country": country,
                        "advertiser": advertiser,
                        "error": "name_not_matched",
                        # A miss on a clipped render only means the page was
                        # not in what rendered: report the same completeness
                        # every other row carries.
                        "partial": not complete,
                        "target": resolution["target"],
                        "candidates": resolution["candidates"],
                        "threshold": resolution["threshold"],
                    }
                )
                continue

        try:
            by_id = {ad["id"]: ad for ad in ads}
            prior = store.load_snapshot(query, country=country, advertiser=advertiser)
            if complete:
                diff_old = prior
                baseline = by_id
            else:
                # Partial listing: mask out prior ads the render never reached,
                # so an absent id is not counted as ended. Status flips on ads
                # that did render are still reported.
                prior_ads = prior.get("ads") or {}
                diff_old = {"ads": {k: v for k, v in prior_ads.items() if k in by_id}}
                # Merge instead of replacing: a truncated render must not shrink
                # the baseline, or the next complete run reports every masked id
                # as new.
                baseline = {**prior_ads, **by_id}
            diff = diffing.diff_snapshots(diff_old, {"ads": by_id})
            store.save_snapshot(
                query, {"ads": baseline}, country=country, advertiser=advertiser
            )
            # A report failure must never fail the check itself.
            try:
                artifacts = report.write_report(
                    query,
                    diff,
                    baseline,
                    {"checked_at": checked_at, "partial": not complete},
                    country=country,
                    advertiser=advertiser,
                )
            except Exception as exc:
                logger.warning("ad_check report failed for %r: %s", query, exc)
                artifacts = {"error": str(exc)}
            results.append(
                {
                    "query": query,
                    "country": country,
                    "partial": not complete,
                    **({"advertiser": advertiser, "resolved": resolution} if resolution else {}),
                    "new_ads": len(diff["new"]),
                    "ended_ads": len(diff["ended"]),
                    "changed_ads": len(diff["changed"]),
                    "new": [_summary(ad) for ad in diff["new"]],
                    "ended": [_summary(ad) for ad in diff["ended"]],
                    "changed": [_summary(ad) for ad in diff["changed"]],
                    "artifacts": artifacts,
                }
            )
        except Exception as exc:
            logger.warning("ad_check failed for %r: %s", query, exc)
            results.append({"query": query, "country": country, "error": str(exc)})

    return json.dumps({"checked_at": checked_at, "results": results}, ensure_ascii=False)
