# ads-intel — catalog submission (PR body)

Repo: **https://github.com/felipauskas/ads-intel** (public). Catalog entry:
`plugin-catalog/ads-intel.yaml`, proposed in a PR against
`NousResearch/hermes-agent`. The plugin is not yet in the catalog, so the install
line below targets the repo identity, not a catalog name.

---

## What it does

`ads-intel` is a free, local, zero-API-key **competitive ad intelligence** plugin for
Hermes. It reads Meta's public Ad Library and exposes three tools:

| Tool | Purpose |
| --- | --- |
| `ad_search(query, limit, country, advertiser, active_status, media_type, page_id)` | Show who is running ads for a brand, advertiser or keyword — or one Page's own listing when a numeric `page_id` is given. |
| `ad_watch(action, query, country, advertiser, active_status, media_type, page_id)` | Track a competitor or keyword over time (`add` / `remove` / `list`). |
| `ad_check()` | Diff every watch against the last snapshot: new, ended, changed ads, plus an HTML report + JSON digest. |

Typical use: find a competitor's live creative, then get a weekly "what launched,
what stopped, what copy changed" diff without a paid ad-intel subscription.

## Hermes surfaces used

- **Tools only.** Three `provides_tools` entries, no slash commands, no hooks, no
  background jobs, no MCP server.
- **`ctx.dispatch_tool("web_extract", ...)`** — the only network path. A read-only
  GET per fetch to `https://www.facebook.com/ads/library/...`, performed by Hermes'
  built-in extractor, not by a bundled HTTP client. Normally one request per query;
  when a render fails to parse, the query is retried with a cache-busting parameter,
  for at most 6 attempts in total within a 60-second wall-clock cap (a transport
  failure is retried once).
- **`plugin_data_dir("ads-intel")`** — the only filesystem path. No paths outside it
  are read or written.
- Standard library only: `python_dependencies: []`, `capabilities: []`.

## Rule-13 disclosures

**Network host**

`www.facebook.com` (Meta Ad Library), one GET per fetch attempt, only while a tool
runs. Normally that is a single request per query; up to 6 attempts are made only
when a render fails to parse, each retry carrying a cache-busting query parameter,
and the whole retry loop stops at a 60-second wall-clock cap.
No other host is contacted; nothing is fetched while idle; no telemetry, no
analytics, no third-party API.

**Filesystem paths** (all under `plugin_data_dir("ads-intel")`)

| Path | Contents |
| --- | --- |
| `watchlist.json` | Tracked `{query, country}` entries (plus `advertiser` and any non-default `active_status` / `media_type`). |
| `snapshots/<sha1>.json` | Last-seen ads per `(query, country, advertiser, active_status, media_type)` key: id, page name, status, dates, creative text and the render-derived fields. |
| `reports/<sha1>.html` | Self-contained HTML report (`report.html` layout): inline CSS, no CDN, no scripts, no external images. |
| `reports/<sha1>.digest.json` | Machine-readable counts for the same run. |

Snapshot and report filenames hash the `(query, country, advertiser, active_status,
media_type)` key, so markets, filter slices and filtered/unfiltered views never
share an artifact. Untrusted page names and
creative copy are HTML-escaped; only `http(s)` URLs become links.

**Credentials**

No credentials. No API key, token, cookie, login, OAuth flow or environment variable
is required, read or stored. There is no account to create.

**Terms of service posture**

The plugin reads Meta's *public* Ad Library — no login, no cookies, no logged-in
scraping, no pagination, one sequential request per query in the normal case (a
parse failure may add up to 5 cache-busted retries, 6 attempts maximum, under a
60-second wall-clock cap).
**Meta's terms do not authorise automated collection of the Ad Library, and this
plugin does not claim such authorisation.** It is a low-rate read-only client for
personal, small-scale research; the user is responsible for their own compliance.
This is disclosed in the README under "Terms of service posture" as well.

## Install + validate

Published at **https://github.com/felipauskas/ads-intel**. Not in the catalog yet,
so install by repo identity:

```bash
hermes plugins install felipauskas/ads-intel --force
hermes plugins enable ads-intel
```

From a checkout you can run the manifest + tool-schema check without installing:
`hermes plugins validate .`.

**No `--force` is required for the shipped tree.** The shipped tree validates
with a clean security scan (see below), so a normal install completes
non-interactively. Install still prints `Warning: custom (unreviewed) source —
not from the Hermes catalog.` because the source is not catalog-reviewed; it is
not a warning-free install, but it is not blocked.

`--force` is needed only for an older tree that still tracks the eval evidence.
The captured renders (`evals/raw/`, `evals/live-matrix/`,
`evals/page-mode-verify/`, `evals/treg-xcheck/`) are now untracked via
`.gitignore`; `hermes plugins install` clones the git tree, so they never reach
the install scan. A tree from before that change, or any tree that still tracks
them, carries Arabic ad copy with invisible directional marks and scans as
`caution`; a non-interactive install then treats community source + caution as
**Blocked** and exits 1 rather than asking (`Decision: BLOCKED — Blocked
(community source + caution verdict). Use --force to override.`). In a real
terminal it blocks only until the `[y/N] "install anyway?"` prompt; `--force`
answers it up front, accepting the verdict rather than silencing it.

Validation on the shipped tree (`hermes plugins validate .` on a fresh clone,
verified 2026-11-09, Hermes v0.23.0): every check passes, the security scan is
`safe`, and the command ends in `Validation passed.` One informational notice
remains and is quoted below rather than hidden:

```text
✓ security scan — safe
◇ Isolation — in-process only: evals/live_eval.py:202 patches tools.store._data_dir (a Hermes module attribute; the host's copy is not the one Hermes runs); scripts/stress_e2e.py:242 patches tools.store._data_dir (a Hermes module attribute; the host's copy is not the one Hermes runs)
Validation passed.
```

Local working checkouts can differ, and this is expected. The evidence dirs are
regenerable, not shipped: on a checkout that has re-run
`.venv/bin/python evals/live_eval.py` and `evals/failed_pairs.py`, those
untracked renders exist on disk, so `hermes plugins validate .` against the
working directory reports a `caution` verdict with 29 `invisible_unicode`
findings (Hermes v0.23.0) — 18 in `evals/live-matrix/dominos-pizza-us/ads.json`,
5 in `evals/live-matrix/dominos-pizza-us/artifacts/html.html`, 2 in
`evals/page-mode-verify/rerun-burger-king-us.json` and 4 in
`evals/page-mode-verify/rerun-mcdonalds-eg.json`. All 29 are invisible
directional marks in Arabic ad copy; **none are in plugin code** or in the
modules Hermes loads (`sources.py`, `tools.py`, `store.py`, `report.py`,
`resolve.py`, `diffing.py`, `schemas.py`, `__init__.py`, `plugin.yaml`). Because
the evidence is untracked, a fresh clone — what a reviewer or catalog install
actually receives — contains none of it and validates clean.

The isolation note is informational: the offline eval and stress harnesses patch
`tools.store._data_dir` to use a temp directory.

## Demo note

```text
ad_search  query="linear.app" country="US" limit=10
ad_watch   action="add" query="linear.app" country="US"
ad_check
```

The first `ad_check()` after a watch is added seeds the baseline and reports every
ad as `new`; the next run reports real diffs. `ad_check` returns artifacts
(`{html, digest}` paths under `reports/`). Expect `partial: true` on broad keyword
watches with 20+ live ads — endings for ids missing from the clipped page are
suppressed rather than guessed, while status flips that did render are still reported.

## Limitations a reviewer should know

- Keyword search, not a brand filter: `advertiser` narrows results by scoring page
  names only (`0.80` exact or trailing-country-qualified, `0.85` normalized
  ceiling, `0.60` substring). With `country` set, a page that explicitly names
  another market is vetoed before ranking; equal scores are broken by the
  requested market, then by an exact name. A tie that survives both returns
  `name_not_matched` with `ambiguous: true` and the tied candidates — never a
  guess, and never keyword noise.
- **Page mode is fetch-exact, identity resolves through the listing.** `page_id`
  (digits only) sends Meta's own Page-search URL (`search_type=page&view_all_page_id=<id>`,
  no `q=`) and `country` stays a separate delivery axis — a country-specific Page
  plus its market (`209644529058679` + `GB`) and the global Page plus a market
  (`50245567013` + `US`) are different watches. Results add `page_found` and
  `country_filtered`. The listing itself is the identity: when its cards all share
  one `page_url` slug, that slug resolves the requested ID at `1.0` even though the
  cards carry no numeric `page_id` (KFC-US: 27 ads, `page_found: true`;
  `evals/page-mode-verify/rerun-*.json`). Honest residual: a listing whose cards
  name more than one slug still reports `name_not_matched` rather than guessing,
  and a card with no usable `page_url` is kept on the resolved listing identity
  with a possibly empty `page_name` (no silent ad loss).
- Result pages are clipped at `char_limit=120000`; a clipped or limit-sliced fetch
  is partial, and partial runs suppress endings for ids missing from the clipped
  page while still reporting status flips on ads that did render. An `advertiser`
  watch resolves the page name against the whole rendered page — no result-limit
  slice — before filtering, so a brand page anywhere in the rendered keyword hits
  is found and all of its ads in that window are tracked. That is still
  rendered-window semantics: the library's URL filters narrow what renders, the
  120,000-character budget can clip it, and Meta's render is only the top of the
  result set, so absence from the window proves nothing about the full listing.
- A markup change on Meta's side surfaces as `parse_failed` (search) /
  `reason: "parse_failed"` (check) instead of a false "all ads ended".
- No pagination in v1: one page per watch. Unfiltered `ad_check` keeps the first
  20 ads; an `advertiser` watch keeps every ad on the resolved page.

## Addendum 2026-11-06 (free field enrichment, Tasks 1–4)

The argument table above still names the original three arguments; this addendum
records what the same three tools now return without adding a surface.

- **New per-ad fields, all from the public render:** `page_url`, `page_id`,
  `link_url`, `link_title`, `cta_text`, `link_caption`, `cta_type`,
  `display_format`, `cards`, `images`, `has_video`, `same_creative_count`,
  `multiple_versions` — the full 20-key set is `id`, `page_name`, `status`,
  `first_seen`, `last_seen`, `creative_text`, `library_url`, `page_url`,
  `page_id`, `link_url`, `link_title`, `cta_text`, `link_caption`, `cta_type`,
  `display_format`, `cards`, `images`, `has_video`, `same_creative_count`,
  `multiple_versions`. Missing values are `""` / `[]` / `0` / `false`; the
  original seven fields are unchanged. `link_caption` is the domain the CTA block
  prints (not necessarily the link URL's host), `cta_type` is `cta_text` as an
  upper-snake enum, `display_format` is `image` / `video` / `dco` inferred from
  the rendered media (`carousel` is never claimed), and `cards` is the per-card
  grouping with `video` always `null` (no video file URL renders).
- **New optional filters:** `active_status` (`all|active|inactive`) and
  `media_type` (`all|image|video`) on `ad_search` and on `ad_watch add`. They are
  query-string parameters on the same single `www.facebook.com` GET, stored on the
  watch entry when non-default, and each filtered watch keeps its own snapshot and
  report key. Invalid values return `invalid_active_status` / `invalid_media_type`.
- **`ad_check` and reports:** the changed-ad signature now includes `link_url`,
  `link_title`, `cta_text`, `link_caption`, `cta_type` and `display_format`
  (compared only when both the old and new record carry them). Bucket summaries
  include the new fields. HTML cards show the CTA and destination link (absolute
  `http(s)` only) plus creative-grouping and image-count badges; the digest adds
  `with_link`, `with_cta`, `with_images`, `with_same_creative`,
  `with_multiple_versions`.
- **Still absent, deliberately:** `platforms` (publisher placements),
  `page_likes`, `spend`, `impressions` and direct video file URLs are not in the
  public logged-out render and are not returned, estimated or sourced elsewhere.
  `has_video` is only the render's video-playback signal.
- **Invariants unchanged:** no key, account, cookie, third-party service or extra
  host; one read-only GET per query in the normal case (up to 6 attempts only when
  a render fails to parse, each retry cache-busted, inside a 60-second wall-clock
  cap); stdlib only;
  `plugin_data_dir("ads-intel")` is still the only filesystem path. Suite: **470
  passed** (`.venv/bin/python -m pytest tests -q`). `hermes plugins validate .`
  passes; at the time it carried an `invisible_unicode` caution from eval data,
  which has since been untracked — see the 2026-11-09 addendum on the clean
  shipped tree.

## Addendum 2026-11-09 (Page search mode)

- **`page_id` on `ad_search` and `ad_watch add`.** A numeric Meta Page ID
  (ASCII digits only; anything else returns `invalid page_id`) switches the fetch
  from keyword search to Meta's Page search:
  `search_type=page&view_all_page_id=<id>` with no `q=` parameter. `query` still
  names the watch but is not sent to the library. Snapshots and reports key on
  `page_id` as well, so a keyword watch and a page watch on one query never share
  a baseline.
- **Two axes, not one.** Page identity (`page_id`) and delivery market (`country`)
  are independent: `209644529058679` + `GB` is McDonald's UK's own Page in the UK
  library; `50245567013` + `US` is the global McDonald's Page read in the US
  library. Page-mode rows add `page_found` and `country_filtered` so a miss states
  which axis failed instead of a bare `name_not_matched`.
- **Keyword mode is unchanged** and remains the lead-generator path: byte-identical
  URL, same name ladder and vetoes, same snapshots. Use `advertiser` for a
  name-scoped watch and `page_id` when the exact Page is known.
- **Listing-identity resolution shipped.** Live verification on the six
  failed-pair Page IDs (KFC US, both Burger King, four McDonald's) had shown the
  page-mode fetch is exact — every render was the requested Page's listing — while
  resolution reported `name_not_matched` because cards expose vanity `page_url`s
  and the per-ad `page_id` is only derived from a numeric URL. The fix treats the
  listing itself as the identity: a single `page_url` slug across the cards
  resolves the requested ID at `1.0`, so KFC-US now returns 27 ads with
  `page_found: true` (`evals/page-mode-verify/rerun-kfc-us.json`). Residual, kept
  honest: a listing whose cards name more than one slug still misses rather than
  guesses. The one honest country miss stays unchanged (`burger-king-eg`:
  `page_found: false`, `country_filtered: true` — the EG listing is empty, not a
  resolver failure). Evidence: `evals/failed-pairs-crosscheck.md` §4 (historical
  `FAILED` record, not rewritten) and §5 (dated rerun pointer),
  `evals/page-mode-verify/`.
- **Suite: 575 passed** (`.venv/bin/python -m pytest tests -q`), superseding the
  count in the 2026-11-06 addendum above. `hermes plugins validate .` passes on
  the shipped tree with a **clean** security scan (`✓ security scan — safe`, no
  findings); only local working checkouts that regenerate the untracked evidence
  dirs show the `invisible_unicode` caution (29 findings, all in those renders),
  plus the informational isolation note. The shipped evidence write-ups and code
  remain tracked; the captured renders are regenerable via `evals/live_eval.py`
  and `evals/failed_pairs.py` and are not cloned or installed.
