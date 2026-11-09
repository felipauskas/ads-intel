"""Single-file, offline-safe HTML report + JSON digest for one watch query.

Mechanism only: one self-contained HTML document with inline CSS, no CDN, no
external images, no scripts. Every ad is a card; every card carries its id in
``data-ad-id`` so it can be found without JS. Untrusted text (page names,
creative copy) goes through :func:`html.escape`.
"""

import html
import json
import logging
import math
from pathlib import Path

try:
    from . import store
except ImportError:  # imported as a bare module in tests
    import store

logger = logging.getLogger(__name__)

_CSS = """
:root { --bg:#f1f5f9; --card:#fff; --fg:#0f172a; --muted:#64748b;
        --border:#e2e8f0; --new:#047857; --ended:#b91c1c; --changed:#b45309; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; background: var(--bg); color: var(--fg); }
.app { max-width: 1440px; margin: 0 auto; padding: 20px; }
header { padding: 16px 0; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
h1 { font-size: 22px; font-weight: 700; word-break: break-word; }
.banner { font-size: 14px; margin-top: 6px; }
.meta-summary { font-size: 13px; color: var(--muted); margin-top: 4px; }
.partial { background: #fef3c7; color: #92400e; border: 1px solid #fde68a;
           border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 16px; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
           gap: 16px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
        padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.card-header { display: flex; align-items: center; gap: 8px; }
.card-page { font-size: 13px; font-weight: 600; color: #334155; flex: 1;
             overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip { font-size: 10px; font-weight: 700; padding: 3px 7px; border-radius: 5px;
        text-transform: uppercase; letter-spacing: .3px; background: #e2e8f0;
        color: #475569; }
.chip-active { background: #dcfce7; color: var(--new); }
.chip-ended { background: #fee2e2; color: var(--ended); }
.copy { font-size: 12.5px; line-height: 1.45; color: #334155; white-space: pre-wrap;
        word-break: break-word; }
.cta { font-size: 12.5px; display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.cta a { font-weight: 600; }
.cta-text { font-weight: 600; color: #334155; }
.cta-dest { color: var(--muted); font-size: 11px; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; }
.badge { font-size: 10px; padding: 2px 6px; border-radius: 5px; background: #eef2ff;
         color: #3730a3; }
.foot { border-top: 1px solid var(--border); padding-top: 8px; font-size: 11px;
        color: var(--muted); display: flex; flex-wrap: wrap; gap: 10px;
        justify-content: space-between; }
a { color: #0369a1; }
.empty { color: var(--muted); padding: 40px; text-align: center; grid-column: 1 / -1; }
"""

_SECTIONS = (
    ("new", "New", "new"),
    ("changed", "Changed", "changed"),
    ("ended", "Ended", "ended"),
)


def _chip_class(status: str) -> str:
    return "chip-ended" if status.strip().lower() in {"ended", "inactive", "stopped"} else "chip-active"


def _http_url(value) -> str:
    """Return ``value`` only when it is an absolute http(s) URL, else ``""``.

    Destination links come from an untrusted page render: ``javascript:``,
    ``data:`` and relative paths must never reach an ``href``.
    """
    url = str(value or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else ""


#: Upper bound for the render's "N ads use this creative" number. A live card
#: never approaches it; clamping keeps a corrupt or hand-edited snapshot from
#: emitting a 5000-digit badge (or an int too large to stringify).
_MAX_SAME_CREATIVE = 1_000_000


def _same_creative_count(ad: dict) -> int:
    value = ad.get("same_creative_count") if isinstance(ad, dict) else 0
    try:
        if isinstance(value, float) and not math.isfinite(value):
            # JSON 1e999 decodes to inf; there is no honest integer for it.
            return 0
        count = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(count, _MAX_SAME_CREATIVE))


def _image_count(ad: dict) -> int:
    images = ad.get("images") or []
    return len(images) if isinstance(images, list) else 0


def _is_flagged(ad: dict, key: str) -> bool:
    value = ad.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _render_cta(ad: dict) -> str:
    """CTA copy plus its destination; a non-http(s) URL stays inert text."""
    cta = html.escape(str(ad.get("cta_text") or "").strip())
    title = html.escape(str(ad.get("link_title") or "").strip())
    url = _http_url(ad.get("link_url"))
    label = cta or title or html.escape(url)
    if not label:
        return ""
    if not url:
        return f'<div class="cta"><span class="cta-text">{label}</span></div>'
    attrs = f' title="{title}"' if title else ""
    dest = f'<span class="cta-dest">{title}</span>' if cta and title else ""
    return (
        f'<div class="cta"><a href="{html.escape(url, quote=True)}" '
        f'target="_blank" rel="noopener noreferrer"{attrs}>{label}</a>{dest}</div>'
    )


def _render_badges(ad: dict) -> str:
    badges = []
    same = _same_creative_count(ad)
    if same:
        badges.append(f'<span class="badge">{same} use this creative</span>')
    if _is_flagged(ad, "multiple_versions"):
        badges.append('<span class="badge">Multiple versions</span>')
    images = _image_count(ad)
    if images:
        badges.append(
            f'<span class="badge">{images} image{"s" if images != 1 else ""}</span>'
        )
    return f'<div class="badges">{"".join(badges)}</div>' if badges else ""


def _render_card(ad: dict) -> str:
    ad_id = html.escape(str(ad.get("id") or ""))
    page = html.escape(str(ad.get("page_name") or "Unknown"))
    status = html.escape(str(ad.get("status") or "unknown"))
    copy = html.escape(str(ad.get("creative_text") or "—"))
    first_seen = html.escape(str(ad.get("first_seen") or "—"))
    last_seen = html.escape(str(ad.get("last_seen") or "—"))
    url = _http_url(ad.get("library_url"))
    # Only http(s) URLs become anchors: a javascript:/data: library_url is
    # untrusted data and must stay inert text.
    link = (
        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Ad library &rarr;</a>'
        if url
        else ""
    )
    return (
        f'<div class="card" data-ad-id="{ad_id}">'
        '<div class="card-header">'
        f'<span class="chip {_chip_class(status)}">{status}</span>'
        f'<span class="card-page" title="{page}">{page}</span>'
        "</div>"
        f'<div class="copy">{copy}</div>'
        f"{_render_cta(ad)}"
        f"{_render_badges(ad)}"
        '<div class="foot">'
        f"<span>First seen: {first_seen}</span>"
        f"<span>Last seen: {last_seen}</span>"
        f"<span>#{ad_id}</span>"
        f"<span>{link}</span>"
        "</div>"
        "</div>"
    )


def _as_mapping(value) -> dict:
    """A snapshot/diff/meta payload; anything else (None/list/str) is empty.

    ``build_html`` and ``build_digest`` are public and are called directly in
    tests and by embedders, not only through ``write_report``. Normalising here
    means a ``None`` diff or metadata object degrades to "nothing to show"
    rather than raising ``AttributeError`` on ``.get``.
    """
    return value if isinstance(value, dict) else {}


def _as_partial(value) -> bool:
    """Strict partial flag: only a boolean ``True`` (or a truthy string like
    ``"true"``) counts. ``bool("false")`` is True, so a raw ``bool()`` cast
    would show the banner for the string ``"false"`` — a cosmetic false alarm.
    ``ad_check`` always passes a real bool; this guards direct API callers."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _as_list(value) -> list:
    """Diff buckets are lists; anything else (dict/str/int/None) is empty.

    Snapshots and diffs come from JSON on disk, so a hand-edited or corrupt
    file can hand us a non-list bucket. Treat it as empty rather than
    iterating a string character by character or raising.
    """
    return value if isinstance(value, list) else []


def _ad_values(ads_by_id) -> list:
    """The dict entries of an ads-by-id mapping; junk values are skipped."""
    if not isinstance(ads_by_id, dict):
        return []
    return [ad for ad in ads_by_id.values() if isinstance(ad, dict)]


def _ordered_ads(diff: dict, ads_by_id: dict) -> list[dict]:
    """Diff buckets first (new, changed, ended), then every other known ad."""
    seen = set()
    ordered = []
    for key in ("new", "changed", "ended"):
        for ad in _as_list(diff.get(key)):
            if not isinstance(ad, dict):
                continue
            ad_id = str(ad.get("id") or "")
            if ad_id and ad_id not in seen:
                seen.add(ad_id)
                ordered.append(ad)
    if isinstance(ads_by_id, dict):
        for ad_id, ad in ads_by_id.items():
            if not isinstance(ad, dict):
                continue
            if str(ad_id) not in seen:
                seen.add(str(ad_id))
                ordered.append(ad)
    return ordered


def build_html(
    query: str,
    diff,
    ads_by_id,
    meta,
    country: str = "US",
    advertiser: str = "",
) -> str:
    diff = _as_mapping(diff)
    meta = _as_mapping(meta)
    counts = {key: len(_as_list(diff.get(key))) for key in ("new", "ended", "changed")}
    total = len(_ad_values(ads_by_id))
    checked_at = html.escape(str(meta.get("checked_at") or ""))
    partial = _as_partial(meta.get("partial"))
    market = html.escape(str(country or "US"))
    target = html.escape(str(advertiser or "").strip())
    scope = f"{market} · {target}" if target else market
    banner = f"{counts['new']} new / {counts['ended']} ended / {counts['changed']} changed"
    cards = "".join(_render_card(ad) for ad in _ordered_ads(diff, ads_by_id))
    if not cards:
        cards = '<div class="empty">No ads in this check.</div>'
    partial_note = (
        '<div class="partial">Partial listing: some ads may not have been reached, '
        "so missing ids are not counted as ended.</div>"
        if partial
        else ""
    )
    # ``query``, ``market`` and ``target`` are escaped exactly once, above (or
    # here for query); escaping the composed title again would render an
    # advertiser like "A&B" as "A&amp;amp;B".
    title = f"Ad check — {html.escape(str(query))} ({scope})"
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>{title}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        '<div class="app">\n<header>\n'
        f"<h1>{title}</h1>\n"
        f'<div class="banner">{banner}</div>\n'
        f'<div class="meta-summary">{total} ads tracked · checked {checked_at}</div>\n'
        "</header>\n"
        f"{partial_note}\n"
        f'<div class="gallery">{cards}</div>\n'
        "</div>\n</body>\n</html>\n"
    )


def build_digest(
    query: str,
    diff,
    ads_by_id,
    meta,
    country: str = "US",
    advertiser: str = "",
) -> dict:
    diff = _as_mapping(diff)
    meta = _as_mapping(meta)
    digest = {
        "query": str(query),
        "country": str(country or "US"),
        "checked_at": meta.get("checked_at"),
        "partial": _as_partial(meta.get("partial")),
        "total": len(_ad_values(ads_by_id)),
        "new": len(_as_list(diff.get("new"))),
        "ended": len(_as_list(diff.get("ended"))),
        "changed": len(_as_list(diff.get("changed"))),
    }
    ads = _ad_values(ads_by_id)
    digest["with_link"] = sum(1 for ad in ads if _http_url(ad.get("link_url")))
    digest["with_cta"] = sum(
        1 for ad in ads if str(ad.get("cta_text") or "").strip()
    )
    digest["with_images"] = sum(1 for ad in ads if _image_count(ad))
    digest["with_same_creative"] = sum(1 for ad in ads if _same_creative_count(ad))
    digest["with_multiple_versions"] = sum(
        1 for ad in ads if _is_flagged(ad, "multiple_versions")
    )
    if str(advertiser or "").strip():
        digest["advertiser"] = str(advertiser).strip()
    return digest


def write_report(
    query,
    diff,
    ads_by_id,
    meta,
    out_dir=None,
    country="US",
    advertiser="",
    active_status="all",
    media_type="all",
    page_id=None,
) -> dict:
    """Write one HTML report and its digest; return their paths as strings.

    ``out_dir`` defaults to the plugin's ``reports`` directory for query +
    ``country`` (+ ``advertiser``, + filters, + ``page_id``); callers that let
    it default must pass the watch entry's market, target, filters and page
    identity so two variants never overwrite each other's artifacts. A page
    watch and a keyword watch on one query+market are separate artifacts.
    """
    meta = dict(meta or {})
    diff = diff or {}
    ads_by_id = ads_by_id or {}

    if out_dir is None:
        paths = store.report_paths(
            query,
            country,
            advertiser,
            active_status,
            media_type,
            page_id=page_id,
        )
        html_path, digest_path = paths["html"], paths["digest"]
    else:
        out = Path(out_dir)
        html_path, digest_path = out / "report.html", out / "digest.json"

    store._write_text(
        html_path, build_html(query, diff, ads_by_id, meta, country, advertiser)
    )
    store._write_text(
        digest_path,
        json.dumps(
            build_digest(query, diff, ads_by_id, meta, country, advertiser),
            ensure_ascii=False,
            indent=2,
        ),
    )
    return {"html": str(html_path), "digest": str(digest_path)}
