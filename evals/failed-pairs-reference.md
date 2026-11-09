# Reference-package runs on the failed pairs

Task 1.3 evidence. Reference repo
`~/coding-projects/marketing-engineering/packages/ad-intel` was run read-only
against a throwaway DB (`AD_INTEL_DATA_DIR=/tmp/ad-intel-xcheck`); nothing in
that repo was modified. Interpreter used:
`~/coding-projects/marketing-engineering/.venv/bin/python` (the system `python3`
resolves to a Hermes venv with a broken `pydantic_core`, so `-m ad_intel.cli`
fails there with `ImportError: cannot import name 'ArgsKwargs'`).

Command shape:

```bash
AD_INTEL_DATA_DIR=/tmp/ad-intel-xcheck \
  ~/coding-projects/marketing-engineering/.venv/bin/python -m ad_intel.cli scrape \
  --brand "<BRAND>" --region <CC> --handle meta=<page_id|slug> --platform meta
```

Every run completed well inside the timeout; playback time was ~30–60 s per run
(not individually instrumented). No run was blocked (no exit 3) and none showed
schema drift (no exit 4).

## Per-pair results

| Pair | Handle passed | Mode | Resolved page (name / id / slug) | Exit | Ads stored | Reference status | ads-intel failure being checked |
|---|---|---|---|---|---|---|---|
| `burger-king-eg` | (none) | keyword | none — 103 distinct pages, no EG Burger King page | 0 | 180 | `ACTIVE` (advertiser `Uber Eats`) | `name_not_matched` |
| `burger-king-eg` | `134615383218473` | page | Burger King / `134615383218473` / `burgerking` | **2** | **0** | `NO_ROWS` | confirms genuine absence |
| `burger-king-us` | `134615383218473` | page | Burger King / `134615383218473` / `burgerking` | 0 | 112 | `ACTIVE` | `check2_not_settled: (6, 5, 0)` |
| `kfc-us` | (none) | keyword | none — 49 distinct pages; `/KFC/` present but unfiltered | 0 | 185 | `ACTIVE` (`KFC`) | `name_not_matched` |
| `kfc-us` | `7144906559` | page | KFC / `7144906559` / `KFC` | 0 | 39 | `ACTIVE` | `name_not_matched` |
| `mcdonalds-ae` | `1491689481076497` | page | McDonald's / `1491689481076497` / `McDonaldsUAE` | 0 | 123 | `ACTIVE` | shell parse / `check2_not_settled` |
| `mcdonalds-ae` | `McDonaldsUAE` (slug) | keyword + 0.90 rung | McDonald's / `1491689481076497` / `McDonaldsUAE` | 0 | 17 | `ACTIVE` | same pair, handle rung only |
| `mcdonalds-eg` | `280155560076` | page | McDonald's / `280155560076` / `McDonaldsEgypt` | 0 | 26 | `ACTIVE` | `dead_render: shell` |
| `mcdonalds-eg` | `McDonaldsEgypt` (slug) | keyword + 0.90 rung | McDonald's / `280155560076` / `McDonaldsEgypt` | 0 | 8 | `ACTIVE` | same pair, handle rung only |
| `mcdonalds-gb` | `209644529058679` | page | McDonald's / `209644529058679` / `McDonaldsUK` | 0 | 58 | `ACTIVE` | `dead_render: shell` |
| `mcdonalds-sa` | `50245567013` | page | McDonald's / `50245567013` / `McDonalds` | 0 | 1 | `ACTIVE` | `dead_render: shell` |
| `mcdonalds-us` | `50245567013` | page | McDonald's / `50245567013` / `McDonalds` | 0 | 290 (289 unique rows) | `ACTIVE` | `dead_render: shell` |

Page IDs used: `209644529058679` (McDonald's UK) came from the plan's captured
URL. `50245567013` (McDonald's global), `134615383218473` (Burger King global)
and `82034284246` (KFC Malaysia — not used) came from the Treg cross-check
payloads (`page_id` field). `1491689481076497`, `280155560076` were discovered by
running with the page slug as handle and reading `resolved_id` back from
`ad_raw`; `7144906559` (`/KFC/`) was discovered from the unfiltered KFC keyword
dump, where it carried 114 of the 185 rows.

Zero-row runs are meaningful: `burger-king-eg` with the global Burger King page
and `country=EG` returns `NO_ROWS` / exit 2, and all five `burgerking` rows the
keyword run returned for EG have `is_active: false` (expired campaigns).

## What the reference resolver does differently

1. **Two navigation modes, not one.** `recipes/meta.yaml` carries both
   - `search_url_template` — `active_status=all&q=<brand>&search_type=keyword_unordered`, and
   - `page_search_url_template` — `active_status=active&search_type=page&view_all_page_id=<id>&country=<region>&sort_data[..]=total_impressions`.
   ads-intel only has the keyword URL (`sources.py:443`), with `advertiser` applied as
   a local page-name filter afterwards.
2. **A numeric handle short-circuits the fetch.** In `commands.py`,
   `elif platform == "meta" and handle.strip().isdigit(): resolved_id = handle`
   happens *before* `engine.scrape`, so `engine.scrape` takes the
   `page_search_url_template` branch (no `q=` at all). A non-numeric handle keeps
   the keyword URL and filters afterwards.
3. **Scoring ladder** (`resolve.py`, threshold `0.80`):
   `1.0` page_id == target · `0.90` handle exact · `0.88` normalized handle ·
   `0.85` normalized name · `0.80` name exact · `0.70` handle substring ·
   `0.60` name substring · `0.0` no match → `NAME_NOT_MATCHED`.
   ads-intel scores only page *names* at `0.80/0.85/0.60` and adds a
   country-qualifier/slug veto. The reference has **no country-qualifier veto and
   no slug veto** — that is exactly why `kfc-us` resolves: with `handle=KFC` the
   `/KFC/` page scores `0.90` on exact handle, whereas ads-intel vetoed
   `KFCMexico` and then had nothing left at ≥ `0.80`.
4. **Typed statuses and exit codes** are written per `(brand, region, platform)`:
   `ACTIVE`→0, `NO_ROWS`→2, `BLOCKED`→3, `SCHEMA_DRIFT`→4, `ERROR`→5
   (`commands.py:40-44`). ads-intel reports `name_not_matched` inside a JSON error
   field rather than as a status row.
5. **No handle means no filtering at all.** The reference stores the raw keyword
   result and marks it `ACTIVE`, attributing the whole batch to the top record's
   page — `burger-king-eg` stored 180 rows labelled `Uber Eats`, `kfc-us` stored
   185 rows across 49 pages. ads-intel's `name_not_matched` is the more honest
   behaviour here, not a regression.
6. **Keyword mode includes inactive ads; page mode does not** (`active_status=all`
   vs `active`). Reference keyword counts are therefore inflated relative to page
   counts and must not be compared one-to-one (KFC US: 185 keyword rows / 39 page
   rows).

## Which failures the page-ID path fixes

| Pair | Verdict | Evidence |
|---|---|---|
| `burger-king-us` | **fixed by page mode** | 112 active ads from `burgerking` vs ads-intel's check2 drift (6 new / 5 ended / 0 changed) |
| `kfc-us` | **fixed by page mode** | 39 active ads from `/KFC/` `7144906559`; keyword-only run cannot filter it |
| `mcdonalds-gb` | **fixed** | 58 ads, exit 0 |
| `mcdonalds-ae` | **fixed** | 123 ads (handle-rung path gave only 17) |
| `mcdonalds-eg` | **fixed** | 26 ads (handle-rung path gave only 8) |
| `mcdonalds-sa` | **fixed, but thin** | 1 ad — the market is served by the global page, same as ads-intel saw |
| `mcdonalds-us` | **fixed** | 290 ads vs ads-intel's 19 in the advertiser check |
| `burger-king-eg` | **not fixed — genuine absence** | exit 2 `NO_ROWS` on the global page with `country=EG`; keyword hits are `is_active: false` |

Two caveats for the fix:

- **Page mode also changes `active_status`** (`active` vs `all`), so these runs do
  not isolate page identity from active-status filtering. They do show the page
  URL renders and parses where ads-intel's keyword URL hit `dead_render: shell`.
- **The resolver never derives a page ID from a brand name.** Every successful run
  was handed an ID (or a slug that resolved to one). The KFC US ID only surfaced
  because the *unfiltered* keyword dump happened to include `/KFC/`. A page-ID
  mode therefore needs an upstream source of IDs (Treg `page_id`, a stored
  `resolved_id`, or a Meta page-search dropdown), not just the URL builder.

## Environment notes

- Repo state: `ads-intel` at `f740ed8`; `pytest -q` → **507 passed**, 1 warning.
- Reference repo untouched (`git status` shows only the pre-existing untracked
  `2026-11-05_known-issues-playwright.md`, present before these runs).
- Scratch DB: `/tmp/ad-intel-xcheck/ad_intel.db` (`ad_raw` table holds each
  payload plus `resolved_id`).
