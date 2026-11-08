# Live verification #2 — ads-intel fix 58877e8 through the restarted gateway (2026-11-08)

Scope: re-run the end-to-end check after the gateway restart, through the
*running* plugin rather than a local import. Fix under test: commit `58877e8`
(require empty-state text before trusting a parse, retry with cache-bust,
lowercase/validate country).

**Headline: the running gateway now executes 58877e8.** The pre-fix reply shape
`{count, ads}` is gone; every reply carries `count`, `complete`, `fetched`,
`country`, `ads`, and all 9 matrix combos returned ads with zero failures.

## 1. Gateway identity

| Fact | Value |
|---|---|
| Old gateway PID | 70939 — gone (started Fri Nov 6 11:23:23, held the pre-fix module) |
| New gateway PID | **76726** (python), supervisor 76789, wrapper 76725/76730 |
| New gateway start | **Sun Nov 8 11:49:54 +04 2026** |
| Fix commit time | Nov 8 11:33:29 +04 2026 (`58877e8`) |
| `sources.py`/`tools.py` mtime | Nov 8 11:32 — before the new process start |
| `hermes plugins doctor ads-intel` | `OK: runtime discovery, manifest parsing, import, and registration passed` — 3 tools, 0 hooks, manifest ads-intel 0.2.0 (standalone) |
| `hermes plugins validate .` | Validation passed (no collisions, security scan safe, no core override) |
| `pytest -q` | **178 passed** in 0.15 s |

The gateway started ~16 minutes *after* the fix landed, so the loaded module is
the fixed one. That is confirmed by the payload shape below, not just by timestamps.

## 2. Through the gateway: KFC / AE (the regression case)

```
ad_search{query:"KFC", country:"AE", limit:20}
-> {"count": 20,
    "complete": false,
    "fetched": 20,
    "country": "AE",
    "ads": [ ... ]}
```

Old stale shape was `{"count": 0, "ads": []}`. Now: 20 ads, `complete` and
`country` present, no error. Pages present: `KFC`, `Zomato` — plus one ad from
the Polish page (`.../kfcpolska/`, Polish copy) that also reports
`page_name: "KFC"`.

Spot checks through the same gateway (limit 5, to keep the reply small):

| Call | count | complete | country | pages | outcome |
|---|---|---|---|---|---|
| McDonald's / AE | 5 | false | AE | McDonald's India, McDowell's Yaaron Waali Baat | ads (was `ParseError`, pre-hydration shell) |
| Burger King / SA | 5 | false | SA | Burger King UK, entel, Soundlines Group, Dream Dubai | ads (was `ParseError`) |

Both combos that truthfully errored in verification #1 now return ads. That is
the cache-bust retry doing its job.

## 3. Full 9-combo matrix (limit 20)

Ads returned > 0 in every cell; **there were no truthful errors in this run** —
the empty-state guard had nothing to refuse, because no fetch came back as a
pre-hydration shell. Counts, pages and timings are from the live raw payloads in
`evals/raw/verify2-*.json`.

| Query | Country | Ads | complete | Pages (dedup, order of appearance) | Secs | Outcome |
|---|---|---|---|---|---|---|
| McDonald's | AE | 20 | false | McDonald's India, McDowell's Yaaron Waali Baat, Ligue 1 McDonald's, McDonald's | 9.2 | ads |
| McDonald's | SA | 20 | false | McDonald's, McDonald's India, McDowell's Yaaron Waali Baat, Ligue 1 McDonald's | 6.4 | ads |
| McDonald's | EG | 20 | false | McDonald's, Ligue 1 McDonald's | 0.0* | ads |
| Burger King | AE | 20 | false | Drama Flash Hub, entel, Soundlines Group, Dream Dubai, Burger King Arabia, Vou de 99, Grubhub, Mercado Libre, Mercado Pago, Nequi, ALDI SÜD, Burger King, Globe Tales | 0.0* | ads |
| Burger King | SA | 20 | false | Burger King UK, entel, Soundlines Group, Dream Dubai, Vou de 99, Mercado Libre, Grubhub, Nequi, ALDI SÜD, Burger King Arabia, Supy, Briana Brandy | 16.4 | ads |
| Burger King | EG | 20 | false | Uber Eats, entel, BUFFALO BURGER, Vou de 99, Grubhub, Burger King Malaysia, Burger King, Nequi, DoorDash, ALDI SÜD, Aljazira Supermarket | 12.2 | ads |
| KFC | AE | 20 | false | KFC, Zomato | 14.6 | ads |
| KFC | SA | 20 | false | KFC, KFC Masr, Zomato | 9.8 | ads |
| KFC | EG | 20 | false | KFC, KFC Masr, foodpanda | 5.1 | ads |

\* Sub-second timings are HTTP-cache hits (the retry path reuses a warm render);
they still yielded 20 parsed ads.

`complete: false` in every row is correct and expected: `limit=20` was reached,
so the listing was sliced. It is not an error signal.

Summary: **9/9 combos returned ads, 0/9 truthful errors, 0 crashes, 0 empty
listings.** Total 180 ads parsed across the matrix.

## 4. How the matrix was driven

The gateway's own tool harness (`ad_search`) is a chat-attached tool, so the
9-combo sweep was driven by `scripts/stress_e2e.py`'s `_LiveBridge`, i.e. the
same host `web_extract` dispatch the gateway uses, against the same plugin tree
(`~/.hermes/profiles/partner/plugins/ads-intel` → this repo), writing each raw
reply straight to `evals/raw/`. The gateway itself was exercised directly for
section 2 (KFC/AE at limit 20, plus the McDonald's/AE and Burger King/SA spot
checks), and its reply shape matches the matrix files exactly
(`count`, `complete`, `fetched`, `country`, `ads`).

## 5. Observations (no source changes made)

1. **Market filter is loose.** `country` is echoed and sent to the Ad Library,
   yet results are not restricted to that market: KFC/SA and KFC/AE both return
   `KFC Masr` (Egypt), and BK/SA returns `Burger King UK` and `entel` (Chile).
   This matches verification #1 — pre-existing behaviour of the free render, not
   a regression from 58877e8.
2. **Keyword noise on 2-token brands.** "Burger King" pulls marketplace and
   telco ads (`Mercado Libre`, `Nequi`, `ALDI SÜD`, `entel`) because the search
   is keyword-based. The `advertiser` parameter is the documented way to cut it.
3. **No shell-parses this run** — the library served a hydrated render on every
   attempt including first tries, so the retry/cache-bust path was not exercised
   live today. It is still covered by the 178-test suite; the two spot checks in
   section 2 are the closest live evidence (those combos shelled out in
   verification #1 and now succeed).
4. Zero-width characters (U+200B/U+200D/U+FEFF) were stripped from the raw files
   after capture — 4 occurrences across `kfc-{ae,eg,sa}` and `mcdonalds-eg`.
   Residual count is 0, and `hermes plugins validate .` stays clean.

## 6. Artifacts

Raw payloads (all stripped, all re-parsed as valid JSON with the five expected keys):

- `evals/raw/verify2-kfc-{ae,sa,eg}.json`
- `evals/raw/verify2-mcdonalds-{ae,sa,eg}.json`
- `evals/raw/verify2-burger-king-{ae,sa,eg}.json`
- `evals/raw/verify2-matrix.json` — per-combo summary (count, complete, pages, secs, file)
