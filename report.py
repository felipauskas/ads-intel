"""Single-file, offline-safe HTML report + JSON digest for one watch query.

Mechanism only: one self-contained HTML document with inline CSS, no CDN, no
external images, no scripts. Every ad is a card; every card carries its id in
``data-ad-id`` so it can be found without JS. Untrusted text (page names,
creative copy) goes through :func:`html.escape`.
"""

import html
import json
import logging
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


def _render_card(ad: dict) -> str:
    ad_id = html.escape(str(ad.get("id") or ""))
    page = html.escape(str(ad.get("page_name") or "Unknown"))
    status = html.escape(str(ad.get("status") or "unknown"))
    copy = html.escape(str(ad.get("creative_text") or "—"))
    first_seen = html.escape(str(ad.get("first_seen") or "—"))
    last_seen = html.escape(str(ad.get("last_seen") or "—"))
    url = str(ad.get("library_url") or "").strip()
    # Only http(s) URLs become anchors: a javascript:/data: library_url is
    # untrusted data and must stay inert text.
    link = (
        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">Ad library &rarr;</a>'
        if url.lower().startswith(("https://", "http://"))
        else ""
    )
    return (
        f'<div class="card" data-ad-id="{ad_id}">'
        '<div class="card-header">'
        f'<span class="chip {_chip_class(status)}">{status}</span>'
        f'<span class="card-page" title="{page}">{page}</span>'
        "</div>"
        f'<div class="copy">{copy}</div>'
        '<div class="foot">'
        f"<span>First seen: {first_seen}</span>"
        f"<span>Last seen: {last_seen}</span>"
        f"<span>#{ad_id}</span>"
        f"<span>{link}</span>"
        "</div>"
        "</div>"
    )


def _ordered_ads(diff: dict, ads_by_id: dict) -> list[dict]:
    """Diff buckets first (new, changed, ended), then every other known ad."""
    seen = set()
    ordered = []
    for key in ("new", "changed", "ended"):
        for ad in diff.get(key) or []:
            ad_id = str(ad.get("id") or "")
            if ad_id and ad_id not in seen:
                seen.add(ad_id)
                ordered.append(ad)
    for ad_id, ad in ads_by_id.items():
        if str(ad_id) not in seen:
            seen.add(str(ad_id))
            ordered.append(ad)
    return ordered


def build_html(
    query: str,
    diff: dict,
    ads_by_id: dict,
    meta: dict,
    country: str = "US",
    advertiser: str = "",
) -> str:
    counts = {key: len(diff.get(key) or []) for key in ("new", "ended", "changed")}
    total = len(ads_by_id)
    checked_at = html.escape(str(meta.get("checked_at") or ""))
    partial = bool(meta.get("partial"))
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
    diff: dict,
    ads_by_id: dict,
    meta: dict,
    country: str = "US",
    advertiser: str = "",
) -> dict:
    digest = {
        "query": str(query),
        "country": str(country or "US"),
        "checked_at": meta.get("checked_at"),
        "partial": bool(meta.get("partial")),
        "total": len(ads_by_id),
        "new": len(diff.get("new") or []),
        "ended": len(diff.get("ended") or []),
        "changed": len(diff.get("changed") or []),
    }
    if str(advertiser or "").strip():
        digest["advertiser"] = str(advertiser).strip()
    return digest


def write_report(
    query, diff, ads_by_id, meta, out_dir=None, country="US", advertiser=""
) -> dict:
    """Write one HTML report and its digest; return their paths as strings.

    ``out_dir`` defaults to the plugin's ``reports`` directory for query +
    ``country`` (+ ``advertiser``); callers that let it default must pass the
    watch entry's market and target so two variants never overwrite each
    other's artifacts.
    """
    meta = dict(meta or {})
    diff = diff or {}
    ads_by_id = ads_by_id or {}

    if out_dir is None:
        paths = store.report_paths(query, country, advertiser)
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
