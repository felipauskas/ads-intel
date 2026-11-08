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

#: Fields surfaced for every ad in an ad_check bucket. The enriched Task-1
#: fields are included so a change report names the destination/CTA and
#: grouping signals, not just the id.
_SUMMARY_KEYS = (
    "id",
    "page_name",
    "status",
    "first_seen",
    "last_seen",
    "creative_text",
    "library_url",
    "page_url",
    "page_id",
    "link_url",
    "link_title",
    "cta_text",
    "images",
    "has_video",
    "same_creative_count",
    "multiple_versions",
)

#: Typed defaults for every summarized field. Pre-upgrade snapshots and
#: renders that omit an enriched field must never surface JSON null: a caller
#: reading `images[0]` or counting `same_creative_count` should see the empty
#: value, not a type error.
_SUMMARY_DEFAULTS = {
    "id": "",
    "page_name": "",
    "status": "",
    "first_seen": "",
    "last_seen": "",
    "creative_text": "",
    "library_url": "",
    "page_url": "",
    "page_id": "",
    "link_url": "",
    "link_title": "",
    "cta_text": "",
    "images": [],
    "has_video": False,
    "same_creative_count": 0,
    "multiple_versions": False,
}

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

_FILTER_CHOICES = {
    "active_status": sources.ACTIVE_STATUSES,
    "media_type": sources.MEDIA_TYPES,
}


def _requested_country(args) -> str | None:
    """Market code from tool args: absent/null means US, present must be XX."""
    raw = args.get("country")
    # Hosts routinely send missing optional fields as JSON null; treat that
    # exactly like an omitted field.
    if raw is None:
        return store.DEFAULT_COUNTRY
    if isinstance(raw, str) and _COUNTRY_RE.fullmatch(raw):
        return raw
    return None


def _requested_filter(args, key: str) -> str | None:
    """Filter value from tool args: absent/null means ``all``, else exact match.

    Returns ``None`` for anything outside the library's vocabulary, so the
    caller can name the field in its error instead of silently widening the
    search.
    """
    raw = args.get(key)
    # Hosts routinely send missing optional fields as JSON null.
    if raw is None:
        return "all"
    if isinstance(raw, str) and raw.strip() in _FILTER_CHOICES[key]:
        return raw.strip()
    return None


def set_ctx(ctx) -> None:
    global _CTX
    _CTX = ctx


def _dispatch(name, args):
    if _CTX is None:
        return None
    return _CTX.dispatch_tool(name, args)


def _summary(ad: dict) -> dict:
    summary = {}
    for key in _SUMMARY_KEYS:
        value = ad.get(key)
        if value is None:
            value = _SUMMARY_DEFAULTS[key]
            if isinstance(value, list):
                # Never hand out the shared default list itself.
                value = list(value)
        summary[key] = value
    return summary


def ad_search(args, **kwargs):
    query = str(args.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "query required"})
    # NUL is the snapshot-key field separator (store._artifact_key), so a
    # query containing it could alias another watch's baseline file.
    if "\x00" in query:
        return json.dumps({"error": "invalid query"})
    country = _requested_country(args)
    if country is None:
        return json.dumps({"error": "invalid_country"})
    active_status = _requested_filter(args, "active_status")
    if active_status is None:
        return json.dumps({"error": "invalid_active_status"})
    media_type = _requested_filter(args, "media_type")
    if media_type is None:
        return json.dumps({"error": "invalid_media_type"})
    advertiser = str(args.get("advertiser") or "").strip()
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError, OverflowError):
        # JSON `1e309` decodes to inf; `int(inf)` is an OverflowError, not a
        # ValueError, and must not escape as a handler crash.
        return json.dumps({"error": "invalid limit"})
    try:
        if not advertiser:
            ads, meta = sources.fetch_ads_with_meta(
                query,
                limit=limit,
                dispatch=_dispatch,
                country=country,
                active_status=active_status,
                media_type=media_type,
            )
            return json.dumps(
                {
                    "count": len(ads),
                    "complete": bool(meta.get("complete", False)),
                    "fetched": len(ads),
                    "country": country,
                    "ads": ads,
                },
                ensure_ascii=False,
            )
        # Keyword hits are not a brand filter: resolve the advertiser to one
        # page name, or say so instead of passing noise off as the brand.
        # Resolve against the FULL parse — the brand's page can sit anywhere
        # in the listing — and only then apply the caller's `limit`.
        ads, meta = sources.fetch_ads_with_meta(
            query,
            limit=None,
            dispatch=_dispatch,
            country=country,
            active_status=active_status,
            media_type=media_type,
        )
        resolution, kept = resolve.filter_ads(ads, advertiser)
        if "error" in resolution:
            return json.dumps(
                {**resolution, "country": country, "query": query},
                ensure_ascii=False,
            )
        total = len(kept)
        kept = kept[: max(limit, 0)]
        # The full parse was whole; `limit` may still have sliced the brand's
        # own ads, so carry the same conservative signal as an unfiltered
        # search. `total == limit` returned every ad: nothing was sliced.
        complete = bool(meta.get("complete", False)) and total <= max(limit, 0)
        return json.dumps(
            {
                "count": len(kept),
                "complete": complete,
                "fetched": len(kept),
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
            # NUL separates the fields of a snapshot key; reject it here so a
            # watch cannot alias another watch's baseline.
            if "\x00" in str(query):
                return json.dumps({"error": "invalid query"})
            country = _requested_country(args)
            if country is None:
                return json.dumps({"error": "invalid_country"})
            active_status = _requested_filter(args, "active_status")
            if active_status is None:
                return json.dumps({"error": "invalid_active_status"})
            media_type = _requested_filter(args, "media_type")
            if media_type is None:
                return json.dumps({"error": "invalid_media_type"})
            advertiser = str(args.get("advertiser") or "").strip()
            items = store.watch_add(
                query,
                country=country,
                advertiser=advertiser or None,
                active_status=active_status,
                media_type=media_type,
            )
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
    query: str,
    country: str = store.DEFAULT_COUNTRY,
    advertiser: str | None = None,
    active_status: str = store.DEFAULT_ACTIVE_STATUS,
    media_type: str = store.DEFAULT_MEDIA_TYPE,
) -> dict:
    try:
        return (
            store.load_snapshot(
                query,
                country=country,
                advertiser=advertiser,
                active_status=active_status,
                media_type=media_type,
            )
            or {}
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
        # Filters are absent on entries written before they existed.
        active_status = entry.get("active_status") or store.DEFAULT_ACTIVE_STATUS
        media_type = entry.get("media_type") or store.DEFAULT_MEDIA_TYPE
        # Echo the filters that narrow this watch so a row is self-describing.
        # Same rule as storage: defaults stay implicit, so an unfiltered row
        # keeps its pre-filter shape byte for byte.
        echo = {}
        if active_status != store.DEFAULT_ACTIVE_STATUS:
            echo["active_status"] = active_status
        if media_type != store.DEFAULT_MEDIA_TYPE:
            echo["media_type"] = media_type
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
                active_status=active_status,
                media_type=media_type,
            )
            # Fail safe: an unknown completeness is treated as partial.
            complete = bool(meta.get("complete", False))
        except sources.ParseError as exc:
            # Markup changed: do not treat it as "every ad ended" and do not
            # overwrite the snapshot with an empty baseline.
            logger.warning("ad_check parse failed for %r: %s", query, exc)
            results.append(
                {
                    "query": query,
                    "country": country,
                    **echo,
                    "skipped": True,
                    "reason": "parse_failed",
                    # Completeness is unknown, so the row is partial by rule.
                    "partial": True,
                    "artifacts": {"error": "parse_failed"},
                }
            )
            continue
        except Exception as exc:
            logger.warning("ad_check fetch failed for %r: %s", query, exc)
            if _prior_ads(query, country, advertiser, active_status, media_type):
                results.append(
                    {
                        "query": query,
                        "country": country,
                        **echo,
                        "skipped": True,
                        "reason": "fetch_empty",
                        "partial": True,
                        "artifacts": {"error": "fetch_failed"},
                    }
                )
            else:
                results.append(
                    {
                        "query": query,
                        "country": country,
                        **echo,
                        "error": str(exc),
                        "partial": True,
                        "artifacts": {"error": str(exc)},
                    }
                )
            continue

        if not ads and _prior_ads(
            query, country, advertiser, active_status, media_type
        ):
            # A blank page must not be read as "every ad ended".
            results.append(
                {
                    "query": query,
                    "country": country,
                    **echo,
                    "skipped": True,
                    "reason": "fetch_empty",
                    "partial": True,
                    "artifacts": {"error": "fetch_empty"},
                }
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
                        **echo,
                        "advertiser": advertiser,
                        "error": "name_not_matched",
                        # A miss on a clipped render only means the page was
                        # not in what rendered: report the same completeness
                        # every other row carries.
                        "partial": not complete,
                        "target": resolution["target"],
                        "candidates": resolution["candidates"],
                        "threshold": resolution["threshold"],
                        "artifacts": {"error": "name_not_matched"},
                    }
                )
                continue

        try:
            by_id = {ad["id"]: ad for ad in ads}
            prior = store.load_snapshot(
                query,
                country=country,
                advertiser=advertiser,
                active_status=active_status,
                media_type=media_type,
            )
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
                query,
                {"ads": baseline},
                country=country,
                advertiser=advertiser,
                active_status=active_status,
                media_type=media_type,
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
                    active_status=active_status,
                    media_type=media_type,
                )
            except Exception as exc:
                logger.warning("ad_check report failed for %r: %s", query, exc)
                artifacts = {"error": str(exc)}
            results.append(
                {
                    "query": query,
                    "country": country,
                    **echo,
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
            results.append(
                {
                    "query": query,
                    "country": country,
                    **echo,
                    "error": str(exc),
                    "partial": True,
                    "artifacts": {"error": str(exc)},
                }
            )

    return json.dumps({"checked_at": checked_at, "results": results}, ensure_ascii=False)
