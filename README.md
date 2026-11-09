# ads-intel

Free, local, zero-API-key ad-library intelligence for Hermes. `ads-intel` searches the public Meta Ad Library and watches competitors for new, ended and changed ads through three tools — `ad_search`, `ad_watch` and `ad_check` — using only the Python standard library and Hermes' built-in `web_extract`; no API keys, accounts, cookies or third-party services, and nothing leaves your machine except the read-only library request itself.

## Requirements

- **Python 3.10+.** The source uses PEP 604 annotations (`str | None`, `dict | None`); 3.9 fails at import. The plugin runs inside Hermes's own Python, but a local checkout's test suite needs a 3.10+ interpreter.
- **git.** Hermes installs a plugin by cloning its repository, so the source must be a git repo — the published GitHub repo is, and a local `file://` checkout must be too.
- **Hermes CLI with plugin support**, `>= 0.21.5` (the `requires_hermes` floor in `plugin.yaml`), including the `hermes plugins` subcommands.

## Install

`ads-intel` is published at **https://github.com/felipauskas/ads-intel** (public).
It is **not yet in the Hermes catalog**: the catalog entry is drafted in
`plugin-catalog/ads-intel.yaml` and lands as a PR against
`NousResearch/hermes-agent`, so install it from the repo:

```bash
hermes plugins install felipauskas/ads-intel --force
hermes plugins enable ads-intel
```

**`--force` is required in non-interactive use.** This plugin carries a
`caution` security verdict (see below) and it is not a catalog-reviewed source:
a non-interactive install — an agent, CI or a scripted shell — treats that
combination as **Blocked** and exits 1 rather than asking. The current block
reads `Decision: BLOCKED — Blocked (community source + caution verdict, 78
findings). Use --force to override.` In a real terminal the same install blocks
only until you answer the `[y/N] "install anyway?"` prompt; `--force` answers it
up front. The force is accepting the scan's caution verdict, not silencing it:
install still prints `Warning: custom (unreviewed) source — not from the Hermes
catalog.` A `file://` checkout install additionally prints `Warning: Using
insecure/local URL scheme`. Neither route gives a warning-free install.

The caution is not a finding in plugin runtime code: it is committed eval
evidence (Arabic ad copy with invisible directional marks under `evals/`), plus
lower-severity heuristics on the eval JSON, the tests, `scripts/stress_e2e.py`
and CI. The install-time scan and `hermes plugins validate .` count differently —
see the two notes below. To drop the verdict you would have to stop shipping
`evals/`; it is also imported by the tests and `scripts/stress_e2e.py`, so those
fixtures and imports would have to move first. There is no warning-free path
today.

Verify the install and the scan:

```bash
hermes plugins list            # ads-intel should be listed as enabled
hermes plugins validate .      # from a checkout; ends in "Validation passed."
```

`hermes plugins validate .` ends in `Validation passed.` Every check passes, but it is **not a silent clean scan**:

- **Security scan caution — `invisible_unicode`.** 29 findings at the last check (`hermes plugins validate .`, Hermes v0.23.0), all in committed eval evidence, none in plugin code: 18 in `evals/live-matrix/dominos-pizza-us/ads.json` (invisible directional marks in the Arabic ad copy), 5 in `evals/live-matrix/dominos-pizza-us/artifacts/html.html`, 2 in `evals/page-mode-verify/rerun-burger-king-us.json` and 4 in `evals/page-mode-verify/rerun-mcdonalds-eg.json`. `validate` prints basenames only, so its `ads.json` / `html.html` entries are the dominos-pizza-us pair; the `rerun-*.json` entries were not previously listed here. The install-time scan is broader and reports **78 findings** for the same tree (36 HIGH `injection` for those characters, 34 MEDIUM `obfuscation`, 4 MEDIUM `execution`, 2 MEDIUM `supply_chain`, 1 MEDIUM `injection`, 1 LOW `persistence`) across 22 files under `evals/`, `tests/`, `scripts/`, `.github/`, `README.md` and `docs/plans/` — again none in the modules Hermes loads (`sources.py`, `tools.py`, `store.py`, `report.py`, `resolve.py`, `diffing.py`, `schemas.py`, `__init__.py`, `plugin.yaml`). The scanner has no ignore-file mechanism (only fixed dir exclusions such as `.git` and `__pycache__`), and deleting `evals/` alone would not produce a clean scan: `tests/test_sources.py` reads `evals/raw/web_extract-KFC-AE.md`, `tests/test_resolve.py` reads `evals/live-matrix/*/ads.json`, `tests/test_live_eval.py` imports `evals/live_eval.py`, and `scripts/stress_e2e.py` imports from `evals.live_eval`, so those fixtures and imports would have to be relocated first. The decision — ship `evals/` and accept the caution, or relocate them — is still open; until then the caution is expected, the plugin still passes admission, and the install needs `--force` as shown above.
- **Isolation note (informational).** `evals/live_eval.py` and `scripts/stress_e2e.py` patch `tools.store._data_dir` to run offline against a temp directory. Hermes reports this as "in-process only" and does not treat it as a failure.

If `hermes plugins list` does not show it, re-run the install line; if you are installing from a local checkout instead, the `file://` path must point at the directory that contains `plugin.yaml` (`hermes plugins install "file://$PWD" --force`).

## Uninstall

```bash
hermes plugins disable ads-intel     # stop loading its tools
hermes plugins uninstall ads-intel   # remove the installed copy
```

`uninstall` removes the plugin code, not its data. To delete the watchlist, snapshots and reports as well, remove the plugin data directory named under Disclosures: `~/.hermes/profiles/<profile>/plugin-data/ads-intel/`.

## Try it in 60 seconds

```bash
hermes plugins doctor ads-intel   # runtime discovery, manifest, registration
```

Then, in a Hermes chat:

- *"Search the Meta Ad Library for ads mentioning Notion in the US, limit 10."* → `ad_search`, a **keyword** search: it returns any page whose ads mention Notion, not only Notion's own page. Add `advertiser: "Notion"` to keep only the resolved Notion page, and expect `name_not_matched` when that page is absent from the keyword listing.
- *"Watch KFC's ads, then check my ad watchlist for what changed."* → `ad_watch` + `ad_check`
- *"Show me KFC's ads in the UAE, but only from KFC's own page."* → `ad_search` with `advertiser`

The `country` code selects the market listing — ads that reached that market. Two different things must not be confused: `country` is the *delivery market* (the listing queried), while a card's `page_name` is the *advertiser page* that ran the ad. A page named "KFC Masr" (Egypt) appearing in an `AE` listing does not mean the country filter failed — that advertiser simply reached the market, or the keyword matched. Identical US copy appearing across markets is the default `active_status=all` view: Meta ranks by total impressions, so the same high-impression *inactive* cards head every listing. Use `active_status=active` for the cards currently running in that market; active AE listings show AED prices.

The first `ad_check()` seeds a baseline and reports every ad as `new`; the next call reports real diffs. Each `ad_check()` also writes an HTML report and JSON digest under the plugin data directory (see Disclosures).

## Tools

### `ad_search(query, limit, country, advertiser, active_status, media_type, page_id)`

Find the ads a brand, advertiser or keyword is running. `query` is required; `limit` defaults to 20. `country` is the two-letter ad-library market code and defaults to `US`; pass e.g. `AE` or `GB` to search that market's library. A malformed code returns `{"error": "invalid_country"}`.

`active_status` (`all` default, or `active` / `inactive`) and `media_type` (`all` default, or `image` / `video`) narrow the listing using the public library's own URL parameters — they are part of the same single free GET, not a second request or a paid endpoint. An unsupported value returns `{"error": "invalid_active_status"}` or `{"error": "invalid_media_type"}` rather than silently widening the search. The filters also apply when `advertiser` is set: the page is still resolved against the full fetched listing, then the filtered ads are kept.

`active_status` is passed to the library unchanged, but the per-ad `status` this plugin returns uses the render's own vocabulary: the library's **Active** is surfaced as `active` and its **Inactive** as `ended`. A filter of `inactive` therefore returns ads whose returned `status` is `ended`; the filter names and the surfaced status values deliberately differ, matching the diff vocabulary in `ad_check`.

Pass `advertiser` to keep only ads whose **page name** matches — this is a local page-name filter applied after the keyword search, *not* Meta's advertiser (Page) search (use `page_id` below for that). Several Pages can share one display name (e.g. every KFC page is named "KFC": US `@KFC`, Egypt "KFC Masr" is a different page but scores as a different name; `@kfcarabia` is also named "KFC" and cannot be distinguished by name alone — use `page_url`/`page_id` on a card to identify the exact Page, or include a distinguishing token in `query`). Because the library is keyword-searched, a query like `Burger King` also returns unrelated pages that merely mention the term; with `advertiser` set, page names are scored (`0.80` exact, `0.85` normalized, `0.60` substring, threshold `0.80`). When `country` is given, a page whose trailing qualifier explicitly names a *different* market is excluded before ranking (a page with no qualifier is global and stays eligible), then equal scores are broken by the requested market and then by an exact name match. The `page_url` slug is checked the same way: `facebook.com/KFCMexico/` is excluded from a US query even though the page is named `KFC`, while a handle with no country token (`McDonalds`, a numeric id) stays eligible, and a regional token narrows to its own set instead of one market: `kfcarabia` carries `arabia`, which spans the GCC markets, so it is eligible for `AE`/`SA`/`QA`/`OM`/`BH`/`KW` and vetoed everywhere else, including `US`, `GB` and `EG`. A qualifier is any ISO-3166-1 country name or alpha-2 code printed *after* the brand (`KFC UAE`, `KFC SA`, `Burger King Arabia`), plus the alias and regional forms resolve.py carries; a bare brand name carries no qualifier and stays eligible in every market. Multi-word country names (`Saudi Arabia`, `United Kingdom`, `Trinidad and Tobago`) are peeled as one phrase, longest first, so no country word is left glued to the brand. Only the winning page's ads come back, with `resolved: {page_name, score}`. If nothing reaches the threshold — or two pages are still tied after both tie-breakers — the response is `{"error": "name_not_matched", target, candidates, threshold}` (a surviving tie also carries `"ambiguous": true`) — never the unfiltered keyword noise, and never a guess between tied pages.

Pass `page_id` — a numeric Meta Page ID, digits only — to search one Page's own listing instead of a keyword. The fetch switches to Meta's Page-search URL (`search_type=page&view_all_page_id=<id>`, no `q=` is sent), and `advertiser` is ignored: an exact numeric identity outranks any page name. Page identity and delivery market are **separate axes**: `page_id` says *which Page*, `country` says *which market's library to read*. A country-specific page plus its own market is one watch (`page_id=209644529058679` for `facebook.com/McDonaldsUK/` with `country=GB`); the global McDonald's Page with `country=US` is a different watch and can return different ads. Results add `page_id`, `page_found` and `country_filtered`. On a miss, `page_found: false, country_filtered: false` means the listing rendered but neither carried that Page ID on a card nor exposed a single listing-wide `page_url` slug to stand as its identity; `page_found: false, country_filtered: true` means this market's listing was empty, so the Page's identity could not be observed here — that is not proof the Page is missing from Meta. A value that is not all ASCII digits returns `{"error": "invalid page_id"}`; an empty string is a caller error, not a fallback to keyword search.

**Resolved, not open:** the page-mode fetch was always exact, and resolution
now treats the page-mode listing itself as the identity. When every card on the
listing shares one `page_url` slug, that slug resolves the requested numeric ID
at score `1.0` (`evals/page-mode-verify/rerun-*.json`; KFC-US: 27 ads on the
listing, `page_found: true`). Residual limitation, stated honestly: a listing
whose cards name *more than one* slug still reports `name_not_matched` rather
than guessing, and a card with no usable `page_url` is kept on the resolved
slug's identity (its `page_name` may be `""`). See `evals/failed-pairs-crosscheck.md`
§5 for the dated rerun pointer.

> "Search the Meta Ad Library for ads from Notion and show me the first 10."
> "What ads is KFC running in the UAE?"
> "Show me Burger King's ads but only from Burger King's own page."

Returns `{count, complete, complete_scope, total_returned, char_limit, fetched, country, ads}` (plus `advertiser` and `resolved` when filtering, and `page_id` / `page_found` / `country_filtered` when `page_id` is given). `count` is the number of ads actually returned in `ads` — after `limit` and after any `advertiser` filter — not the number matched on the page; `complete` is the signal that the rendered page came back *unclipped* — `limit` and the fetch char budget did not slice it. `complete_scope` is always `rendered_window`, the machine-readable reminder that `complete` never means Meta's full result set was retrieved (there is no pagination; see "No pagination" under Limitations). `total_returned` is how many ads the render held before `limit` sliced it, `char_limit` the fetch budget in characters, and `fetched` the number fetched into this response. Each ad carries:

| Field | Meaning | Source |
| --- | --- | --- |
| `id`, `page_name`, `status`, `first_seen`, `last_seen`, `creative_text`, `library_url` | The original seven fields, unchanged. | public render + library URL |
| `page_url` | The advertiser's Facebook page link shown on the card (`facebook.com/nike/`, or a numeric `facebook.com/615…/`). | public render |
| `page_id` | The numeric page id parsed from `page_url`; `""` when the page link is a vanity handle. | derived |
| `link_url`, `link_title` | Destination URL and title/caption of the ad's CTA block; `""` when the ad has no external CTA (help/facebook.com links are ignored). | public render |
| `cta_text` | CTA label such as `Shop Now` or `Learn More`; `""` when absent. | public render |
| `link_caption` | The display domain the CTA block prints above the title (`AD.DOUBLECLICK.NET`, `PLAY.GOOGLE.COM`, `bk.com`); `""` when the render shows no caption. This is what is printed, not the link URL's host: `bk.com` can point at an `app.link` redirect. | public render |
| `cta_type` | `cta_text` as Treg's upper-snake enum: `ORDER_NOW`, `SHOP_NOW`, `LEARN_MORE`, `SIGN_UP`, `DOWNLOAD`, `GET_OFFER`, `INSTALL_MOBILE_APP`, `USE_MOBILE_APP`, `SEE_DETAILS`, `BOOK_NOW`, `BUY_NOW`, `CONTACT_US`, `APPLY_NOW`, `SUBSCRIBE`, `MESSAGE_US`, `SEND_MESSAGE`; an unmapped label is upper-snaked as printed (`Visit Instagram profile` → `VISIT_INSTAGRAM_PROFILE`), `""` when `cta_text` is empty. | derived from `cta_text` |
| `display_format` | `image` (one rendered image), `video` (video marker, no image), `dco` (multiple rendered images, or an image plus video), or `""` when no media signal rendered. Treg also reports `carousel`, but the public render cannot distinguish it from `dco`, so it is never claimed. | derived from `images` + `has_video` |
| `cards` | Per-card grouping in Treg's shape, always a non-empty list of `{body, cta, image, link_url, title, video}`. A multi-image ad gets one card per rendered image (body/CTA/link repeated, image varied); any other ad gets one card. `video` is always `null`: the render exposes no video file URL. | public render (grouped) |
| `images` | Creative image URLs found on the card (the 60×60 profile thumbnail is excluded); `[]` when none render. | public render |
| `has_video` | `true` only when the card shows the "having trouble playing this video" signal. There is no video file URL. | public-render signal |
| `same_creative_count` | `N` from "**N ads** use this creative and text"; `0` when the card does not say. | public render |
| `multiple_versions` | `true` when the card says "This ad has multiple versions". | public render |

Missing values are always `""` / `[]` / `0` / `false`, never absent keys, so old snapshots and new reads have the same shape.

### `ad_watch(action, query, country, advertiser, active_status, media_type, page_id)`

Manage the local watchlist: `add` a query, `remove` a query, or `list` saved queries. `query` is required for `add`; `country`, `advertiser`, `active_status`, `media_type` and `page_id` apply to `add` (defaults `US`, none, `all`, `all`, none). A `page_id` stores a Page-identity watch: the fetch uses page mode and the snapshot/report key carries the ID, so a keyword watch and a page watch on the same query never share a baseline. The watchlist stores `{query, country}` entries, plus `advertiser` and any non-default filter. `remove` drops every entry for that query regardless of market or filters — unless you pass `advertiser`, `country`, `active_status` or `media_type`, which narrows the removal to matching entries: two brand watches on one keyword (`advertiser: "KFC"` and `advertiser: "KFC Masr"`) can be removed one at a time. Filters are stored only when they differ from `all`, so an unfiltered watch keeps exactly the entry shape and snapshot filename it had before filters existed. A filtered watch has its own snapshot and report, and never falls back to the unfiltered baseline — the excluded ads would otherwise be reported as `ended`.

> "Add 'KFC' to my ad watchlist, country AE, advertiser KFC."
> "Add 'KFC' to my watchlist, country US, page id 7144906559."
> "Add a US keyword watch too, e.g. 'nike'."
> "What am I watching?"
> "Remove 'KFC' from my ad watchlist."

Returns `{"action": "add" | "remove" | "list", "watchlist": [...]}` — the full watchlist after the change, in every case (not the single entry or a count). Each entry is `{"query", "country"}`, plus `"advertiser"` when one was set, `"page_id"` when a Page identity was given, and `"active_status"` / `"media_type"` when they differ from `all`; an unfiltered, advertiser-less, ID-less entry keeps exactly the two-key shape. Invalid input returns `{"error": "..."}` (`query required`, `invalid_country`, `invalid_active_status`, `invalid_media_type`, or `unknown action: <action>`).

### `ad_check()`

Fetch every watchlist entry (re-applying its country, advertiser and filters), diff it against that entry's last saved snapshot, and report what changed.

> "Check my ad watchlist and tell me what's new."

Diff semantics:

- **new** — an ad id appears that was not in the prior snapshot, or an ad went `ended` → `active`.
- **ended** — an ad id is no longer present, or an ad went `active` → `ended`.
- **changed** — an ad kept its id but its status or creative signature changed. The signature is creative text plus, when both the old and new record carry them, `link_url`, `link_title`, `cta_text`, `link_caption`, `cta_type` and `display_format`; a field added by a newer version is not compared against an older baseline, so upgrading does not report every ad as changed. Image lists and `cards` are not part of the signature (their signed URLs rotate between renders of identical creative). `link_title` is compared after the render's live Like-Page counter ("N people like this / follow this") is normalised out, so counter drift alone is not reported as a creative change.
- **baseline** — the first `ad_check()` after adding a watch has no prior snapshot, so every ad it finds reports as `new`. That run seeds the baseline; diffs start on the next run.
- **fail-safe** — if a fetch fails or returns an empty page while a snapshot exists, that query is reported as `skipped` (`fetch_empty`) and the diff is skipped. The snapshot is never overwritten with an empty result, so a transient failure cannot be mistaken for "every ad ended".

Response shape — one row per watchlist entry, in watchlist order:

```json
{
  "checked_at": "2026-11-06T12:00:00",
  "results": [
    {
      "query": "KFC",
      "country": "US",
      "partial": true,
      "new_ads": 1,
      "ended_ads": 0,
      "changed_ads": 2,
      "new": [{"id": "…", "page_name": "…", "status": "active", "…": "…"}],
      "ended": [],
      "changed": [{"id": "…", "status": "active", "…": "…"}],
      "artifacts": {"html": "/…/reports/<sha1>.html", "digest": "/…/reports/<sha1>.digest.json"}
    }
  ]
}
```

There is no top-level count — sum the rows if you need one. A processed row always carries `query`, `country`, `partial`, the three integer counts (`new_ads`, `ended_ads`, `changed_ads`) and the three matching arrays (`new`, `ended`, `changed`). Each bucket entry is an ad summary with the same 20 keys as an `ad_search` ad (`id`, `page_name`, `status`, `first_seen`, `last_seen`, `creative_text`, `library_url`, `page_url`, `page_id`, `link_url`, `link_title`, `cta_text`, `link_caption`, `cta_type`, `display_format`, `cards`, `images`, `has_video`, `same_creative_count`, `multiple_versions`), defaulted to `""` / `[]` / `0` / `false`. Per-ad free-text fields in the tool output (`creative_text`, `page_name`, `link_title`, and each card's `title` / `body`) are truncated at 1200 characters (the ellipsis marker counts against the cap); non-string copy becomes `""`. The HTML report is not truncated: it keeps the full snapshot copy by design, so a report can show copy longer than the tool response did; the JSON digest carries counts only. An advertiser watch adds `advertiser` and `resolved`; a non-default filter adds `active_status` / `media_type`.

Rows that did not diff carry the same `query`, `country` and `artifacts: {error}`, and one of:

- `skipped: true` with `reason: "fetch_empty"` or `"parse_failed"` — no snapshot was written and no endings were inferred.
- `error: "name_not_matched"` with `advertiser`, `target`, `candidates` and `threshold` — the page could not be resolved (including a tie that survived the market/exact tie-breakers, in which case `candidates` is the tied set), so no snapshot was written.
- `error: "<detail>"` — an unexpected failure for that entry; the other entries still run.

`partial` reports **rendered-window completeness**, not success and not "the whole result set was retrieved". It is `true` when the rendered page was clipped or could not be read, and `false` when the page came back unclipped. A `false` is a fact about *the rendered window only* — this plugin has no pagination (see "No pagination" below). `name_not_matched` is therefore `partial: false` on an unclipped render, but `true` when the render was clipped and the page may simply not have rendered.

## Disclosures

- **Network: yes.** When a tool runs, the plugin asks Hermes to fetch `https://www.facebook.com/ads/library/...`, a read-only GET performed by Hermes' built-in `web_extract`. A query normally costs **one** request. If the render fails to parse (a pre-hydration shell or corrupt payload), the same query is retried with a cache-busting query parameter, for at most **6 attempts in total** (the whole loop is capped at 60 seconds of wall-clock time); the first attempt uses the plain URL, and a successfully parsed render stops the loop immediately. A transport failure (`FetchError`) is retried once before it surfaces. No other hosts are contacted, and the plugin makes no requests while idle.
- **Filesystem:** writes only inside the plugin data directory (`plugin_data_dir("ads-intel")`) — `watchlist.json`, `snapshots/<sha1>.json` and `reports/`. It reads nothing outside that directory, runs no shell commands, starts no background processes, and needs no credentials, environment variables or secrets — there is no account, API key or token to configure. Outside Hermes (for example when the test suite imports `store` directly), `store` falls back to `~/.ads-intel-dev` because `plugins.plugin_storage` is not importable there.
- **Reports in `reports/`:** each `ad_check()` run writes a self-contained pair per query + country + advertiser + filters — `reports/<sha1>.html` (the rendered `report.html` card gallery, inline CSS, no CDN, no scripts, no external images) and `reports/<sha1>.digest.json` (machine-readable counts for the same run). Cards now show the CTA label and its destination link (only absolute `http(s)` URLs become anchors; anything else stays inert text), plus badges for `N use this creative`, `Multiple versions` and the number of creative images — the image count is text, the URLs are never embedded as `<img>`, so the report stays offline and fetches nothing. The digest adds `with_link`, `with_cta`, `with_images`, `with_same_creative` and `with_multiple_versions` alongside `total`/`new`/`ended`/`changed`. The filename hashes the `(query, country, advertiser, active_status, media_type)` key, so the same query in two markets, two filter slices, or filtered vs. unfiltered, never overwrites the other. The HTML escapes untrusted page names and creative copy.
- **Data stored locally:** watchlist `{query, country}` (plus `advertiser` and any non-default filters when set) entries, ad snapshots (id, page name, status, dates, creative text, page URL/id, destination link and title, CTA text, creative image URLs, video flag, creative-grouping signals) and the generated reports. Nothing is sent anywhere; the only outbound traffic is the library GET above.
- **Country:** `country` is the two-letter ad-library market code (`US` by default; `AE`, `GB`, …). It selects the market in the library URL and is part of every snapshot and report key, so a country change starts a fresh baseline for that market instead of mixing markets.
- **Upgrade note:** an older watchlist of plain query strings loads as `US` watches, and their pre-country `US` snapshots are still read, so no baseline is lost. The watchlist is rewritten in the new `{query, country}` format on the next `ad_watch` change; the snapshot is written to its new country-keyed file on the next `ad_check`. The old `sha1(query)` snapshot file is orphaned after that but harmless, and can be deleted.
- **Terms of service posture — stated plainly:** this reads Meta's *public* Ad Library with no login, no cookies and no logged-in scraping, but Meta's terms do not authorise automated collection, and this plugin does not claim that authorisation. It is a read-only, low-rate client (one request per query in the normal case, sequential, no pagination; a retry happens only when a render fails to parse, at most 6 attempts within a 60-second ceiling), intended for personal, small-scale research. **You are responsible for your own use**; if Meta's terms or your jurisdiction forbid it, do not run it.

## Keyword matching

Queries are keyword searches, not brand filters: the library returns any page whose ads mention the term, so a keyword watch acts as a lead generator rather than a strict brand watch — that is Meta's own model (type a name, then pick the Page from the dropdown) and this plugin is honest about it. Passing `advertiser` narrows a search or watch to one **page name** after the fetch; it is not Meta's Page search. When the Page ID is known, `page_id` is the precise path: it fetches that Page's own listing (`search_type=page&view_all_page_id=`) and bypasses the name ladder entirely. When several Pages score equally, the requested market (a page naming a different market is vetoed outright) and then an exact name match break the tie; a tie that survives both is reported as `ambiguous` rather than guessed — inspect `page_url`/`page_id` on the returned cards to see which Page actually ran them, or add a distinguishing token to `query`.

Name resolution works on page names (and, with `page_id`, on the numeric Page identity rung first). The highest name score it can award is `0.85` — a target differing only in punctuation or case (`KFC` vs `K.F.C.`). An identical name scores `0.80`, the threshold; trailing country qualifiers (`KFC UAE`, `Burger King Arabia`, `Pizza Hut KSA`, `KFC SA`) are stripped before comparison, so those pages score `0.80` and resolve to the brand. Any ISO-3166-1 country name (all 249 officially assigned) or its alpha-2 code qualifies, and the alias/regional table adds the short forms a page may print (`KSA`, `UAE`, `UK`); multi-word country names are peeled whole, longest phrase first (`Trinidad and Tobago`, `United Kingdom`), so no country word is left glued to the brand. Substring hits where the brand is *not* the trailing country-qualified core still score `0.60` and never match on their own, and a miss is reported as `name_not_matched` (in `ad_check`: a row with `error`, `partial` reflecting rendered-window completeness, and no snapshot write — on a clipped render the miss only proves the page was not in what rendered) rather than falling back to the keyword hits. Adding or changing `advertiser` starts a filtered watch from a clean baseline, because filtered and unfiltered snapshots are keyed separately. An advertiser watch, and any watch with non-default filters, never adopts a legacy unstamped snapshot — only a plain unfiltered watch keeps a pre-stamp baseline.

## Limitations

- **Page-ID resolution works through the listing identity.** A page-mode fetch is exact — the URL pins `view_all_page_id` and the render is that Page's listing — and resolution now uses the listing itself as the identity: when every card shares one `page_url` slug, that slug resolves the requested ID at score `1.0`, even though the cards carry no numeric `page_id` (`evals/page-mode-verify/rerun-*.json`; KFC-US: 27 ads on the listing, `page_found: true`). Honest residual: a listing whose cards name more than one slug still returns `name_not_matched` instead of guessing, and a card with no usable `page_url` is kept under the resolved slug's identity with a possibly empty `page_name`. History in `evals/failed-pairs-crosscheck.md` §4 (`FAILED`) with the dated rerun in §5.
- Meta may change the ad-library page markup; the parser lives in a single file (`sources.py`) and would need updating. When the page cannot be parsed at all, `ad_search` returns `{"error": "parse_failed: <detail>"}` and `ad_check` reports that entry as skipped with `reason: "parse_failed"` — it never writes an empty snapshot, so a markup break cannot masquerade as "everything ended".
- Large result pages are truncated by the fetcher (`char_limit=120000`). A render that fills the whole budget, or that carries the fetch host's head+tail truncation footer, is treated as partial: `ad_check` merges the fetched ads into the stored snapshot and suppresses endings for ids missing from the clipped page (`partial: true`), because an id absent from a clipped page has not necessarily stopped running. Status flips on ads that *did* render are still reported.
- A fetch that returns at least `limit` ads is also treated as partial: the tail past the limit was sliced off, so absent ids prove nothing there either. An unfiltered `ad_check` fetches the default `limit` of 20 ads per watch, which means **an unfiltered watch with 20 or more live ads reports `partial: true`; endings are suppressed for ids missing from the clipped page, while status flips that did render are still reported**. That is deliberate — a false "ended" is worse than a missed one — but it is a real ceiling: keep keyword watches narrow enough to stay under 20 results, and read `new`/`changed` (which stay accurate) rather than relying on retirements. A watch with `advertiser` is exempt from that 20-ad slice: it fetches the rendered page with no result-limit slice, resolves the page name against the whole rendered window, and tracks every ad that fetch returned for the resolved page. That is still rendered-window semantics, not a full inventory — the library's own URL filters (`active_status`, `media_type`) narrow what renders, the fetch's 120,000-character budget can clip the page, and Meta's render is itself only the top of the result set. So an `advertiser` watch is complete only when the fetch came back unclipped (`partial: false`, `complete_scope: "rendered_window"`); absence from that window still proves nothing.
- **No pagination — every reading is window-scoped.** One page of results per query, capped at 20 ads for an unfiltered `ad_check` (an `advertiser` watch keeps every ad on the resolved page). `ad_search` makes this ceiling visible instead of silent: every successful search listing carries `complete` and `fetched` (the underlying fetch meta also stamps `complete_scope: "rendered_window"`). **`complete` means the rendered page came back unclipped — it does NOT mean Meta's entire result set was retrieved.** There is no pagination here, so a "complete" listing is still only the top-N window the public render showed. Concretely:
  - **absence ≠ ended.** An id missing from a complete window has left the visible window, not necessarily stopped running. `ended` in `ad_check` is therefore a window-scoped observation. (On a clipped render it is weaker still: endings are suppressed only for ids missing from the clipped page, while a status flip on an ad that did render is still reported — see above.)
  - **appearance ≠ launched.** A newly appearing top-20 ad may simply have entered the visible window. `new` is likewise a window-scoped observation, and the plugin does not guess whether the ad launched or the window shifted.
  - `complete: false` means the render or the requested `limit` clipped the listing. When `limit` was the clip, raising it (or narrowing the query) can show more; when the fetch's fixed char budget clipped the render, raising `limit` will not recover the tail — narrow the query instead.
  - Do not read a missing id as "ended" or a fresh id as "launched" without checking `first_seen` on the ad; treat both as "shown / not shown in this window".
- **Fields the public render does not expose — and this plugin therefore does not return:** publisher `platforms` (Facebook/Instagram/Audience Network placement), `page_likes`, `spend` and `impressions`, and direct video file URLs. These exist in paid/authenticated ad-intel products but not in Meta's public, logged-out page render. They are reported as absent, not guessed or back-filled from other sources. `has_video` is only the render's "trouble playing this video" signal; it is not a media inventory, and `images` is only what rendered on the card.
- The CTA fields are likewise render-derived: an ad whose card shows no outbound CTA block returns `link_url`/`link_title`/`cta_text`/`link_caption` as `""` and `cta_type` as `""` rather than an inferred destination. `link_caption` is the domain the CTA block *prints*, which is not always the link URL's host (`bk.com` pointing at `burgerking.app.link`), and `display_format` is inferred from the rendered media only — `carousel` is indistinguishable from `dco` here and is never claimed. `cards[].video` is always `null`: the public render has no video file URL.
- **Free-only invariant:** the new fields and filters add no key, no login and no third-party service. Each query still performs one read-only GET to `www.facebook.com/ads/library/` in the normal case — up to 6 only when a render fails to parse, each retry carrying a cache-busting parameter (a transport failure is retried once); the filters are query-string parameters on that same URL.

## Development

The test suite is stdlib-only — `pytest` is the sole dependency — and runs fully offline: no test performs a network request or reads the live ad library. Run it from the repository root (the tests import the modules as top-level names):

```bash
python -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest tests -q
```

CI runs the same command on Python 3.10 — the minimum in Requirements — for every push and pull request (`.github/workflows/ci.yml`).

The end-to-end stress harness is offline by default: it replays the recorded library render through the full tool path and adds concurrency and corruption checks. Only `--live` touches the network.

```bash
.venv/bin/python scripts/stress_e2e.py            # 50 offline iterations
.venv/bin/python scripts/stress_e2e.py -n 200     # more iterations
```

## License

MIT — see [LICENSE](LICENSE).
