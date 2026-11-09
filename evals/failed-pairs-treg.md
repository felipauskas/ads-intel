# Failed-pairs Treg cross-check (Task 1.2)

Treg answers one narrow question: **is the advertiser's page live and serving ads right
now, and what is its numeric page ID?** It has no country parameter, so it cannot answer
the question the live matrix asks (does the brand's page deliver *in this market*).

Run: `2026-11-09T16:50Z`, `treg 0.30.0`, route `treg.meta-ads.library.advertiser`
(served by `crawl4ai.meta-ads.library.advertiser`), `X-Treg-Route-Max-Cost: 0.05`.

| Brand | Call ID | Cost | Raw file |
|---|---|---|---|
| Burger King | `4728f33f7ef649e294315219757df77b` | $0.00165 | `evals/treg-xcheck/burger-king.json` |
| KFC | `6eb196366c114e1abf45e73dff7182d8` | $0.00165 | `evals/treg-xcheck/kfc.json` |
| McDonalds | `d11b1a24dd7e45b78edda624d87a4fe3` | $0.00165 | `evals/treg-xcheck/mcdonalds.json` |

Total spend $0.00495; balance `$0.9868 → $0.9819`. Stderr charge lines kept in the
matching `.err` files.

## Per-brand result

All three calls hit (`outcome: hit`, HTTP 200) and returned the default page of 20 ads.

| Brand | Ads | `count` | distinct `page_name` | distinct `page_url` | distinct `page_id` | Active | Ad `start_date` window | Other pages returned |
|---|---|---|---|---|---|---|---|---|
| Burger King | 20 | 20 | 1 — `Burger King` | 1 — `facebook.com/burgerking/` | 1 — `134615383218473` | 20/20 | 2026-09-04 → 2026-11-06 | none |
| KFC | 20 | 20 | 1 — `KFC` | 1 — `facebook.com/KFCMalaysia/` | 1 — `82034284246` | 20/20 | 2026-10-03 → 2026-11-07 | none |
| McDonald's | 20 | 20 | 1 — `McDonald's` | 1 — `facebook.com/McDonalds/` | 1 — `50245567013` | 20/20 | 2026-04-13 → 2026-11-02 | none |

Field notes:

- **One page per brand, not a mixed set.** The plan's assumption that Treg "mixes pages
  in one result set" did not reproduce: each call resolved a single advertiser page and
  returned only that page's ads. Treg is therefore *not* a page enumerator — it cannot
  tell us whether an Egypt or US page exists for these brands.
- **No market axis at all.** Every ad has `country: null`, `currency: null`,
  `spend: null`, `impressions: null`, `paid_for_by: null`. Platforms are
  facebook/instagram (McDonald's also audience_network/whatsapp/threads). Nothing in the
  payload says where an ad was delivered.
- **Page identity agrees with what ads-intel already saw.** Treg's URLs/IDs match pages
  in the live-matrix listings: `burgerking` (`134615383218473`), `McDonalds`
  (`50245567013`), and `KFCMalaysia` (`82034284246`) — the same Malaysia page that
  surfaced as a 0.80 candidate in `burger-king-eg`. So the identity axis is consistent;
  Treg's contribution is the numeric IDs for three global pages.

## Per-failed-pair verdict input

Evidence column = what the pair's own `ads.json` / `result.json` recorded in the
`f740ed8` matrix run. Verdicts below are **guesses**, labelled with confidence, not
instrumented conclusions.

| Pair | ads-intel failure | What the matrix run actually saw | Treg input | Verdict (guess) | Confidence |
|---|---|---|---|---|---|
| `burger-king-eg` | `name_not_matched` ×4 | EG keyword listing (20 ads / 17 pages) contained **no** BK Egypt page; only `Burger King Malaysia` (`bkmalaysia`) 0.80 and `Burger King Arabia` 0.80. Sibling markets do resolve to distinct pages: AE `BurgerKingArabia`, GB `burgerkinguk`, SA `burgerkingksa` | global `burgerking` page live, 20 active ads — but no country data | **genuine-absence** — no EG page/ads in the listing; a BK Egypt page plausibly exists on FB but is not in this listing | medium-low (20-ad cap, `complete=false`) |
| `burger-king-us` | `check2_not_settled: (6, 5, 0)` | Same page every phase: `burgerking`, 9–10 ads, check1 9 new, check2 6 new → 5 → 0 | `134615383218473` = `facebook.com/burgerking/`, 20 live ads — the same page | **fetch-timing** — page identity is correct; only the new-ad count is unstable across checks | high |
| `kfc-us` | `name_not_matched` ×4 | US listing pages named `KFC`: only `facebook.com/KFCMexico/` (6 ads, `page_id: ""`) plus `Saucy by KFC`. No `facebook.com/KFC`. Plan's "slug veto drops KFCMexico" confirmed | KFC's page is **Malaysia** (`82034284246`), not US | **genuine-absence** — no US KFC page in the listing; the veto of `KFCMexico` is a correct wrong-page refusal, not the bug | medium-low (20-ad cap; US page may exist unlisted) |
| `mcdonalds-ae` | `check1_no_new_ads (None,None,None)`, `check2 (26,0,0)`, artifacts `parse_failed` | `advertiser_search` in the **same run** resolved `McDonald's` with 20 ads (`McDonaldsUAE` 17, global 3); check2 found 26 | global `McDonalds` live, 20 active ads | **fetch-timing** — same-run success on the same page proves the page is live; only the keyword-search parse died | high |
| `mcdonalds-eg` | `search_error: dead_render: shell (5154 chars)` | `advertiser_search` resolved 13 ads on `facebook.com/McDonaldsEgypt/` | global `McDonalds` live | **fetch-timing** | high |
| `mcdonalds-gb` | `search_error: dead_render: shell (5217 chars)` | `advertiser_search` resolved 13 ads (`McDonaldsUK` 10, `mcd` 2, global 1) | global `McDonalds` live | **fetch-timing** | high |
| `mcdonalds-sa` | `search_error: dead_render: shell (5161 chars)`, `check2_not_settled`, `artifacts2 parse_failed` | `advertiser_search` resolved **1** ad, on the global page | global `McDonalds` live | **fetch-timing**, but see note — SA has genuinely ~1 active ad, so a retry may still read empty | medium |
| `mcdonalds-us` | `search_error: dead_render: shell (5216 chars)` | `advertiser_search` resolved 19 ads (global 17, `mcd` 2) | `50245567013` = `facebook.com/McDonalds/`, 20 live ads | **fetch-timing** | high |

### Reading of the table

- **6 of 8 failures are fetch-timing** (`burger-king-us` + all five McDonald's pairs).
  For the McDonald's five this is not speculation about the cause: the very same run's
  `advertiser_search` phase parsed the same page and harvested 1–20 ads, so the page was
  live while the keyword `search` phase returned a pre-hydration shell. Treg's 20 live
  ads on `McDonalds` are consistent but add nothing beyond that internal control.
- **2 of 8 are `name_not_matched` in markets where the listing contains no brand-market
  page** (`burger-king-eg`, `kfc-us`). In both, Treg's page is a *different market*
  (global `burgerking`, Malaysia `KFCMalaysia`), so Treg cannot corroborate either way —
  it only shows the brand is active somewhere. Best guess is genuine absence *in the
  listing*; the honest alternative is that the 20-ad cap (`complete=false` on every
  search in this matrix) truncated the page that would have matched.
- **No pair shows ads-intel keeping a wrong page** that a correct resolver would have
  fixed. `kfc-us` is the closest, and there the refusal was correct. So Treg offers no
  Phase B acceptance pair; Phase B's justification is the missing page-ID *axis*
  (identity vs country), not a demonstrated wrong-page pick.
- **Page IDs harvested for page-mode work:** Burger King `134615383218473`, McDonald's
  `50245567013`, KFC `82034284246` (Malaysia — *not* a US ID). For `burger-king-us` and
  the McDonald's pairs these IDs are the right page identities for the *country* under
  test only in the sense that the page is the one the library serves; whether it delivers
  in AE/EG/GB/SA/US is still only answerable through `country=`.

## Caveats

- One call per brand, default page size 20, no pagination; `count` equals the number of
  ads returned, so 20 is a page size, not a total.
- Treg has no country parameter and its ads carry no country/delivery fields; treat it as
  a page-liveness and page-ID oracle only.
- The ad library changes between runs; the matrix artifacts are from `f740ed8` and the
  Treg calls are ~8h later.
- Raw payloads keep the full `output`/`raw`/`_treg` envelope, so every claim above is
  re-derivable from `evals/treg-xcheck/*.json`.
