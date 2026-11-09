# Reference study: `marketing-engineering/packages/ad-intel`

Read-only study, 2026-11-09. Source: `~/coding-projects/marketing-engineering/packages/ad-intel/`
(Playwright-based, 3 platforms, SQLite, 121 tests). Target: this plugin
(`ads-intel`, stdlib-only, `web_extract` markdown, Meta-only).

## 1. How the reference works

1. **One real browser, three libraries.** `ad_intel/engine.py:60` launches
   `chromium.launch_persistent_context` with a profile at
   `~/.hermes/browser-profiles/ad-tracker`, a desktop UA and
   `--disable-blink-features=AutomationControlled`. The page is hydrated and
   scrolled like a user's; nothing is fetched as static HTML.
2. **It does not scrape the DOM for ads.** `engine.py:193` registers
   `page.on("response")` and captures the sites' own internal JSON: Meta
   `/api/graphql/`, Google `SearchService/SearchCreatives`, TikTok
   `/api/v1/search` — each `url_pattern` plus a dotted `response_root`
   (`data.ad_library_main.search_results_connection.edges`). CSS/class churn
   cannot break it.
3. **Second capture path: server-preloaded JSON.** `engine.py:144`
   `_extract_embedded_items` regexes `<script type="application/json">` blocks,
   checks for the `search_results_connection` marker, `json.loads` them and
   recursively `find_key()`s the result set — catching hydration that happens
   before any XHR.
4. **Per-site knowledge is data.** `recipes/{meta,google,tiktok}.yaml` hold the
   entry URL templates, consent-button selectors, intercept target,
   `response_root`, scroll policy and a `field_map` of ordered fallback paths
   plus `$literal:` constants. Upstream drift is fixed by editing YAML
   (`AGENTS.md` doctrine #4), not Python.
5. **Identity is `sha256(platform:ad_id)`.** `model.py:15`. That hash is the
   `ad_raw` primary key; `_process_items` also dedupes in memory by `ad_id`
   across scrolls.
6. **Two tiers, raw is immutable.** `ad_raw.payload_json` keeps the untouched
   upstream object plus `first_seen`/`last_seen`; `v_ad_creatives_unified`
   (`store.py:73`) is a SQL **view** that `json_extract`s per-platform paths
   with `coalesce` fallbacks. Extraction can be improved without re-scraping.
   (The shipped code violates this on duplicate save — `store.py:172` rewrites
   `payload_json`; that bug is documented in the known-issues file, not fixed.)
7. **Resolution refuses to guess.** `resolve.py:37` scores candidate pages:
   numeric page_id 1.0, exact handle 0.90, normalized handle 0.88, exact name
   0.85/0.80, substring 0.70/0.60; below `META_MATCH_THRESHOLD = 0.80` it
   stores `NAME_NOT_MATCHED` with the top candidate instead of off-brand ads.
   Google resolves the legal entity (`AR…` id) through an in-page `fetch()` to
   the `SearchSuggestions` RPC, then caches it in `google_advertisers`.
8. **Pagination is a paced scroll loop.** `engine.py:369`: `scrollTo` bottom,
   sleep `max(scroll_delay_seconds, 1.0)`, stop when the collected count stops
   growing, capped by `max_scrolls` from the recipe. No page tokens.
9. **Absence is typed, never an error.** Canonical statuses `ACTIVE`,
   `NO_ROWS`, `NOT_COVERED`, `NAME_NOT_MATCHED`, `BLOCKED`, `SCHEMA_DRIFT`
   (`store.py:18`, mirrored in `references/feature_map.json`). Exit codes
   0/2/3/4/5; an expected-empty region (TikTok outside EU/DSA coverage) exits
   **0** and writes an `expected_empty=1` tombstone row. 421/429 or a
   `"system busy"` body raises `AntiBotBlockError` → exit 3.
10. **Facts, then verification.** `digest.py` emits `harvest_digest.json` —
    platform/format counts, shares, dominance order, first/last-seen span,
    per-platform status, exit codes. `verify_snapshot.py` regex-scans the
    report's prose and fails (exit 5) on any number, percentage (±0.5) or
    dominance claim that does not trace to the digest. `report_html.py` renders
    a self-contained gallery: status bar, platform/format chips, search, sort,
    modal, lazy `<img>`, 24-card cap + "load more".
11. **Offline proof.** 121 tests over golden SQLite fixtures (AI-GT1..GT4),
    the TikTok expected-empty contract, view-widening and match-threshold
    characterisation; `bench/results.md` times CLI vs agent turns (17–66s vs
    216–285s).

## 2. What to borrow

Legend: effort S/M/L; "fits" = free, no key, no browser, stdlib only,
`web_extract` transport.

| # | Borrow | Where it lands here | Effort | Fits? |
|---|---|---|---|---|
| 1 | **Canonical status vocabulary** (`ACTIVE`/`NO_ROWS`/`NOT_COVERED`/`NAME_NOT_MATCHED`/`BLOCKED`/`SCHEMA_DRIFT`/`PARTIAL`) as a closed set in the per-row digest. | `report.build_digest`, one string per watch row; `ad_check` rows already have `error`/`skipped`/`partial`, this just names them. | S | Yes — pure data. Makes "empty market" distinguishable from "we failed". |
| 2 | **Mechanical prose verification.** Light version of `verify_snapshot.py`: collect digest numbers/percentages/handles into a set, then reject any number in agent-written or generated summary text that is not in it. | New `report.verify_text(text, digest)` + a test; call it before writing any insights block. | M | Yes — stdlib regex; digest already exists. This is the strongest borrow: it stops invented "73% video" claims. Port the *idea*, not the implementation (see §3). |
| 3 | **Richer digest facts**: `format_counts` + `format_shares` + explicit `dominance` order + `first_seen`/`last_seen` min-max span. | `report.build_digest` currently has counts only; add derived shares and a date span. | S | Yes. Gives reports and any prose verifier something to cite. |
| 4 | **Status/coverage line in the report header** ("TikTok: NOT_COVERED (EU DSA Art 39) \| Meta: ACTIVE (67 rows)"). | `report.build_html` banner: it already prints `N new / N ended / N changed`; add the status bar. | S | Yes — the plugin has `partial` and `name_not_matched` to show. |
| 5 | **Page-handle / page-id matching rungs.** Reference scores numeric id 1.0 and slug 0.90 above the name ladder. | `sources._page_label_before` already parses `page_url`; `tools` resolution currently name-only (README admits "no page-id or handle matching rungs"). Add: exact numeric page_id, exact `/slug/` handle, then names. | M | Yes — card data is already there. Removes the "@kfcarabia vs @KFC" ambiguity the README flags. |
| 6 | **Small known-alias map**, like `references/feature_map.json` `known_legal_entities` (brand → canonical advertiser name per region). | A `aliases.json`-style constant: `{"kfc": {"ae": "KFC Arabia"}}` consulted when name scoring ties. | S | Yes — static data, no key. Keep it tiny and user-editable. |
| 7 | **Two-tier "keep the raw card, derive fields later".** Reference keeps `payload_json` and derives in a view. | Store the raw card text/line-block per ad in the snapshot (or only in `evals/`) so a parser fix can be replayed offline without refetching. | M | Partly — snapshots grow ~3–5x. Best scoped to eval fixtures. |
| 8 | **Append-only observation log** to get true "first observed by us" and per-ad history, which per-entry snapshots cannot give. | `store`: `observations.jsonl` (`run_ts, key, ad_id, status`), read by `ad_check` for "running since" instead of trusting the render's `Started running on`. | M | Yes — stdlib jsonl append. Highest new-signal-per-line item after #2. |
| 9 | **Recipe-as-grammar for the markdown parser.** Reference's `field_map` = ordered fallback paths + `$literal:`. | `sources.py` already hardcodes regexes/line offsets. Extract a `CARD_GRAMMAR` table (marker → extractor, ordered fallbacks) so a markup change is a table edit. | M | Yes, but only as constants — no YAML/pydantic layer. |
| 10 | **Classification of a dead render.** Reference separates anti-bot block ("system busy", 421/429) from schema drift. Plugin lumps everything into `parse_failed`. | `sources.ParseError` → typed `reason`: `shell` (pre-hydration/consent), `blocked`, `markup_changed`. | S | Yes. Lets `ad_check` say "likely rate-limited, retry later" vs "parser needs update". |
| 11 | **Golden scoreboard tests.** Golden fixture + expected row counts, asserted per scenario. | `evals/live-matrix/*/ads.json` already recorded; add an expected-counts table and assert it. | S | Yes — no new deps. |
| 12 | **Preview-vs-asset honesty** (`media.py` preview tier: a poster is tagged, never shown as the creative). | If image URLs ever reach a report, mark `poster` vs `asset`; today report is image-free by design. | S | Yes, only if that feature is added. |

Not worth borrowing: the exit-code contract (tools return JSON), the status
*derivation* engine (see §3), the 24-card cap (no images here), the scroll
pacing (no browser), the chrome/bench ops doctrine.

## 3. What must NOT be copied

- **Playwright + Chromium.** Violates no-browser and stdlib-only, adds a ~300 MB
  runtime, an async event loop, and 45–66 s per run (`bench/results.md`). The
  reference's own `2026-11-05_known-issues-playwright.md` §4 calls Chromium the
  main deployment friction.
- **The intercepted endpoints.** Meta's `/api/graphql/` needs a live session and
  a rotating `doc_id`; Google's `SearchCreatives` is positional protobuf-JSON
  (`"1"`, `"3"."1"."4"`, `"4"`) that fails silently; the `SearchSuggestions`
  resolution is an in-page **POST**, impossible through a `web_extract` GET.
  Copying any of these turns a 3-line parser into an opaque, breaking contract.
- **Persistent browser profile / automation flags / cookie consent clicking.**
  That is a logged-in-looking automation footprint. The plugin's Disclosures
  promise one read-only public GET, no cookies, no login, and the ToS paragraph
  is written around that. Borrowing the mechanics would invalidate the stated
  posture, not just the code.
- **`pydantic` + `pyyaml` recipes.** `recipes.py` exists because the reference
  runs a data-driven multi-site engine. For one source, a dict constant is the
  whole requirement; a schema layer is dependency weight with no payoff.
- **The SQLite corpus, WAL/SHM golden DBs, and the view.** Binary fixtures, a
  second storage format, and a `json_extract` view whose `coalesce` chains
  duplicate the parser in a second language. Snapshots stay JSON.
- **`get_platform_harvest_status`'s derivation logic** (`store.py:365`, ~120
  lines inferring ACTIVE/NOT_COVERED from row counts + feature map + advertiser
  cache). It encodes policy for three platforms and already has a casing bug
  (`KFC` vs `kfc` status rows, known-issues §2). Port the *vocabulary*, not the
  inference engine.
- **The raw-tier overwrite pattern.** `store.py:172` rewrites `payload_json` on
  duplicate identity — the reference's own highest-priority bug. Any "immutable
  raw" idea here must actually be append-only.
- **`verify_snapshot.py` as written.** It depends on `class="analysis-text"` /
  `<section class="analysis">` selectors that **none of the three shipped
  reports contain** (`grep -c analysis-text report_*.html` → 0 for all). It is
  effectively dead code; only the invariant (numbers must trace to the digest)
  is worth having.
- **Hotlinked creative images in reports.** Reference cards embed CDN
  `<img src>` that expire ("Media unavailable / expired CDN" is the default
  state in `report_kfc_ae.html`) and make the report call out to Facebook/Google
  when opened. This plugin's report is deliberately offline; do not import that.
- **The 5-exit-code CLI contract and the "one scrape then one Google retry"
  doctrine.** Process semantics and an agent-repair ops loop for a runtime this
  plugin does not have.
