# Failed-pairs cross-check and classification (Tasks 1.2–1.4)

Merged record of the two lane files, plus the final per-pair verdict and the Phase B
scope decision.

**Sources (retained, not deleted):**

- [`evals/failed-pairs-treg.md`](failed-pairs-treg.md) — Treg page-liveness / page-ID
  cross-check, 3 calls, $0.00495. Raw payloads in `evals/treg-xcheck/*.json`.
- [`evals/failed-pairs-reference.md`](failed-pairs-reference.md) — reference-package
  (`~/coding-projects/marketing-engineering/packages/ad-intel`) page-ID and keyword runs,
  12 invocations, read-only.
- Frozen failed set: [`evals/failed-pairs.json`](failed-pairs.json) (8 pairs, from
  `evals/live-matrix/*/result.json` at `f740ed8`).
- Per-pair matrix artifacts: `evals/live-matrix/<pair>/{result.json,ads.json,attempts.json}`.
- Shell root cause: [`evals/d3-shell-rootcause.md`](d3-shell-rootcause.md)
  (pre-hydration snapshot; p(success) per fresh attempt = 0.34).

Repo state for every claim below: `ads-intel` at `f740ed8`, 17 PASS / 8 FAIL matrix.

---

## 1. Verdict table (all 8 pairs)

Verdict classes are the plan's three: **fetch-timing** (page identity is right, the fetch
or settle lost data), **wrong-page** (ads-intel kept a page a correct resolver would not
have kept), **genuine-absence** (the page does not serve ads for this market / is not
present in the keyword listing).

| # | Pair | Failure as recorded | Verdict | Evidence |
|---|---|---|---|---|
| 1 | `burger-king-eg` | `name_not_matched` ×4 | **genuine-absence** (in EG / in listing) | EG keyword listing: 20 ads / 17 pages, no BK Egypt page; nearest are `bkmalaysia` and `Burger King Arabia`, both name-only 0.80 candidates. Treg: only the global `burgerking` (`134615383218473`), 20 live ads, no country axis. Reference: page mode on `134615383218473` with `country=EG` → exit 2 **`NO_ROWS`**; the 5 `burgerking` rows in the EG keyword run are all `is_active: false`. Three independent tools agree the brand is active, no live EG delivery. |
| 2 | `burger-king-us` | `check2_not_settled: (6, 5, 0)` | **fetch-timing** | Identity correct in all phases: `facebook.com/burgerking/`, 9–10 ads per fetch. check1 9 new, check2 6 new / 5 ended / 0 changed within ~7 s — diff-window churn, no page ambiguity. Treg: same page ID, 20 live ads. Reference page mode: 112 ads, exit 0 (page renders and is stable). |
| 3 | `kfc-us` | `name_not_matched` ×4 | **genuine-absence in the keyword listing** — fixed by page mode | US keyword listing has a page *named* `KFC` but it is `facebook.com/KFCMexico/` (6 ads); ads-intel's slug veto correctly refused it, leaving nothing ≥ 0.80. `Saucy by KFC` is a different page. Treg: KFC's page is Malaysia (`82034284246`) — no help. Reference unfiltered keyword dump (185 rows, 49 pages) contained `facebook.com/KFC/` id `7144906559` (114 rows); page mode on it → 39 active ads, exit 0. So the page exists but the 20-ad keyword page ads-intel sees never surfaces it. |
| 4 | `mcdonalds-ae` | `check1_no_new_ads (None,None,None)`, `check2_not_settled (26,0,0)`, `artifacts_error: parse_failed` | **fetch-timing** (settle/artifact, *not* search shell) | Search phase itself succeeded (20 ads, 5 pages) and advertiser search resolved McDonald's (0.8, 20 ads: `McDonaldsUAE` 17, global 3). check1 was `skipped: true, reason: parse_failed` after 33 s → no baseline written → check2's 26 rows are all "new" by construction, so it can never settle. Shell count 16/19 attempts. Reference on `1491689481076497` (`McDonaldsUAE`): 123 ads, exit 0. |
| 5 | `mcdonalds-eg` | `search_error: dead_render: shell (5154 chars)` | **fetch-timing** | Same-run `advertiser_search` parsed 13 ads on `facebook.com/McDonaldsEgypt/`, so the page was live while `search` returned chrome-only. Treg: global `McDonalds` live (20 ads). Reference on `280155560076` (`McDonaldsEgypt`): 26 ads, exit 0. |
| 6 | `mcdonalds-gb` | `search_error: dead_render: shell (5217 chars)` | **fetch-timing** | `advertiser_search` resolved 13 ads (`McDonaldsUK` 10, `mcd` 2, global 1) in the same run. Treg: global page live. Reference on `209644529058679` (`McDonaldsUK`): 58 ads, exit 0. |
| 7 | `mcdonalds-sa` | `search_error: dead_render: shell (5161 chars)`, `check2_not_settled (None,None,None)`, `artifacts2_error: parse_failed` | **fetch-timing**, but thin market | `advertiser_search` resolved 1 ad on the global page; reference page mode on `50245567013` with `country=SA` also returns exactly **1** ad. The page/identity is right and live; the market genuinely has ~1 active ad, so a clean retry can still read empty and look unsettled. |
| 8 | `mcdonalds-us` | `search_error: dead_render: shell (5216 chars)` | **fetch-timing** | `advertiser_search` resolved 19 ads (global 17, `mcd` 2). Treg: `50245567013` = `facebook.com/McDonalds/`, 20 live ads. Reference page mode: 290 ads (289 unique), exit 0. |

**Tally: 6 fetch-timing, 2 genuine-absence (in the keyword listing / in-market), 0
wrong-page.** No pair shows ads-intel committing to a page that Treg or the reference
would have rejected. The closest call is `kfc-us`, and there the refusal of `KFCMexico`
was correct behaviour, not the defect.

### Notes that matter for honest reading

- **`mcdonalds-ae` is not a search-shell failure.** Per Task 1.1 the frozen reason is
  check1 `parse_failed` → missing baseline → check2 all-new. It is classified
  fetch-timing because the page was live and parsed in the same run, but it will not be
  fixed by a retry alone: `check1` needs a baseline before `check2` can settle. Phase B
  page mode also removes a real *identity* ambiguity here (ads-intel pools
  `McDonaldsUAE` + global + `mcdonaldshongkong` under the single name "McDonald's";
  the reference pins `McDonaldsUAE`).
- **The four shell pairs are orthogonal to search mode.** `dead_render: shell` is the
  extractor snapshotting before the results grid hydrates (same renderer for keyword and
  page URLs); `d3-shell-rootcause.md` measures p(success) = 0.34 per fresh attempt. Page
  mode cannot claim to fix these.
- **Reference "7/8 fixed" is about the reference fetcher.** Its page-mode runs render and
  parse where ads-intel's keyword URL hit a shell, but that is a different fetcher, and
  its page mode also flips `active_status=all` → `active`, so page identity and
  active-status filtering are not isolated in those numbers.
- **20-ad cap everywhere.** Every ads-intel search in the matrix is `complete: false`;
  Treg returns one page of 20. Absence in a 20-ad window is not proof of absence on Meta.

---

## 2. Treg vs reference vs ads-intel, by failure class

| Failure class | Treg | Reference package | ads-intel | What it proves |
|---|---|---|---|---|
| **Shell / settle (`mcdonalds-ae/eg/gb/sa/us`, `burger-king-us`)** | Page is live and has 20 active ads; no country field, so it says nothing about the market. | Page-ID URL renders and parses (26–290 ads); keyword mode also renders. Different fetcher, so not a like-for-like shell comparison. | `search`/`check1` returns the 5154–5217-char pre-hydration shell after up to 3 effective fresh attempts; `advertiser_search` in the *same run* parses the same page (1–19 ads). | Timing, not identity, not search mode. Retry/cache policy is the lever; page mode changes neither hydration nor settle. |
| **`name_not_matched` (`burger-king-eg`, `kfc-us`)** | Resolves exactly one page per brand — global `burgerking`, Malaysia `KFCMalaysia` — so it is a page-liveness oracle, not a market or enumeration oracle. It cannot corroborate an EG or US page either way. | No handle → stores the unfiltered keyword dump and labels it `ACTIVE` (180 rows / 103 pages for BK-EG; 185 rows / 49 pages for KFC-US), attributing the batch to the top page (`Uber Eats`). With a page ID it is decisive: BK-EG `NO_ROWS` (exit 2) vs KFC-US 39 ads (exit 0). | Refuses to guess: name ladder only reaches 0.80 siblings (`bkmalaysia`, `Burger King Arabia`) or is vetoed (`KFCMexico`). Honest, but has no way to express "this brand has a page my listing did not show". | Two different outcomes hiding under one error string: BK-EG has **no live EG delivery**; KFC-US has a **live US page missing from the 20-ad keyword window**. Only a page ID separates them. |
| **Resolver behaviour** | n/a | Ladder id 1.0 → handle 0.90 → name 0.80, no slug veto, no country-qualifier veto; numeric handle short-circuits to the page URL. | Name-only 0.80/0.85/0.60 plus slug/country veto; no page ID, no page mode (`sources.py:443` hardcodes `search_type=keyword_unordered`). | The missing capability is a **page-identity axis**, not a better name guess. Reference's no-id behaviour (whole keyword batch labelled with one page) is worse than ads-intel's refusal — do not copy it. |

---

## 3. Phase B scope decision

### 3.1 Which pairs page-ID mode fixes

Reference evidence is 7/8 page-mode runs returning ads — but the *reason* differs per
pair and only one is a true keyword-listing gap.

| Pair | Page ID | Page mode effect | Why |
|---|---|---|---|
| `kfc-us` | `7144906559` (`facebook.com/KFC/`) | **Fixed — primary acceptance pair** | Only genuine keyword-listing absence that a known ID repairs: 39 ads vs `name_not_matched`. |
| `mcdonalds-ae` | `1491689481076497` (`McDonaldsUAE`) | **Fixed for identity** (123 ads vs 20 mixed) | Removes pooling of UAE/global/HK under one name. The recorded FAIL (check1 baseline) still needs the settle fix. |
| `mcdonalds-eg` | `280155560076` (`McDonaldsEgypt`) | Ads available when render succeeds (26 vs 13) | Shell timing unchanged by search mode. |
| `mcdonalds-gb` | `209644529058679` (`McDonaldsUK`) | Ads available when render succeeds (58 vs 13) | Same; also stops `mcd`/global bleed into a UK watch. |
| `mcdonalds-us` | `50245567013` (`McDonalds`) | Ads available when render succeeds (290 vs 19) | Same; global page is the correct US identity per the library. |
| `mcdonalds-sa` | `50245567013` (`McDonalds`) | Thin but correct (1 ad) | Market is served by the global page; must not be reported as a failure of identity. |
| `burger-king-us` | `134615383218473` (`burgerking`) | Identity unchanged; not fixed | Already the right page. Needs settle/diff-window handling, not search mode. |
| `burger-king-eg` | `134615383218473` (`burgerking`) | **Not fixed — honest miss** | `NO_ROWS` on the global page with `country=EG`; live ads exist but not for EG. Must report page-found + no-country-ads, never a PASS. |

**Page IDs discovered (for Phase B and later Task 2.5):**

| Page | ID | Source |
|---|---|---|
| Burger King (global) | `134615383218473` | Treg `page_id`; confirmed by reference resolution |
| KFC `/KFC/` (US) | `7144906559` | Reference unfiltered keyword dump (114 of 185 rows) |
| McDonald's UK | `209644529058679` | Plan's captured reference URL |
| McDonald's UAE | `1491689481076497` | Reference: slug handle `McDonaldsUAE` → `resolved_id` |
| McDonald's Egypt | `280155560076` | Reference: slug handle `McDonaldsEgypt` → `resolved_id` |
| McDonald's global | `50245567013` | Treg `page_id`; `facebook.com/McDonalds/` |

KFC Malaysia `82034284246` is known but irrelevant to any failed pair (no US value).

### 3.2 Phase B acceptance criteria

1. **`kfc-us` resolves via `page_id`.** Watch `KFC/US` with `page_id=7144906559`: fetch
   uses `search_type=page&view_all_page_id=7144906559&country=US`, resolver returns the
   `/KFC/` page at 1.0, and the run yields ≥ 1 ad with no `name_not_matched`. This is the
   one pair that must go FAIL → PASS on search mode alone.
2. **McDonald's shells unchanged by design.** Any McD pair with a page ID must show the
   same `dead_render: shell` character and rate as keyword mode (same renderer,
   p ≈ 0.34/attempt). Success is "no regression in shell rate and no claim that page mode
   fixes timing", not "all five turn green". `mcdonalds-sa` may legitimately report 0–1
   ads as a thin market.
3. **No wrong-page PASS.** `burger-king-eg` with `page_id=134615383218473&country=EG`
   must report page-found + zero country ads (the `page_found` / `country_filtered` axes
   from Task 2.4), never silently resolve to Malaysia/Arabia and never PASS on sibling
   pages. Likewise no McDonald's watch may emit rows from `mcdonaldshongkong`, `mcd`, or
   the global page when a country page ID is supplied.
4. **Keyword mode byte-identical.** `build_url(query, country, limit)` with no page ID
   produces the exact current URL; the existing suite passes unmodified (507 tests at
   `f740ed8`). Page mode is additive only.
5. **IDs are caller-supplied and exact.** `page_id` must be all digits; a non-matching ID
   must not fall back to name resolution when the caller explicitly gave an ID (Task 2.2
   decision). No ID derivation from brand names — Treg/stored `resolved_id`/explicit input
   only.
6. **Dual axes documented.** Page identity (`page_id`) and delivery country (`country`)
   are separate: a country-specific page plus `country=CC` is the McDonald's UK shape; a
   global page plus `country=CC` is the US/SA shape. Different watches, different rows.

### 3.3 Explicitly out of scope

- Fixing the shell hydration race (retry/cache policy; not search mode).
- Auto-discovering a page ID from a `facebook_url` or brand name (YAGNI).
- Changing `active_status` semantics to match the reference's `active` vs `all` split
  beyond what page mode needs.
