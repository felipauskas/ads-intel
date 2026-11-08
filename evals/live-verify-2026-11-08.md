# Live verification — ads-intel fix 58877e8 (2026-11-08)

Scope: verify the "silent zero" fix (pre-hydration shell detection + cache-bust
retry + country normalization) end to end against the real Meta Ad Library.

## Headline: the gateway is NOT running 58877e8

The live `ad_search` tool (through the restarted UI) still returns the
pre-fix payload shape:

```
ad_search{query:"KFC", country:"AE"} -> {"count": 0, "ads": []}
```

The fixed handler (tools.py, 58877e8) always emits `count`, `complete`,
`fetched`, `country`, `ads`. The reply has neither `complete` nor `country`,
so it cannot be 58877e8 code — and the empty result is exactly the silent zero
the fix targets (`build_url` country filter never applied, no error surfaced).

Evidence:

| Fact | Value |
|---|---|
| Gateway PID | 70939, `hermes gateway run --external-supervisor` |
| Gateway start | **Fri Nov 6 11:23:23 2026** (`ps -p 70939 -o lstart=`) |
| sources.py mtime | **Nov 8 11:32:49 2026** (fix landed after the process started) |
| commit 58877e8 | Nov 8 11:33:29 +0400 |
| `hermes plugins doctor ads-intel` | OK (fresh import: manifest, loadable, 3 tools registered) |
| `hermes plugins validate <repo>` | Validation passed |
| load path | `~/.hermes/profiles/partner/plugins/ads-intel` → symlink to repo (correct tree) |

So the code on disk is right; the long-lived gateway holds the module it
imported on Nov 6. A gateway restart (not just a UI/session restart) is
required before any tool-level check can be trusted. The pre-fix module is the
`{"count": N, "ads": [...]}` shape introduced in d6ee5cd.

## What was verified live anyway

The fixed pipeline (`sources.fetch_ads_with_meta` + `resolve.filter_ads`)
was driven against the real Ad Library through the host `web_extract`, i.e.
the same dispatch contract the gateway uses. 9-combo matrix plus advertiser
variants, all with limit 20.

Basis "ads" = ads returned; "truthful error" = the fixed code refused to
report a confident empty listing.

### Base matrix (keyword only)

| Query | Country | Ads | Pages (sample) | total parsed | complete | outcome |
|---|---|---|---|---|---|---|
| KFC | AE | 20 | KFC, Zomato | 28 | false (sliced) | ads |
| KFC | SA | 20 | KFC, KFC Masr, Zomato | 28 | false (sliced) | ads |
| KFC | EG | 20 | KFC, KFC Masr, foodpanda | 28 | false (sliced) | ads |
| McDonald's | AE | — | — | — | — | truthful `ParseError` (shell 5163 chars, 4/4 attempts) |
| McDonald's | SA | — | — | — | — | truthful `ParseError` (shell 5155, 4/4, reproduced on retry) |
| McDonald's | EG | 20 | McDonald's, Ligue 1 McDonald's | 30 | false (sliced) | ads |
| Burger King | AE | 20 | Burger King, Burger King Arabia, +11 keyword noise | 29 | false (sliced) | ads |
| Burger King | SA | — | — | — | — | truthful `ParseError` (shell 5157, 4/4, reproduced on retry) |
| Burger King | EG | 20 | Burger King, Burger King Malaysia, +9 noise | 27 | false (sliced) | ads |

### Advertiser-filtered matrix (`advertiser` = brand)

| Query | Country | Advertiser | Ads | Resolved page(s) | total parsed | outcome |
|---|---|---|---|---|---|---|
| KFC | AE | KFC | 20 | KFC | 28 | ads |
| KFC | SA | KFC | 20 | KFC | 28 | ads |
| KFC | EG | KFC | 20 | KFC | 28 | ads |
| McDonald's | AE | McDonald's | — | — | — | truthful `ParseError` (shell on 16/16 attempts across base+advertiser, two runs each) |
| McDonald's | SA | McDonald's | 19 | McDonald's | 29 | ads |
| McDonald's | EG | McDonald's | 20 | McDonald's | 30 | ads |
| Burger King | AE | Burger King | 3 | Burger King | 29 | ads |
| Burger King | SA | Burger King | 0 | — | 26 | truthful `name_not_matched` (candidates "Burger King UK", "Burger King Arabia" @ 0.60 < 0.80) |
| Burger King | EG | Burger King | — | — | — | truthful `ParseError` (shell, 4/4, reproduced on retry) |

Retries of failures (a second full 4-attempt cycle) were run and recorded as
`*-retry.json`: all reproduced except Burger King SA (advertiser), which
hydrated on attempt 4 and then correctly reported `name_not_matched`; and
McDonald's SA, whose base run failed twice but whose advertiser run succeeded,
showing the pair can hydrate. Everything else that failed stayed failed.

## Attempt-level evidence (the fix working as designed)

76 `web_extract` attempts across the run: **63 pre-hydration shells**
(~5.1k chars, nav + country list, zero `Library ID` markers) and **13 hydrated
renders** (74k–81k chars, 26–30 cards). Typical recovered case:

```
burgerking-eg (base): attempt 0 -> 5150 chars, 0 cards (shell, cached URL)
                      attempt 1 -> 81320 chars, 28 cards  (cache_bust=...)
```

Before the fix, attempt 0's shell was parsed as a confident empty listing —
that is the silent zero. Now it raises `ParseError` and retries; the eventual
success (or the honest `ParseError` after 4 tries) is what reaches the caller.

Observed robustness limit, not a regression: only ~17% of attempts hydrated,
so 4 attempts succeed roughly half the time on a bad pair (McDonald's AE did
not hydrate in 16 consecutive attempts). If that matters, the retry budget or
the wait-for-hydration strategy is the lever; no source change was made here.

Side observation (pre-existing, outside this fix): every query returned 27–30
ads regardless of AE/SA/EG, and page names include global advertisers
(Nequi, entel, Vou de 99, Mercado Libre). The `country` parameter appears not
to narrow the keyword result set the way the docstring implies. Worth a
separate look.

## Files

Markdown: `evals/live-verify-2026-11-08.md` (this file).

Raw JSON in `evals/raw/` (each holds the full ad records, meta, resolution and
every captured `web_extract` request/response):

- `kfc-ae-limit20.json`, `kfc-sa-limit20.json`, `kfc-eg-limit20.json`
- `mcdonalds-ae-limit20.json`, `mcdonalds-sa-limit20.json`, `mcdonalds-eg-limit20.json`
- `burgerking-ae-limit20.json`, `burgerking-sa-limit20.json`, `burgerking-eg-limit20.json`
- `*-adv.json` for the nine advertiser-filtered runs
- `*-retry.json` for the five re-run failures

All zero-width and other Unicode format characters (U+200B/U+200D, U+200E/F,
U+2068/69, U+FEFF) were stripped from the raw payloads; `hermes plugins
validate coding-projects/ads-intel` now passes with no `invisible_unicode`
caution.

## Next action

Restart the gateway (`hermes gateway restart`, PID 70939) and re-run
`ad_search{query:"KFC", country:"AE"}`. Expected: `count > 0` with `page_names`
containing `KFC`, and a payload carrying `complete`/`country`. If it still
returns `{"count":0,"ads":[]}` after a true gateway restart, the plugin loader
is serving a cached copy and that is the bug to chase next.
