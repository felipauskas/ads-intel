# ads-intel

Free, local, zero-API-key ad-library intelligence for Hermes. `ads-intel` searches the public Meta Ad Library and watches competitors for new, ended and changed ads through three tools — `ad_search`, `ad_watch` and `ad_check` — using only the Python standard library and Hermes' built-in `web_extract`; no API keys, accounts, cookies or third-party services, and nothing leaves your machine except the read-only library request itself.

## Requirements

- **Python 3.10+.** The source uses PEP 604 annotations (`str | None`, `dict | None`); 3.9 fails at import. The plugin runs inside Hermes's own Python, but a local checkout's test suite needs a 3.10+ interpreter.
- **git.** Hermes installs a local checkout from a `file://` URL by cloning it, so the directory must be a git repository.
- **Hermes CLI with plugin support**, `>= 0.21.5` (the `requires_hermes` floor in `plugin.yaml`), including the `hermes plugins` subcommands.

## Install (local checkout only)

This plugin is **not published yet** — there is no published catalog entry and no public repo. Install it from the local checkout (it must be a git repo, since Hermes installs from a `file://` URL):

```bash
cd /path/to/ads-intel          # the checkout that contains plugin.yaml
hermes plugins validate .      # manifest + tool schema check, installs nothing
hermes plugins install "file://$PWD"
hermes plugins enable ads-intel
```

`file://` installs prompt with an "insecure source" warning: the path is local, unsigned and has no catalog entry. That warning is expected here; the source is the checkout you just validated.

Verify the install and the checkout's scan:

```bash
hermes plugins list            # ads-intel should be listed as enabled
hermes plugins validate .      # expect a clean scan: no errors or warnings
```

If `hermes plugins list` does not show it, re-run the install block from the same checkout; the `file://` path must point at the directory that contains `plugin.yaml`.

## Uninstall

```bash
hermes plugins disable ads-intel     # stop loading its tools
hermes plugins uninstall ads-intel   # remove the installed copy
```

`uninstall` removes the plugin code, not its data. To delete the watchlist, snapshots and reports as well, remove the plugin data directory named under Disclosures: `~/.hermes/profiles/<profile>/plugin-data/ads-intel/`.

## Try it in 60 seconds

```bash
hermes plugins validate .      # manifest, declarations and security scan
```

Then, in a Hermes chat:

- *"Search the Meta Ad Library for ads mentioning Notion in the US, limit 10."* → `ad_search`, a **keyword** search: it returns any page whose ads mention Notion, not only Notion's own page. Add `advertiser: "Notion"` to keep only the resolved Notion page, and expect `name_not_matched` when that page is absent from the keyword listing.
- *"Watch KFC's ads, then check my ad watchlist for what changed."* → `ad_watch` + `ad_check`
- *"Show me KFC's ads in the UAE, but only from KFC's own page."* → `ad_search` with `advertiser`

The `country` code selects that market's ad-library listing, but Meta's public render does not guarantee market-pure creatives: an international brand can still show US-market copy or prices in the `AE` listing, and the plugin reports what the card shows rather than relabelling it. Treat `country` as the listing queried, not as proof of where an ad ran.

The first `ad_check()` seeds a baseline and reports every ad as `new`; the next call reports real diffs. Each `ad_check()` also writes an HTML report and JSON digest under the plugin data directory (see Disclosures).

## Tools

### `ad_search(query, limit, country, advertiser, active_status, media_type)`

Find the ads a brand, advertiser or keyword is running. `query` is required; `limit` defaults to 20. `country` is the two-letter ad-library market code and defaults to `US`; pass e.g. `AE` or `GB` to search that market's library. A malformed code returns `{"error": "invalid_country"}`.

`active_status` (`all` default, or `active` / `inactive`) and `media_type` (`all` default, or `image` / `video`) narrow the listing using the public library's own URL parameters — they are part of the same single free GET, not a second request or a paid endpoint. An unsupported value returns `{"error": "invalid_active_status"}` or `{"error": "invalid_media_type"}` rather than silently widening the search. The filters also apply when `advertiser` is set: the page is still resolved against the full fetched listing, then the filtered ads are kept.

`active_status` is passed to the library unchanged, but the per-ad `status` this plugin returns uses the render's own vocabulary: the library's **Active** is surfaced as `active` and its **Inactive** as `ended`. A filter of `inactive` therefore returns ads whose returned `status` is `ended`; the filter names and the surfaced status values deliberately differ, matching the diff vocabulary in `ad_check`.

Pass `advertiser` to keep only the resolved brand's page. Because the library is keyword-searched, a query like `Burger King` also returns unrelated pages that merely mention the term; with `advertiser` set, page names are scored (`0.80` exact, `0.85` normalized, `0.60` substring, threshold `0.80`) and only the winning page's ads come back, with `resolved: {page_name, score}`. If nothing reaches the threshold the response is `{"error": "name_not_matched", target, candidates, threshold}` — never the unfiltered keyword noise.

> "Search the Meta Ad Library for ads from Notion and show me the first 10."
> "What ads is KFC running in the UAE?"
> "Show me Burger King's ads but only from Burger King's own page."

Returns `{count, complete, fetched, country, ads}` (plus `advertiser` and `resolved` when filtering). `count` is the number of ads actually returned in `ads` — after `limit` and after any `advertiser` filter — not the number matched on the page; `complete` is the signal that the page held more ads than were returned, and `fetched` is the number fetched into this response. Each ad carries:

| Field | Meaning | Source |
| --- | --- | --- |
| `id`, `page_name`, `status`, `first_seen`, `last_seen`, `creative_text`, `library_url` | The original seven fields, unchanged. | public render + library URL |
| `page_url` | The advertiser's Facebook page link shown on the card (`facebook.com/nike/`, or a numeric `facebook.com/615…/`). | public render |
| `page_id` | The numeric page id parsed from `page_url`; `""` when the page link is a vanity handle. | derived |
| `link_url`, `link_title` | Destination URL and title/caption of the ad's CTA block; `""` when the ad has no external CTA (help/facebook.com links are ignored). | public render |
| `cta_text` | CTA label such as `Shop Now` or `Learn More`; `""` when absent. | public render |
| `images` | Creative image URLs found on the card (the 60×60 profile thumbnail is excluded); `[]` when none render. | public render |
| `has_video` | `true` only when the card shows the "having trouble playing this video" signal. There is no video file URL. | public-render signal |
| `same_creative_count` | `N` from "**N ads** use this creative and text"; `0` when the card does not say. | public render |
| `multiple_versions` | `true` when the card says "This ad has multiple versions". | public render |

Missing values are always `""` / `[]` / `0` / `false`, never absent keys, so old snapshots and new reads have the same shape.

### `ad_watch(action, query, country, advertiser, active_status, media_type)`

Manage the local watchlist: `add` a query, `remove` a query, or `list` saved queries. `query` is required for `add`; `country`, `advertiser`, `active_status` and `media_type` apply to `add` (defaults `US`, none, `all`, `all`). The watchlist stores `{query, country}` entries, plus `advertiser` and any non-default filter; `remove` drops every entry for that query regardless of market or filters. Filters are stored only when they differ from `all`, so an unfiltered watch keeps exactly the entry shape and snapshot filename it had before filters existed. A filtered watch has its own snapshot and report, and never falls back to the unfiltered baseline — the excluded ads would otherwise be reported as `ended`.

> "Add 'KFC' to my ad watchlist, country AE, advertiser KFC."
> "Add a US keyword watch too, e.g. 'nike'."
> "What am I watching?"
> "Remove 'KFC' from my ad watchlist."

Returns `{"action": "add" | "remove" | "list", "watchlist": [...]}` — the full watchlist after the change, in every case (not the single entry or a count). Each entry is `{"query", "country"}`, plus `"advertiser"` when one was set and `"active_status"` / `"media_type"` when they differ from `all`; an unfiltered, advertiser-less entry keeps exactly the two-key shape. Invalid input returns `{"error": "..."}` (`query required`, `invalid_country`, `invalid_active_status`, `invalid_media_type`, or `unknown action: <action>`).

### `ad_check()`

Fetch every watchlist entry (re-applying its country, advertiser and filters), diff it against that entry's last saved snapshot, and report what changed.

> "Check my ad watchlist and tell me what's new."

Diff semantics:

- **new** — an ad id appears that was not in the prior snapshot, or an ad went `ended` → `active`.
- **ended** — an ad id is no longer present, or an ad went `active` → `ended`.
- **changed** — an ad kept its id but its status or creative signature changed. The signature is creative text plus, when both the old and new record carry them, `link_url`, `link_title` and `cta_text`; a field added by a newer version is not compared against an older baseline, so upgrading does not report every ad as changed. Image lists are not part of the signature.
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

There is no top-level count — sum the rows if you need one. A processed row always carries `query`, `country`, `partial`, the three integer counts (`new_ads`, `ended_ads`, `changed_ads`) and the three matching arrays (`new`, `ended`, `changed`). Each bucket entry is an ad summary with the same 16 keys as an `ad_search` ad (`id`, `page_name`, `status`, `first_seen`, `last_seen`, `creative_text`, `library_url`, `page_url`, `page_id`, `link_url`, `link_title`, `cta_text`, `images`, `has_video`, `same_creative_count`, `multiple_versions`), defaulted to `""` / `[]` / `0` / `false`. An advertiser watch adds `advertiser` and `resolved`; a non-default filter adds `active_status` / `media_type`.

Rows that did not diff carry the same `query`, `country` and `artifacts: {error}`, and one of:

- `skipped: true` with `reason: "fetch_empty"` or `"parse_failed"` — no snapshot was written and no endings were inferred.
- `error: "name_not_matched"` with `advertiser`, `target`, `candidates` and `threshold` — the page could not be resolved, so no snapshot was written.
- `error: "<detail>"` — an unexpected failure for that entry; the other entries still run.

`partial` reports fetch completeness, not success: it is `true` when the listing was clipped or could not be read, and `false` when the outcome is a fact about a complete listing. `name_not_matched` is therefore `partial: false` on a complete listing, but `true` when the render was clipped and the page may simply not have rendered.

## Disclosures

- **Network: yes.** When a tool runs, the plugin asks Hermes to fetch exactly one URL per query: `https://www.facebook.com/ads/library/...`, a read-only GET performed by Hermes' built-in `web_extract`. No other hosts are contacted, and the plugin makes no requests while idle.
- **Filesystem:** writes only inside the plugin data directory (`plugin_data_dir("ads-intel")`) — `watchlist.json`, `snapshots/<sha1>.json` and `reports/`. It reads nothing outside that directory, runs no shell commands, starts no background processes, and needs no credentials, environment variables or secrets — there is no account, API key or token to configure. Outside Hermes (for example when the test suite imports `store` directly), `store` falls back to `~/.ads-intel-dev` because `plugins.plugin_storage` is not importable there.
- **Reports in `reports/`:** each `ad_check()` run writes a self-contained pair per query + country + advertiser + filters — `reports/<sha1>.html` (the rendered `report.html` card gallery, inline CSS, no CDN, no scripts, no external images) and `reports/<sha1>.digest.json` (machine-readable counts for the same run). Cards now show the CTA label and its destination link (only absolute `http(s)` URLs become anchors; anything else stays inert text), plus badges for `N use this creative`, `Multiple versions` and the number of creative images — the image count is text, the URLs are never embedded as `<img>`, so the report stays offline and fetches nothing. The digest adds `with_link`, `with_cta`, `with_images`, `with_same_creative` and `with_multiple_versions` alongside `total`/`new`/`ended`/`changed`. The filename hashes the `(query, country, advertiser, active_status, media_type)` key, so the same query in two markets, two filter slices, or filtered vs. unfiltered, never overwrites the other. The HTML escapes untrusted page names and creative copy.
- **Data stored locally:** watchlist `{query, country}` (plus `advertiser` and any non-default filters when set) entries, ad snapshots (id, page name, status, dates, creative text, page URL/id, destination link and title, CTA text, creative image URLs, video flag, creative-grouping signals) and the generated reports. Nothing is sent anywhere; the only outbound traffic is the library GET above.
- **Country:** `country` is the two-letter ad-library market code (`US` by default; `AE`, `GB`, …). It selects the market in the library URL and is part of every snapshot and report key, so a country change starts a fresh baseline for that market instead of mixing markets.
- **Upgrade note:** an older watchlist of plain query strings loads as `US` watches, and their pre-country `US` snapshots are still read, so no baseline is lost. The watchlist is rewritten in the new `{query, country}` format on the next `ad_watch` change; the snapshot is written to its new country-keyed file on the next `ad_check`. The old `sha1(query)` snapshot file is orphaned after that but harmless, and can be deleted.
- **Terms of service posture — stated plainly:** this reads Meta's *public* Ad Library with no login, no cookies and no logged-in scraping, but Meta's terms do not authorise automated collection, and this plugin does not claim that authorisation. It is a read-only, low-rate client (one request per watch per `ad_check()`, sequential, no pagination, no retries hammering the endpoint), intended for personal, small-scale research. **You are responsible for your own use**; if Meta's terms or your jurisdiction forbid it, do not run it.

## Keyword matching

Queries are keyword searches, not brand filters: the library returns any page whose ads mention the term, so a watch acts as a keyword watch rather than a strict brand watch. Passing `advertiser` narrows a search or watch to one page after the fetch.

Advertiser resolution works on page names only (there are no page-id or handle matching rungs here), so the highest score it can award is `0.85` — a target differing only in punctuation or case (`KFC` vs `K.F.C.`). An identical name scores `0.80`, the threshold; substring hits score `0.60` and never match on their own. That means an owned page named `KFC UAE` is *not* selected by `advertiser: "KFC"`, and a miss is reported as `name_not_matched` (in `ad_check`: a row with `error`, `partial` reflecting fetch completeness, and no snapshot write — on a clipped render the miss only proves the page was not in what rendered) rather than falling back to the keyword hits. Adding or changing `advertiser` starts a filtered watch from a clean baseline, because filtered and unfiltered snapshots are keyed separately. An advertiser watch, and any watch with non-default filters, never adopts a legacy unstamped snapshot — only a plain unfiltered watch keeps a pre-stamp baseline.

## Limitations

- Meta may change the ad-library page markup; the parser lives in a single file (`sources.py`) and would need updating. When the page cannot be parsed at all, `ad_search` returns `{"error": "parse_failed: <detail>"}` and `ad_check` reports that entry as skipped with `reason: "parse_failed"` — it never writes an empty snapshot, so a markup break cannot masquerade as "everything ended".
- Large result pages are truncated by the fetcher (`char_limit=120000`). A render that fills the whole budget, or that carries the fetch host's head+tail truncation footer, is treated as partial: `ad_check` merges the fetched ads into the stored snapshot and suppresses endings for ids missing from the clipped page (`partial: true`), because an id absent from a clipped page has not necessarily stopped running. Status flips on ads that *did* render are still reported.
- A fetch that returns at least `limit` ads is also treated as partial: the tail past the limit was sliced off, so absent ids prove nothing there either. An unfiltered `ad_check` fetches the default `limit` of 20 ads per watch, which means **an unfiltered watch with 20 or more live ads reports `partial: true`; endings are suppressed for ids missing from the clipped page, while status flips that did render are still reported**. That is deliberate — a false "ended" is worse than a missed one — but it is a real ceiling: keep keyword watches narrow enough to stay under 20 results, and read `new`/`changed` (which stay accurate) rather than relying on retirements. A watch with `advertiser` is exempt: it fetches the full listing, resolves the page name against all of it, and tracks every ad on that page.
- No pagination in v1: one page of results per query, capped at 20 ads for an unfiltered `ad_check` (an `advertiser` watch keeps every ad on the resolved page). `ad_search` makes this ceiling visible instead of silent: every successful search listing carries `complete` (false when the render or the requested `limit` clipped the listing) and `fetched`, and `ad_check` rows carry `partial` in the same spirit. `complete: false` means there were more ads on the page than were returned — narrow the query or raise `limit`, and do not read a missing id as "ended".
- **Fields the public render does not expose — and this plugin therefore does not return:** publisher `platforms` (Facebook/Instagram/Audience Network placement), `page_likes`, `spend` and `impressions`, and direct video file URLs. These exist in paid/authenticated ad-intel products but not in Meta's public, logged-out page render. They are reported as absent, not guessed or back-filled from other sources. `has_video` is only the render's "trouble playing this video" signal; it is not a media inventory, and `images` is only what rendered on the card.
- The CTA fields are likewise render-derived: an ad whose card shows no outbound CTA block returns `link_url`/`link_title`/`cta_text` as `""` rather than an inferred destination.
- **Free-only invariant:** the new fields and filters add no request, no key, no login and no third-party service. Every tool call still performs exactly one read-only GET to `www.facebook.com/ads/library/`; the filters are query-string parameters on that same URL.

## License

MIT — see [LICENSE](LICENSE).
