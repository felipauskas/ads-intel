# ads-intel enhancement plan — free Treg-grade fields

Goal: close the field/filter gap vs Treg's Meta tools WITHOUT paying anyone:
no keys, no treg calls, no third-party services, stdlib + Hermes web_extract only.
Only outbound traffic stays the single public `facebook.com/ads/library/` GET per query.

## What Treg returns that we don't (verified 2026-11-06 via `treg catalog get/call`)
Routed `treg.meta-ads.library.advertiser` (Crawl4AI/ScrapeCreators/AnyAPI/Adyntel)
and official `meta-ad-library` (`ads_archive`): page_id, page_url, page_likes,
platforms, CTA, link_url, link_title/caption, images, videos, cards, display_format,
same_creative_ads, spend/impressions (political), ISO start/end dates, plus filters
ad_active_status/media_type/publisher_platforms/date range/language/pagination.

## What the PUBLIC library markdown actually contains (fixture library_page.md)
Already rendered but currently discarded by sources.py: page link URL
(`facebook.com/nike/` or numeric `facebook.com/615…/`), creative image URLs
(scontent…600x600) vs 60x60 profile pic, CTA blocks `[title\\ CTA](dest URL)`
(e.g. Shop Now → nike.com), "**N ads** use this creative and text",
"This ad has multiple versions", "having trouble playing this video" signal.
Platform icons, page_likes, spend/impressions, video file URLs are NOT in the
public markdown render — do NOT invent/fabricate them.

## Tasks (sequential — same files, no parallel implementers)

### Task 1 — Parser field enrichment (sources.py, tests/test_sources.py)
Add to each parsed ad (backward-compatible, missing = "" / [] / None / 0, never break old snapshots):
- page_url (the facebook.com page link), page_id (numeric only, else "")
- link_url + link_title/title + cta_text from the CTA block (ignore facebook.com/help links)
- images: list of creative image URLs (exclude 60x60 profile pic), has_video: bool
  ("trouble playing this video" signal only — no invented video URL)
- same_creative_count: int from "**N ads** use this creative and text" (0 if absent)
- multiple_versions: bool ("This ad has multiple versions")
- Keep existing 7 keys unchanged. TDD: failing tests first, then parser, then suite green.

### Task 2 — Filters + diff signature (tools.py, schemas.py, diffing.py, resolve.py if needed)
- build_url/fetch_ads gain optional active_status (active|inactive|all, default all)
  and media_type (all|image|video, default all) — mirrors Treg/official API, still free URL params.
- ad_search/ad_watch accept + validate them; invalid → {"error": "invalid_…"}.
- diffing._sig includes creative_text + link_url/title + cta_text (new fields only when present in both).
- tools._SUMMARY_KEYS extended to surface new fields in ad_check summaries.
- Update schemas.py descriptions to match. TDD.

### Task 3 — Report enrichment (report.py)
- Cards show CTA + destination link (http(s) only, escaped), same_creative_count,
  multiple_versions flag, and image count (NOT <img> — report stays offline/no-external-images).
- Digest gains per-field counts if trivial; keep offline-safe invariant.
- TDD, existing render tests must still pass.

### Task 4 — Docs + full verification (README.md, docs/, plugin.yaml if needed)
- Document new fields (honest: what's from public render vs what we can't get),
  new filters, and what stays out of scope (platforms, page_likes, spend, video URLs).
- Run FULL suite: pytest -q (84 existing + new). No commits/pushes without explicit yes.

## Non-goals
No Treg/treg calls, no API keys, no cookies/login, no pagination beyond one page,
no spend/impressions, no fabricated fields.
