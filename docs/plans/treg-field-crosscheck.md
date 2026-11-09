# Treg output vs ads-intel extraction — field-level cross-check

Source data: `treg-xcheck/{burger-king,dominos-pizza,kfc,mcdonalds,pizza-hut}.json`,
20 ads each (100 total), served by `crawl4ai.meta-ads.library.advertiser`,
$0.00165/call, captured 2026-11-09. ads-intel side: `sources.py` (parser),
`tools.py` (`_SUMMARY_KEYS`), sample `evals/live-matrix/kfc-sa/ads.json`.

## 1. Field-level table

Fill-rate = non-null/non-empty occurrences across the 100 Treg ads.
"render" = present in the public markdown render; "provider" = only visible to
a paid renderer/browser (icons, counters, signed video CDN URLs).

| Treg field | Treg fill | ads-intel field | ads-intel status | source |
|---|---|---|---|---|
| `ad_archive_id` | 100/100 | `id` | ✅ parsed | render |
| `ad_url` | 100/100 | `library_url` | ✅ constructed | render |
| `body` | 99/100 | `creative_text` | ✅ parsed | render |
| `title` | 92/100 | `link_title` | ✅ parsed | render |
| `cta` | 99/100 | `cta_text` | ✅ parsed | render |
| `cta_type` (`ORDER_NOW`) | 99/100 | — | ❌ dropped (derivable) | render (owner of `cta`) |
| `link_url` | 100/100 | `link_url` | ✅ parsed | render |
| `link_caption` (`bk.com`) | 100/100 | — | ❌ **explicitly discarded** (`sources.py:428`) | render |
| `images[]` | 74/100 | `images[]` | ✅ parsed | render |
| `is_active` | 100/100 | `status` (active/ended) | ✅ parsed | render |
| `start_date` (ISO Z) | 100/100 | `first_seen` (local "Oct 22, 2026") | ⚠️ parsed, not ISO | render |
| `end_date` (ISO Z) | 0/100 | `last_seen` | ⚠️ parsed, not ISO | render |
| `page_name` | 100/100 | `page_name` | ✅ parsed | render |
| `page_url` | 100/100 | `page_url` | ✅ parsed | render |
| `page_id` | 100/100 (numeric always) | `page_id` | ⚠️ empty for vanity URLs (`/kfcarabia/`) | provider (numeric id not in render) |
| `same_creative_ads` | 65/100 | `same_creative_count` | ✅ parsed (0 when absent) | render |
| `cards[]` (per-card body/cta/image/link/title/video) | 58/100 ads have ≥1 | — | ❌ flattened to first CTA block + flat `images` | render |
| `display_format` (`dco`57 `image`26 `video`15 `carousel`1 `multi_images`1) | 100/100 | — | ❌ dropped, 87% inferable from `images`+`has_video` | render (inferable) |
| `videos[]` (signed CDN URL) | 34/100 | `has_video` (bool) | ⚠️ bool only, no URL | provider |
| `page_likes` | 100/100 | — | ❌ unreachable | provider |
| `platforms[]` | 100/100 | — | ❌ unreachable — render has the word "Platforms" and no icons | provider |
| `spend` | 0/100 | — | not a real loss | political/EU only |
| `impressions` | 0/100 | — | not a real loss | political/EU only |
| `currency` | 0/100 | — | not a real loss | political/EU only |
| `paid_for_by` | 0/100 | — | not a real loss | political/EU only |

ads-intel also has `multiple_versions` (18/20 on kfc-sa), which Treg's advertiser
endpoint does not return at all — the one field ads-intel wins.

## 2. Free wins — already in the public render, dropped by ads-intel

1. **`link_caption`** — the display domain is rendered as the first CTA segment
   (`[Shop Now \ nike.com](https://…)`) and `_cta_fields` deletes it on purpose
   for being `AD.DOUBLECLICK.NET`-shaped. 100/100 in Treg, 0 in ads-intel. One
   line: keep the first segment as `link_caption` instead of dropping it.
2. **`cta_type`** — pure normalization of `cta_text` (`Order Now` → `ORDER_NOW`),
   99/100 in Treg. Cheap enum, useful for filtering "order" vs "learn more".
3. **`display_format`** — 87/100 reconstructable from `images`+`has_video` alone
   (`images==0 & has_video → video`; `images>=2 → dco|multi_images`;
   `images==1 → image`; the 13 misses are video-only DCO, which need card
   grouping). 100/100 reconstructable if `cards[]` grouping is added.
4. **`cards[]` grouping** — 58/100 Treg ads have 2–9 cards (median 3), which is
   exactly the DCO set. The render already contains each card's image + CTA +
   title in sequence; ads-intel keeps only the first CTA block and a flat image
   list, so per-card (ad variant) attribution is lost.
5. **ISO dates** — `start_date` is `2026-10-19T07:00:00Z`; ads-intel keeps the
   render's `Oct 19, 2026`. Reformatting is free and makes diffing/ordering sane.

## 3. Provider-only — unreachable without a paid key/browser

Verified from the data, not assumed:

- **`page_likes`** 100/100 numeric (BK 8,358,861 … McDonald's 82,197,917). No
  like counter exists in the markdown render (`_NOISE_LINES` has no such line,
  fixture has none).
- **`platforms`** 100/100 (`["facebook","instagram"]`, 3 ads add
  `audience_network,whatsapp,threads`). The render emits a bare `Platforms`
  label with icon glyphs that markdown extraction strips — see
  `tests/fixtures/library_page.md:591`.
- **`videos[]`** 34/100 `video-*.xx.fbcdn.net` URLs; the render only yields the
  "Sorry, we're having trouble playing this video." marker, which is what
  `has_video` uses. Also **ephemeral**: every media URL carries `oe=` (hex
  expiry), e.g. `oe=6AF746DD` = 2026-11-13 17:20 UTC — ~4.4 days after capture.
  Image URLs have the same expiry, so any stored Treg image/video URL rots.
- **numeric `page_id` for vanity URLs** — `/burgerking/` → `134615383218473` is
  not derivable from the render; ads-intel gets `page_id` only when the page URL
  is already numeric (`facebook.com/615…/`).

Not losses: `spend`, `impressions`, `currency`, `paid_for_by` are null in
100/100 Treg ads for commercial advertisers (political/EU-only fields). Treg
would not have passed the Pizza Hut AE `currency_missing` check either.

## 4. Data-quality notes

- **Exactly 20/20/20/20/20 ads.** `output.count == len(output.ads) == 20`.
  Warning line: `ALL · active · 20 ad(s) · one view · direct`, `pages_fetched`
  5–6. Strongly suggests a fixed 20-ad ceiling (one results view), the same
  top-N window ads-intel sees. No pagination, no `has_more`.
- **No country parameter at all.** Zero occurrences of "country" in all five
  files; no country/market field in output. The endpoint resolves a page by
  name globally (`verified or has the most likes`), so Treg is market-blind.
  Consequence, visible in the data: KFC → `/KFCMalaysia/` (61.7M likes),
  Pizza Hut → `/PizzaHutEgy/` (32.6M), i.e. not the US pages.
- **Mixed pages inside one result set.** Domino's returns 17 ads from
  `/Dominos/` (22,420,092 likes), 2 from `/RealPrestonPlayz/` (607,699) and 1
  from `/61575502537640/` (2,113) — while `page_id` (6657899956) and `page_name`
  ("Domino's Pizza") stay constant for all 20. So Treg's page fields are
  request-scoped, and `page_likes` is the only tell that the set is polluted.
- **"ALL" behaves as active-only**: `is_active` is `true` for 100/100 ads and
  `end_date` is null 100/100. Either the render only showed active ads or the
  parser keeps only active — unverified, but it means Treg cannot be used to
  detect *retirements* in the way `ad_check` does.
- **Date ranges are sane and ISO**: BK 09-04→10-26, Domino's 10-26→11-02,
  KFC 10-03→10-30, McDonald's 04-13→11-02, Pizza Hut 10-16→10-25 (all 2026).
- **Cost/shape**: 1 call, 6 scrape units, ISP proxy, 2.5–5.2 s (0 ms on cache
  hit), `partial: false`, `llm_calls: 0`. `raw.rows` duplicates `output.ads`
  byte-for-byte, so the payload is ~2× redundant (144–207 KB/file).

### The 10 failed D3 pairs — what Treg says

All ten fail on the *render*, not on page existence. Nine of ten show the
5,154–5,219-char pre-hydration shell (`parse_failed: … no card markers`),
the exact failure `sources.py` already classifies correctly.

| Brand | Failed pairs | Treg evidence | Verdict |
|---|---|---|---|
| Burger King | US (5218ch), GB (5219ch), AE (search 5171ch, advertiser resolved "Burger King Arabia", 2 ads), EG (`name_not_matched`) | Page `facebook.com/burgerking`, id 134615383218473, **8.36M likes, 20/20 active** | Page exists and is heavily active → BK US/GB are render-timing failures. BK-EG is genuinely unresolved: Treg's hit is the global/US page, so it neither confirms nor denies an EG page |
| Domino's | SA (search 5173ch, advertiser resolved, 7 ads) | 20/20 active; 3 pages mixed in one set (see above) | Page exists, ads active; SA failed only in the *search* fetch, the advertiser path worked (7 ads) |
| McDonald's | AE (search 5169ch, advertiser 20), SA (watch/artifacts parse_failed), EG (search+advertiser 5154ch), US (watch/artifacts parse_failed) | Page `facebook.com/McDonalds`, 50245567013, **82.2M likes, 20/20 active**, ads back to 2026-04-13 | Strongest case that these are render failures: 4 of 10 D3 failures, page demonstrably live |
| Pizza Hut | AE (`currency_missing: AED absent`, 10 ads, `complete: true`) | 20/20 active (Egypt page, 32.6M likes) | Not a fetch failure at all — the currency heuristic is the bug; Treg has `currency` null 100/100 and would fail the same check |

Caveat: Treg answers "does this brand run ads somewhere", never "in market X".
For the EG/SA/AE pairs it cannot be used as a per-market oracle.

## 5. Cost / coverage trade-off

- Treg: 1 call = 20 ads = $0.00165. Whole 25-pair matrix = **$0.0413/run**;
  daily for 30 days = **$1.24**. Latency 2.5–5.2 s/call, 6 scrape units.
- ads-intel: $0, but 10/25 pairs fail (40%) and the matrix burns 210
  `web_extract` attempts (8.4/pair) to get there.
- Treg adds exactly 6 usable fields ads-intel lacks — `page_likes`,
  `platforms`, video URLs, numeric `page_id`, `link_caption`, `cta_type` — of
  which the first three are provider-only, and 4 of the 6 are null or derelict
  within days.
- Hybrid that pays off: **keep Treg out of the field path** (add the §2 free
  wins instead) and spend it only as a *page-existence oracle* on render
  failures — 10 calls = $0.0165 per matrix run, replacing a re-fetch loop that
  currently fails anyway. Do not put it in the watch path: no country, mixed
  pages, active-only, and 20-ad ceiling make it worse than the failed fetch it
  would replace.
