# Treg field gap audit (Phase 0, read-only)

Audit of `feat/free-treg-fields` at commit `50e2919` ("feat: free Treg-grade
fields — 9 enriched ad fields, active_status/media_type filters (129 tests)").
Generated 2026-11-06. No code was changed by this task.

Method: read `sources.py` (`build_url` and parser), `schemas.py`, `tools.py`,
`plugin.yaml` in that order, then re-checked the only captured search URL in
`tests/fixtures/library_page.md` (line 11, duplicated verbatim at line 545).
A field is marked **free-feasible = yes** only when the fixture render or a
confirmed URL parameter carries it today; anything else is **no** with the
reason recorded. Free means: public `facebook.com/ads/library/` GET via Hermes
`web_extract`, stdlib only, no key/cookie/token, no new outbound host.

## 1. URL parameters `build_url` emits today

`build_url(query, country="US", active_status="all", media_type="all")` —
`sources.py:138-159`. Emitted in this fixed order:

| # | Parameter | Value today | Source of value | Validation |
|---|---|---|---|---|
| 1 | `active_status` | caller value; default `all` | `sources.py:121,153` | enum `all\|active\|inactive` → `ValueError("invalid_active_status")` (`sources.py:125-135`) |
| 2 | `ad_type` | **hardcoded `all`** | `sources.py:156` | none — not a function argument |
| 3 | `country` | caller value; default `US` | `sources.py:151-152` | `^[A-Z]{2}$` → `ValueError("invalid_country")` |
| 4 | `q` | caller `query`, percent-encoded | `sources.py:65-76,157` | non-empty enforced in `tools.py:93-95`, not in `build_url` |
| 5 | `media_type` | caller value; default `all` | `sources.py:122,154` | enum `all\|image\|video` → `ValueError("invalid_media_type")` |
| 6 | `search_type` | **hardcoded `keyword_unordered`** | `sources.py:158` | none — not a function argument |

Exact output (`.venv/bin/python -c "import sources; print(sources.build_url(...))"`):

```
https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&q=nike&media_type=all&search_type=keyword_unordered
https://www.facebook.com/ads/library/?active_status=inactive&ad_type=all&country=GB&q=nike&media_type=video&search_type=keyword_unordered
```

So: 6 parameters, 2 of them (`ad_type`, `search_type`) fixed constants with no
caller control. `schemas.py` exposes only `query`, `advertiser`, `limit`,
`country`, `active_status`, `media_type` (`schemas.py:27-53`); `tools.py`
validates `country`/`active_status`/`media_type` before any fetch
(`tools.py:96-104`) and never passes `ad_type`/`search_type`, which is why they
stay constants. `plugin.yaml` (v0.2.0) declares only the three tools and no
parameters (`plugin.yaml:12`).

## 2. Confirmed parameter set from the captured fixture

`tests/fixtures/library_page.md:11` (identical at `:545`):

```
[​](https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&is_targeted_country=false&media_type=all&q=nike&search_type=keyword_unordered&sort_data[mode]=total_impressions&sort_data[direction]=desc#)
```

That is the *only* distinctive query URL in the fixture (2 occurrences of
`ads/library/?active_status`, both the same line). Confirmed set — 9 keys:

`active_status` (all), `ad_type` (all), `country` (US),
`is_targeted_country` (false), `media_type` (all), `q` (nike),
`search_type` (keyword_unordered), `sort_data[mode]` (total_impressions),
`sort_data[direction]` (desc).

Compared with section 1, `build_url` **omits** `is_targeted_country` and both
`sort_data` keys, although the captured page URL proves the library accepts
them. No fixture URL carries any other filter key.

## 3. Required grep run

Command and verbatim output:

```
$ grep -o 'active_status[^&]*' tests/fixtures/library_page.md | sort -u
active_status=all
```

Matches the plan's expected single value. Supporting counts from the same
fixture settle the field questions below: 28 `**Sponsored**` markers and 28
`Library ID:` lines (`grep -c`), i.e. a full page of 28 cards, not a clipped
render.

## 4. Field-by-field gap table

Treg field list is the one recorded in `docs/plans/free-treg-fields.md:7-12`
(routed `treg.meta-ads.library.advertiser` + official `ads_archive`), which is
this repo's source of truth for the comparison.

| Treg field | ads-intel status | Free-feasible? | Evidence |
|---|---|---|---|
| `page_id` | **present** | **yes** | Parsed from numeric page URL only; vanity handles yield `""` (`sources.py:264-271,380`). Fixture has both: numeric `facebook.com/61551864263186/` at `:605`, vanity `facebook.com/nike/` at `:681`. |
| `page_url` | **present** | **yes** | Page-label link (`sources.py:241-261,379`); fixture `:605`, `:681`. |
| `page_likes` | absent | **no** | `grep -ci page_likes` = 0 and no likes/follower text anywhere in the render; numeric counts are not rendered. |
| `platforms` | absent | **no** | Fixture has the bare label `Platforms` (`:591`, repeated per card) followed by blank/zero-width lines — the icon set is lost in markdown. `publisher_platforms` also appears 0 times. Not reconstructible. |
| `CTA` | **present** as `cta_text` | **yes** | CTA block parser (`sources.py:302-335`); fixture `:639-643` (`[INSTAGRAM.COM\\ … Visit Instagram profile](http://instagram.com/sukeban_world)`), help-centre link at `:637` correctly excluded. |
| `link_url` | **present** | **yes** | Destination URL of the CTA block (`sources.py:309-314,332`); fixture `:643` (`http://instagram.com/sukeban_world`). |
| `link_title` / `caption` | **present** as `link_title` (caption+title merged) | **yes** | Text segments before the display domain (`sources.py:323-334`); fixture `:639-643`. Caption is not a separate key — one string only. |
| `images` | **present** as list of creative URLs | **yes** | `_image_urls` drops `60x60` profile pictures (`sources.py:338-347`); fixture creative `600x600` at `:687` vs profile `60x60` at `:603`. |
| `videos` (file/URL) | absent; only `has_video: bool` | **no** | Fixture carries the text marker `Sorry, we're having trouble playing this video.` (`:635`) and no video file URL or poster URL. Flag is honest; a URL would be fabrication. |
| `cards` | absent | **no** | `grep -ci cards` = 0; no carousel/card annotation in the render. |
| `display_format` | absent | **no** | `grep -ci display_format` = 0; format is implied at best (image vs video) and not stated. |
| `same_creative_ads` | **present** as `same_creative_count` (int) | **yes** | `sources.py:91-93,398-404`; fixture `**4 ads** use this creative and text` at `:763`, `**2 ads**` at `:1201`. |
| `spend` / `impressions` | absent | **no** | `grep -ci spend` = 0; `impressions` occurs only inside the `sort_data[mode]=total_impressions` URL on `:11`/`:545`, never as a card value. Political-only and not in this render. |
| start/end dates, **ISO** | **partial**: present as localized display strings, not ISO | **yes** (dates) / formatting only | `_dates` (`sources.py:224-238`) fills `first_seen`/`last_seen`; fixture `Jul 9, 2025 - Nov 21, 2025` at `:589` and `Started running on May 19, 2026` at `:941`. ISO-8601 is a local reformat of the same two strings, not new data. |
| filter `ad_active_status` | **present** as `active_status` | **yes** | `sources.py:121,153,156`; fixture `:11` `active_status=all`; schema enum `schemas.py:40-45`. |
| filter `media_type` | **present** as `media_type` | **yes** | `sources.py:122,154,157`; fixture `:11` `media_type=all`; schema enum `schemas.py:46-51`. |
| filter `publisher_platforms` | absent | **no** | No such key in the captured URL (`:11`), and platform values are not rendered (see `platforms`). Nothing to filter on. |
| filter date range | absent | **no** | No date parameter in the captured URL; no second URL exists in the fixture to confirm one. |
| filter `language` | absent | **no** | Only hit is the UI footer `[English (US)](https://www.facebook.com/language/)` at `:1995`; not a search parameter. |
| pagination / cursors | absent | **no** | No cursor/page key in the captured URL; one render = one page (`sources.py:26-33` budget + `fetch_ads_with_meta` completeness). Documented ceiling, not a fetch loop. |

Rows: 20. Every `yes` cites a fixture line or `sources.py` line.

## 5. Verdicts on the Phase 1 candidates

### `ad_type` — name confirmed, values NOT confirmed

- Name and default value are real: `ad_type=all` at fixture `:11`/`:545`, and
  `build_url` already sends it hardcoded (`sources.py:156`).
- The claimed alternates (`political_and_issue_ads`, `housing_ads`,
  `employment_ads`, `financial_products_and_services_ads`) appear **nowhere**
  in the fixture or tests. `grep -o 'ad_type=[^&]*'` returns only `ad_type=all`.
- Verdict: **not yet free-feasible as a filter.** Exposing it with only the
  confirmed `all` value adds no capability; adding the other four would violate
  the plan's evidence rule (`2026-11-06_162500-treg-parity-evals.md:13,90`).
  Needs one live URL per value before implementation.

### `search_type` — name confirmed, alternate value NOT confirmed

- `search_type=keyword_unordered` at fixture `:11`/`:545`; `build_url` sends it
  hardcoded (`sources.py:158`).
- `keyword_exact_phrase` does not appear in the fixture or tests;
  `grep -o 'search_type=[^&]*'` returns only `keyword_unordered`.
- Verdict: **not yet free-feasible as a filter.** Same rule: confirm the exact
  phrase value in a live URL before exposing it.

### `sort_data[mode]=total_impressions` + `sort_data[direction]=desc` — confirmed, unimplemented

- Both keys are present in the captured page URL (`:11`, `:545`), which is
  direct evidence the library accepts them, but `build_url` does not emit
  either. `total_impressions` never appears as a card value, so this is
  ordering only, not spend/impression data.
- Verdict: **free-feasible (yes), not implemented.** Distinct from the Treg
  "impressions" field — it must not be presented as a metric.

### `is_targeted_country=false` — confirmed, unimplemented

- Present in the captured URL (`:11`); absent from `build_url`. Semantics
  (venue-scoped targeting, not an ad filter) are unclear from the fixture, so
  treat as **free-feasible but unexplained** — do not add without a purpose.

## 6. Consequences for Phase 1 Task 1

- Only parameters with a confirmed value in a real URL may be coded. Today that
  is `ad_type` (`all` only), `search_type` (`keyword_unordered` only), and the
  two `sort_data` keys; the two filter enums the plan expected are **not**
  confirmed beyond their defaults.
- Recommended Task 1 scope: implement `sort_data[mode]`/`sort_data[direction]`
  (evidence-backed, changes ordering) and hold `ad_type`/`search_type` until a
  live capture shows at least one non-default value. If the user insists on
  shipping them, ship the parameter with the single confirmed value plus a
  documented "unverified enum" note — never invent the other values.
- No rows justify parser work: every Treg field marked `no` (platforms,
  page_likes, spend/impressions, video URLs, cards, display_format,
  publisher/date/language filters, pagination) is absent from the render or the
  URL, and must stay documented as a limitation rather than fabricated.
