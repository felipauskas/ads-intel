# ads-intel

Free, local, zero-API-key ad-library intelligence for Hermes. `ads-intel` searches the public Meta Ad Library and watches competitors for new, ended and changed ads through three tools — `ad_search`, `ad_watch` and `ad_check` — using only the Python standard library and Hermes' built-in `web_extract`; no API keys, accounts, cookies or third-party services, and nothing leaves your machine except the read-only library request itself.

## Install (local checkout only)

This plugin is **not published yet** — there is no catalog entry and no public repo. Install it from the local checkout (it must be a git repo, since Hermes installs from a `file://` URL):

```bash
cd /path/to/ads-intel          # the checkout that contains plugin.yaml
hermes plugins validate .      # manifest + tool schema check, installs nothing
hermes plugins install "file://$PWD"
hermes plugins enable ads-intel
```

`file://` installs prompt with an "insecure source" warning: the path is local, unsigned and has no catalog entry. That warning is expected here; the source is the checkout you just validated.

## Try it in 60 seconds

```bash
hermes plugins validate .      # manifest, declarations and security scan
```

Then, in a Hermes chat:

- *"Search the Meta Ad Library for ads from Notion in the US, limit 10."* → `ad_search`
- *"Watch linear.app's ads, then check my ad watchlist for what changed."* → `ad_watch` + `ad_check`
- *"Show me KFC's ads in the UAE, but only from KFC's own page."* → `ad_search` with `advertiser`

The first `ad_check()` seeds a baseline and reports every ad as `new`; the next call reports real diffs. Each `ad_check()` also writes an HTML report and JSON digest under the plugin data directory (see Disclosures).

## Tools

### `ad_search(query, limit, country, advertiser)`

Find the ads a brand, advertiser or keyword is running. `query` is required; `limit` defaults to 20. `country` is the two-letter ad-library market code and defaults to `US`; pass e.g. `AE` or `GB` to search that market's library. A malformed code returns `{"error": "invalid_country"}`.

Pass `advertiser` to keep only the resolved brand's page. Because the library is keyword-searched, a query like `Burger King` also returns unrelated pages that merely mention the term; with `advertiser` set, page names are scored (`0.80` exact, `0.85` normalized, `0.60` substring, threshold `0.80`) and only the winning page's ads come back, with `resolved: {page_name, score}`. If nothing reaches the threshold the response is `{"error": "name_not_matched", target, candidates, threshold}` — never the unfiltered keyword noise.

> "Search the Meta Ad Library for ads from Notion and show me the first 10."
> "What ads is KFC running in the UAE?"
> "Show me Burger King's ads but only from Burger King's own page."

Returns `{count, country, ads}` (plus `advertiser` and `resolved` when filtering), where each ad carries `id`, `page_name`, `status` (`active`/`ended`), `first_seen`, `last_seen`, `creative_text` and `library_url`.

### `ad_watch(action, query, country, advertiser)`

Manage the local watchlist: `add` a query, `remove` a query, or `list` saved queries. `query` is required for `add`; `country` applies to `add` (default `US`). The watchlist stores `{query, country}` entries, plus `advertiser` when given; `remove` drops every entry for that query regardless of market.

> "Add 'linear.app' to my ad watchlist."
> "Watch KFC in the UAE too."
> "What am I watching?"
> "Remove 'linear.app' from my ad watchlist."

### `ad_check()`

Fetch every watchlist entry, diff it against the last saved snapshot, and report what changed.

> "Check my ad watchlist and tell me what's new."

Diff semantics:

- **new** — an ad id appears that was not in the prior snapshot, or an ad went `ended` → `active`.
- **ended** — an ad id is no longer present, or an ad went `active` → `ended`.
- **changed** — an ad kept its id but its creative text or status string changed.
- **baseline** — the first `ad_check()` after adding a watch has no prior snapshot, so every ad it finds reports as `new`. That run seeds the baseline; diffs start on the next run.
- **fail-safe** — if a fetch fails or returns an empty page while a snapshot exists, that query is reported as `skipped` (`fetch_empty`) and the diff is skipped. The snapshot is never overwritten with an empty result, so a transient failure cannot be mistaken for "every ad ended".

## Disclosures

- **Network: yes.** When a tool runs, the plugin asks Hermes to fetch exactly one URL per query: `https://www.facebook.com/ads/library/...`, a read-only GET performed by Hermes' built-in `web_extract`. No other hosts are contacted, and the plugin makes no requests while idle.
- **Filesystem:** writes only inside the plugin data directory (`plugin_data_dir("ads-intel")`) — `watchlist.json`, `snapshots/<sha1>.json` and `reports/`. It reads nothing outside that directory, runs no shell commands, starts no background processes, and needs no credentials, environment variables or secrets — there is no account, API key or token to configure. Outside Hermes (for example when the test suite imports `store` directly), `store` falls back to `~/.ads-intel-dev` because `plugins.plugin_storage` is not importable there.
- **Reports in `reports/`:** each `ad_check()` run writes a self-contained pair per query + country + advertiser — `reports/<sha1>.html` (the rendered `report.html` card gallery, inline CSS, no CDN, no scripts, no external images) and `reports/<sha1>.digest.json` (the same counts as machine-readable JSON). The filename hashes the `(query, country, advertiser)` key, so the same query in two markets, or filtered vs. unfiltered, never overwrites the other. The HTML escapes untrusted page names and creative copy, and only `http(s)` library URLs become links.
- **Data stored locally:** watchlist `{query, country}` (plus `advertiser` when set) entries, ad snapshots (id, page name, status, dates, creative text) and the generated reports. Nothing is sent anywhere; the only outbound traffic is the library GET above.
- **Country:** `country` is the two-letter ad-library market code (`US` by default; `AE`, `GB`, …). It selects the market in the library URL and is part of every snapshot and report key, so a country change starts a fresh baseline for that market instead of mixing markets.
- **Upgrade note:** an older watchlist of plain query strings loads as `US` watches, and their pre-country `US` snapshots are still read, so no baseline is lost. The watchlist is rewritten in the new `{query, country}` format on the next `ad_watch` change; the snapshot is written to its new country-keyed file on the next `ad_check`. The old `sha1(query)` snapshot file is orphaned after that but harmless, and can be deleted.
- **Terms of service posture — stated plainly:** this reads Meta's *public* Ad Library with no login, no cookies and no logged-in scraping, but Meta's terms do not authorise automated collection, and this plugin does not claim that authorisation. It is a read-only, low-rate client (one request per watch per `ad_check()`, sequential, no pagination, no retries hammering the endpoint), intended for personal, small-scale research. **You are responsible for your own use**; if Meta's terms or your jurisdiction forbid it, do not run it.

## Keyword matching

Queries are keyword searches, not brand filters: the library returns any page whose ads mention the term, so a watch acts as a keyword watch rather than a strict brand watch. Passing `advertiser` narrows a search or watch to one page after the fetch.

Advertiser resolution works on page names only (`ad-intel`'s page-id and handle rungs do not exist here), so the highest score it can award is `0.85` — a target differing only in punctuation or case (`KFC` vs `K.F.C.`). An identical name scores `0.80`, the threshold; substring hits score `0.60` and never match on their own. That means an owned page named `KFC UAE` is *not* selected by `advertiser: "KFC"`, and a miss is reported as `name_not_matched` (in `ad_check`: a row with `error`, no snapshot write) rather than falling back to the keyword hits. Adding or changing `advertiser` starts a filtered watch from a clean baseline, because filtered and unfiltered snapshots are keyed separately; the one exception is a watch that adopts a legacy unstamped snapshot (written before snapshots carried an `advertiser` stamp), where other pages' ads stored earlier can be reported as `ended` once.

## Limitations

- Meta may change the ad-library page markup; the parser lives in a single file (`sources.py`) and would need updating. When the page cannot be parsed at all, `ad_search` returns `{"error": "parse_failed: <detail>"}` and `ad_check` reports that entry as skipped with `reason: "parse_failed"` — it never writes an empty snapshot, so a markup break cannot masquerade as "everything ended".
- Large result pages are truncated by the fetcher (`char_limit=120000`). A render that fills the whole budget, or that carries the fetch host's head+tail truncation footer, is treated as partial: `ad_check` merges the fetched ads into the stored snapshot and suppresses endings for ids missing from the clipped page (`partial: true`), because an id absent from a clipped page has not necessarily stopped running. Status flips on ads that *did* render are still reported.
- A fetch that returns at least `limit` ads is also treated as partial: the tail past the limit was sliced off, so absent ids prove nothing there either. `ad_check` fetches the default `limit` of 20 ads per watch, which means **any watch with 20 or more live ads reports `partial: true`; endings are suppressed for ids missing from the clipped page, while status flips that did render are still reported**. That is deliberate — a false "ended" is worse than a missed one — but it is a real ceiling: keep keyword watches narrow enough to stay under 20 results, and read `new`/`changed` (which stay accurate) rather than relying on retirements.
- No pagination in v1: one page of results per query, capped at 20 ads for `ad_check`.

## License

MIT — see [LICENSE](LICENSE).
