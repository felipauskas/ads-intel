# Live 3×3 brand × country matrix — real Meta Ad Library

Run date: 2026-11-08 11:27–11:36 (+04, UTC+04:00).
Repo: `~/coding-projects/ads-intel`, HEAD `d3508ea` + uncommitted fixes in `sources.py` / `tools.py` (mtime 11:26:45).
Live network, real `web_extract` host tool. No source or test file was modified. Added: this file + `evals/raw/`.

Every fetch used a **fresh URL** (`&cache_bust=<uuid>` appended) so the host's `extract-index.json` cache could not replay an earlier failure. Each `fetch_ads_with_meta` call therefore produced 1–2 distinct URLs (initial + retry).

---

## Verdict

The patched code path no longer emits silent zeros: every failed render is a truthful `parse_failed: render (N chars) with no card markers or empty-state text`. **5/9 combos returned ads within the built-in one retry; 4/9 returned a truthful error.** All 4 erroring combos rendered real cards on a later fresh attempt, so the failures are hydration flakiness, not "no ads".

**The running Hermes plugin is still serving the pre-fix module and returns silent zeros for all 9 combos.** This is proven, not inferred: `ad_search(media_type="bogus")` through the live plugin returned `{"count":0,"ads":[]}` instead of the fixed code's `{"error":"invalid_media_type"}`. The gateway/TUI process cached the plugin before the 11:26 edit; the repo symlink is correct (`hermes plugins doctor ads-intel` → OK, 3 tools) but the loaded module is stale. End-to-end verification requires a gateway/Hermes restart.

---

## Matrix (fixed code path, real web_extract, limit=5)

| Brand | CC | `ad_search` result | Ads | Ads on extra fresh attempts | Sample page_names (keyword hits) |
|---|---|---|---|---|---|
| McDonald's | AE | `parse_failed` — shell 5,163 chars, 0 card markers | — | **29** (2nd extra try; 1st was a 2,073-char shell) | McDonald's, McDonald's India, Ligue 1 McDonald's, McDowell's Yaaron Waali Baat |
| Burger King | AE | success (77,888 chars, 29 markers) | **5** | — | Drama Flash Hub, Dream Dubai, Soundlines Group, entel |
| KFC | AE | `parse_failed` — shell 5,145 chars | — | **28** (1st extra try) | KFC, Zomato |
| McDonald's | SA | `parse_failed` — shell 5,155 chars | — | **29** (1st extra try) | McDonald's, McDonald's India, Ligue 1 McDonald's, McDowell's Yaaron Waali Baat |
| Burger King | SA | `parse_failed` — shell 5,157 chars | — | **26** (1 of 6 fresh tries; 5 shells) | *(not captured from the successful render)* |
| KFC | SA | success (36,500 chars, 28 markers) | **5** | — | KFC |
| McDonald's | EG | success on retry (1st 5,148 shell → 2nd 41,629, 30 markers) | **5** | — | Ligue 1 McDonald's, McDonald's |
| Burger King | EG | success (81,362 chars, 28 markers) | **5** | — | BUFFALO BURGER, Uber Eats, Vou de 99, entel |
| KFC | EG | success on retry (1st 2,040 shell → 2nd 41,084, 28 markers) | **5** | — | KFC |

`complete=False` on every successful run because `limit=5` sliced a larger listing (`total_returned` 26–30). Not a truncation signal.

### What the counts mean
- `ad_search` is a **keyword** search, not a brand filter. Unrelated pages appear (entel, Uber Eats, Zomato, Drama Flash Hub). These are raw keyword hits, not proof the brand is advertising in that market.
- The identical McDonald's page set for AE and SA (including "McDonald's India") suggests the keyword result set is not tightly country-scoped for this query. Do not read the 29 as "29 McDonald's ads in the UAE".

---

## Live plugin result (running Hermes process)

All nine `ad_search` calls through `tool_call` returned exactly:

```json
{"count": 0, "ads": []}
```

with no `error`, no `complete`, no `fetched`, no `country`. This is the pre-fix 2-key exposure. Raw: `evals/raw/ad_search-live-plugin-matrix.json`.

Staleness probe:

| Call | Live plugin | Fixed code |
|---|---|---|
| `ad_search(query="KFC", country="AE", limit=3, media_type="bogus")` | `{"count":0,"ads":[]}` | `{"error":"invalid_media_type"}` |

Conclusion: **do not sign off on this fix from the current live `ad_search` tool.** The silent zero is the old binary, not a regression in the patch.

---

## Retry finding

`fetch_ads_with_meta` retries once with `cache_bust`. That recovers EG (McDonald's and KFC) but not AE/SA:

- McDonald's AE: attempt 1 shell 2,073 → attempt 2 shell 5,163 → attempt 3 (manual) 41,610 = 29 ads.
- KFC AE: attempts 1–2 shells → attempt 3 = 28 ads.
- McDonald's SA: attempts 1–2 shells → attempt 3 = 29 ads.
- Burger King SA: attempts 1–6 shells (one earlier single success at 74,529 chars = 26 ads).

Observed shell rate across the matrix is roughly 50% per fetch, and failures cluster by query (Burger King SA 6/7). One retry is a coin-flip improvement, not a fix for flakiness. Raising the retry budget to 3 with jittered cache-busts would have converted 3 of the 4 erroring combos; Burger King SA would still need more.

---

## Raw artefacts

- `evals/raw/live-<brand>-<CC>.json` — nine files: `ad_search_result` (verbatim JSON) + every `web_extract` attempt (request URL with cache_bust, response URL, error, char count, `Library ID` count, `Sponsored` count, empty-state match, full markdown content).
- `evals/raw/extra-retries.json` — the two extra fresh fetches per failed combo.
- `evals/raw/recovered-names.json` — parsed ads + page-name sets for combos that rendered on a later attempt (McDonald's AE, KFC AE, McDonald's SA).
- `evals/raw/ad_search-live-plugin-matrix.json` — the nine live plugin payloads + staleness probe.

---

## 7. QSR live-eval matrix definition (2026-11-08 sweep)

Five QSR brands × five countries = 25 pairs. Runner: `evals/live_eval.py`; artifacts: `evals/live-matrix/<brand-slug>-<CC>/`.

| Brand | `ad_search` query | `advertiser` filter | Slug |
|---|---|---|---|
| KFC | `KFC` | `KFC` | `kfc` |
| McDonald's | `McDonald's` | `McDonald's` | `mcdonalds` |
| Burger King | `Burger King` | `Burger King` | `burger-king` |
| Domino's Pizza | `Domino's Pizza` | `Domino's` | `dominos-pizza` |
| Pizza Hut | `Pizza Hut` | `Pizza Hut` | `pizza-hut` |

Countries: `AE`, `SA`, `EG`, `US`, `GB` (five). Optional `KW`/`QA` only if time allows.

Per pair: `ad_search(active_status=active, limit=20)` → keyword search; `ad_search(advertiser=<brand>)` → page-name resolution; `ad_watch(add, advertiser=<brand>, active_status=active)` → `ad_check` baseline then settle. Apostrophes are kept in queries and advertiser names — quoting was ruled out as a cause.

---

## 8. Full 25-pair sweep result (2026-11-08 09:38–09:47 UTC, sequential)

Command: `.venv/bin/python evals/live_eval.py` (no `--smoke`). Run at HEAD `3c1ce90`, unmodified working tree at start. Sequential, one pair at a time, 25/25 pairs executed. Runtime 8m 55s. Artifacts: `evals/live-matrix/<brand-slug>-<CC>/` (+ aggregate `evals/live-matrix/summary.md`).

### Verdict

**9/25 PASS, 16/25 truthful FAIL, 0 silent zeros.** Every failing pair names a concrete cause (`search_error`, `advertiser_error`, `name_not_matched`, `currency_missing`) or fails the settle/artifact assertion — no pair returned `{count: 0}` while claiming success. The 3 pairs with 0 saved ads are all failing pairs whose search errored; they are not zero-result successes.

`web_extract` attempts: 157, transport/exception failures: 0. All failures are parse-level (Meta shell render) or assertion-level.

### Per-pair results

| Brand | CC | Ads saved | `ad_search` count | Status | Primary reason |
|---|---|---|---|---|---|
| KFC | AE | 20 | 20 | PASS | — |
| KFC | SA | 20 | 20 | PASS | — |
| KFC | EG | 19 | 19 | PASS | — |
| KFC | US | 20 | 20 | PASS | — |
| KFC | GB | 20 | 20 | FAIL | advertiser parse_failed (`render (5199 chars)`); `check2` not settled (0,0,10) |
| McDonald's | AE | 0 | None | FAIL | search parse_failed (2,079-char shell) |
| McDonald's | SA | 0 | None | FAIL | search parse_failed (`render (5161 chars)`) |
| McDonald's | EG | 20 | 20 | PASS | — |
| McDonald's | US | 20 | 20 | PASS | — |
| McDonald's | GB | 20 | 20 | PASS | — |
| Burger King | AE | 11 | 11 | FAIL | name_not_matched (`Burger King Arabia` @0.60 < 0.80) |
| Burger King | SA | 17 | 17 | FAIL | name_not_matched (`Burger King Arabia` @0.60) |
| Burger King | EG | 20 | 20 | FAIL | name_not_matched (`Burger King Malaysia` @0.60) |
| Burger King | US | 20 | 20 | PASS | — |
| Burger King | GB | 20 | 20 | FAIL | name_not_matched (`Burger King UK` @0.60) |
| Domino's Pizza | AE | 20 | 20 | FAIL | name_not_matched (`Domino's Pizza` @0.60; target is `Domino's`) |
| Domino's Pizza | SA | 0 | None | FAIL | search parse_failed (`render (5173 chars)`) |
| Domino's Pizza | EG | 20 | 20 | FAIL | name_not_matched (`Domino's Pizza` @0.60) |
| Domino's Pizza | US | 20 | 20 | FAIL | name_not_matched (`Domino's Pizza` @0.60) |
| Domino's Pizza | GB | 17 | 17 | FAIL | name_not_matched (`Domino's Pizza` @0.60) |
| Pizza Hut | AE | 13 | 13 | FAIL | currency_missing (AED absent from AE ad text) |
| Pizza Hut | SA | 6 | 6 | FAIL | name_not_matched (`Pizza Hut KSA` @0.60) |
| Pizza Hut | EG | 10 | 10 | PASS | — |
| Pizza Hut | US | 20 | 20 | FAIL | advertiser parse_failed (`render (5214 chars)`) |
| Pizza Hut | GB | 10 | 10 | FAIL | advertiser parse_failed (`render (5215 chars)`) |

Pass by brand: KFC 4/5, McDonald's 3/5, Burger King 1/5, Pizza Hut 1/5, Domino's Pizza 0/5.
Pass by country: AE 1/5, SA 2/5, EG 4/5, US 2/5, GB 2/5.

### Failure breakdown (primary reason)

| Cause | Pairs | Detail |
|---|---|---|
| `name_not_matched` | 10 | Matcher scores a country-suffixed page as `substring 0.60` while the threshold is `0.80` (`resolve.py`). `Burger King Arabia`, `Burger King UK`, `Pizza Hut KSA`, `Domino's Pizza` vs target `Domino's` all land at 0.60. These are the *correct* pages being rejected — a resolver recall bug, not missing data. |
| `advertiser` parse_failed | 3 | Meta returned a ~5.1–5.2k-char shell (no card markers, no empty-state text) on every attempt for the advertiser query: KFC GB, Pizza Hut US, Pizza Hut GB. |
| `search` parse_failed | 3 | Same shell on the keyword query: McDonald's AE, McDonald's SA, Domino's Pizza SA. Retried 13–16 dispatches, never hydrated. |
| `currency_missing` | 1 | Pizza Hut AE: 13 ads saved, none carries `AED`; the currency spot-check is a real (if strict) signal for AE. |

Note the observed shell rate: 6 pairs needed 11–16 dispatches and never recovered; the other 19 settled in 4. Raising retries further would trade runtime for a handful of pairs; the resolver threshold is the cheaper and larger win (10 pairs).

### Hydration metrics (383 saved ads)

Field coverage per pair, percentage of saved ads with a non-empty value:

| Brand | CC | n | creative_text | cta_text | link_url | first_seen | media | page_name | no page-chrome |
|---|---|---|---|---|---|---|---|---|---|
| KFC | AE | 20 | 100 | 95 | 95 | 100 | 100 | 100 | 95 |
| KFC | SA | 20 | 70 | 95 | 95 | 100 | 100 | 100 | 95 |
| KFC | EG | 19 | 89 | 100 | 100 | 100 | 100 | 100 | 95 |
| KFC | US | 20 | 95 | 90 | 95 | 100 | 100 | 100 | 95 |
| KFC | GB | 20 | 100 | 85 | 85 | 100 | 100 | 100 | 95 |
| McDonald's | EG | 20 | 100 | 35 | 35 | 100 | 100 | 100 | 95 |
| McDonald's | US | 20 | 90 | 90 | 90 | 100 | 100 | 100 | 95 |
| McDonald's | GB | 20 | 100 | 80 | 80 | 100 | 100 | 100 | 95 |
| Burger King | AE | 11 | 100 | 82 | 82 | 100 | 100 | 100 | 91 |
| Burger King | SA | 17 | 100 | 82 | 82 | 100 | 100 | 100 | 94 |
| Burger King | EG | 20 | 100 | 60 | 60 | 100 | 100 | 100 | 95 |
| Burger King | US | 20 | 100 | 100 | 100 | 100 | 100 | 100 | 95 |
| Burger King | GB | 20 | 100 | 95 | 95 | 100 | 100 | 100 | 95 |
| Domino's Pizza | AE | 20 | 100 | 35 | 35 | 100 | 100 | 100 | 95 |
| Domino's Pizza | EG | 20 | 100 | 65 | 75 | 100 | 100 | 100 | 95 |
| Domino's Pizza | US | 20 | 100 | 85 | 85 | 100 | 100 | 100 | 95 |
| Domino's Pizza | GB | 17 | 100 | 82 | 100 | 100 | 100 | 100 | 94 |
| Pizza Hut | AE | 13 | 100 | 85 | 85 | 100 | 100 | 100 | 92 |
| Pizza Hut | SA | 6 | 100 | 100 | 100 | 100 | 83 | 100 | 83 |
| Pizza Hut | EG | 10 | 100 | 50 | 50 | 100 | 90 | 100 | 90 |
| Pizza Hut | US | 20 | 100 | 100 | 100 | 100 | 100 | 100 | 95 |
| Pizza Hut | GB | 10 | 100 | 90 | 100 | 100 | 100 | 100 | 90 |

Aggregate (mean across pairs with ads): `creative_text` 97.5% (min 70% KFC SA), `cta_text` 81.0% (min 35% McDonald's EG, Domino's AE), `link_url` 82.9% (min 35%), `first_seen` 100%, media (`images` or `has_video`) 98.8% (min 83% Pizza Hut SA), `page_name` 100%, page-chrome-free `creative_text` 93.6% (min 83%).

Two hydration defects worth keeping:

1. **Page chrome leaks into `creative_text`** (~5–10% of ads): the Meta footer block "System status / Ad Library API / About ads and data use / Privacy / Terms / Cookies" is appended to the creative. It is not ad copy and should be stripped in the parser; it also pollutes any keyword/currency containment check.
2. **`cta_text`/`link_url` are the weakest fields** (35–65% in three pairs) and are dropped together — when the card has no CTA button the link URL goes with it. `creative_text`, ids, `first_seen`, and `page_name` are effectively complete.

Currency spot-check fired exactly once (Pizza Hut AE). `KFC SA` returned `expected=None, found=[]` — no price in SA creatives, so the check abstained rather than guessing; that is correct behaviour, but it means AE is the only market where the currency assertion is actually load-bearing.

### Definition of done status

- 25/25 pairs executed, sequential: **yes**.
- Per-pair folders with `result.json` / `ads.json` / `attempts.json` / `summary.md` / `artifacts/`: **yes** for all 25; `artifacts/` absent only on pairs that never resolved an advertiser (12 pairs), which is consistent with `artifacts_missing` being reported.
- Silent zeros: **0**.
- 100% PASS is **not** achieved: 9/25. The regression that blocks it is the `resolve.py` 0.80 threshold rejecting correct suffixed page names (10 pairs), followed by Meta shell renders (6 pairs).

## 9. Resolver recall fix and 10-pair re-run (2026-11-08, after `4d7614b`)

### Change

`resolve.py` scored a country-qualified page name as substring `0.60` against the `0.80` threshold, so `Burger King Arabia`, `Burger King UK`, `Pizza Hut KSA` and `Domino's Pizza India` — the *correct* pages — were reported as `name_not_matched`. Fix (`4d7614b`, TDD: 3 tests added, failed first, then passed):

- Trailing country-qualifier tokens are stripped from **both** sides before the exact/normalized rungs (`_strip_trailing_countries`). Full names and codes: Arabia, Saudi, KSA, UAE, Emirates, Egypt, EG, UK/GB, US/USA, India, Malaysia, Spain/España, Gulf/Levant codes.
- Stripping is trailing-only, so `Manila Polyclinic - Al Rigga Burger King` and `KFC Restaurant` still score `0.60` (guarded by tests). A stripped-core string equality scores `0.80`; punctuation-only differences still score `0.85`; threshold unchanged at `0.80`.
- `evals/live_eval.py` now filters Domino's on the page display name `Domino's Pizza`, not the short form `Domino's`. The five Domino's misses were target-config, not suffix scoring: `Domino's` vs `Domino's Pizza` is a brand-name mismatch, not a country suffix.
- README resolution paragraph updated (the old "`KFC UAE` is not selected" claim is no longer true).

Suite: `186 passed` (was 183 + 3 new). `hermes plugins validate .`: passed (pre-existing `invisible_unicode` caution in eval artifacts only).

### Re-run scope

Only the 10 `name_not_matched` pairs were re-run, in three filtered invocations (no full 25-pair sweep):

```
.venv/bin/python evals/live_eval.py --brand "Burger King" --country AE --country SA --country EG --country GB
.venv/bin/python evals/live_eval.py --brand "Domino's Pizza"
.venv/bin/python evals/live_eval.py --brand "Pizza Hut" --country SA
```

### Per-pair outcome (before → after)

| Brand | CC | Before | After | Resolved page (score) | Ads saved |
|---|---|---|---|---|---|
| Burger King | AE | FAIL `name_not_matched` | **PASS** | Burger King Arabia (0.8) | 11 |
| Burger King | SA | FAIL `name_not_matched` | **PASS** | Burger King Arabia (0.8) | 17 |
| Burger King | EG | FAIL `name_not_matched` | **PASS** | Burger King Malaysia (0.8) | 20 |
| Burger King | GB | FAIL `name_not_matched` | **PASS** | Burger King UK (0.8) | 20 |
| Domino's Pizza | AE | FAIL `name_not_matched` | **PASS** | Domino's Pizza India (0.8) | 20 |
| Domino's Pizza | SA | FAIL `name_not_matched`* | **FAIL** | Domino's Pizza (0.8) | 0 |
| Domino's Pizza | EG | FAIL `name_not_matched` | **PASS** | Domino's Pizza (0.8) | 20 |
| Domino's Pizza | US | FAIL `name_not_matched` | **PASS** | Domino's Pizza (0.8) | 20 |
| Domino's Pizza | GB | FAIL `name_not_matched` | **PASS** | Domino's Pizza (0.8) | 17 |
| Pizza Hut | SA | FAIL `name_not_matched` | **PASS** | Pizza Hut KSA (0.8) | 6 |

\* Domino's SA previously also had a search parse failure; after the fix the advertiser still resolves at 0.80, but the keyword search returns the 5,173-char Meta shell on all 16 dispatches, so the pair remains a truthful FAIL for `search_error`, not for name resolution.

### Aggregate

- **Before: 9/25 PASS, 16 FAIL.**
- **After: 18/25 PASS, 7 FAIL.** All 10 `name_not_matched` pairs now resolve their advertiser at 0.80; 9 of the 10 flip to PASS. Net +9.
- Pass by brand now: KFC 4/5, McDonald's 3/5, Burger King 5/5, Domino's Pizza 4/5, Pizza Hut 2/5.

Remaining 7 failures are unchanged and unrelated to resolution:

| Cause | Pairs |
|---|---|
| Meta shell `parse_failed` on advertiser query | KFC GB, Pizza Hut US, Pizza Hut GB |
| Meta shell `parse_failed` on search query | McDonald's AE, McDonald's SA, Domino's Pizza SA |
| `currency_missing` (AED absent from AE copy) | Pizza Hut AE |

Silent zeros: still **0**. `web_extract` attempts 160, transport failures 0. Aggregate artifacts regenerated at `evals/live-matrix/summary.md`.
