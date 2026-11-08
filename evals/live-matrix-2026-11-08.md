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
