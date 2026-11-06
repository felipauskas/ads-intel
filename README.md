# ads-intel

Free, local, zero-API-key ad-library intelligence for Hermes. `ads-intel` searches the public Meta Ad Library and watches competitors for new, ended and changed ads through three tools — `ad_search`, `ad_watch` and `ad_check` — using only the Python standard library and Hermes' built-in `web_extract`; no API keys, accounts, cookies or third-party services, and nothing leaves your machine except the read-only library request itself.

## Install

```bash
hermes plugins install felipauskas/ads-intel
hermes plugins enable ads-intel
```

## Tools

### `ad_search(query, limit, country)`

Find the ads a brand, advertiser or keyword is running. `query` is required; `limit` defaults to 20. `country` is the two-letter ad-library market code and defaults to `US`; pass e.g. `AE` or `GB` to search that market's library. A malformed code returns `{"error": "invalid_country"}`.

> "Search the Meta Ad Library for ads from Notion and show me the first 10."
> "What ads is KFC running in the UAE?"

Returns `{count, country, ads}`, where each ad carries `id`, `page_name`, `status` (`active`/`ended`), `first_seen`, `last_seen`, `creative_text` and `library_url`.

### `ad_watch(action, query, country)`

Manage the local watchlist: `add` a query, `remove` a query, or `list` saved queries. `query` is required for `add`; `country` applies to `add` (default `US`). The watchlist stores `{query, country}` entries; `remove` drops every entry for that query regardless of market.

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
- **Filesystem:** writes only inside the plugin data directory — `watchlist.json` and `snapshots/<sha1>.json` (a truncated SHA-1 of the query plus market code is the filename). It reads nothing outside that directory, runs no shell commands, starts no background processes, and needs no credentials, environment variables or secrets.
- **Data stored locally:** watchlist `{query, country}` entries and ad snapshots (id, page name, status, dates, creative text). Nothing is sent anywhere.
- **Upgrade note:** an older watchlist of plain query strings loads as `US` watches, and their pre-country `US` snapshots are still read, so no baseline is lost; the first check after upgrading rewrites both in the new format.
- **ToS posture:** public ad library only — no login, no cookies, no logged-in scraping. Polite by design: `ad_check` issues one request per watchlist entry, sequentially.

## Keyword matching

Queries are keyword searches, not brand filters: the library returns any page whose ads mention the term, so a watch acts as a keyword watch rather than a strict brand watch.

## Limitations

- Meta may change the ad-library page markup; the parser lives in a single file (`sources.py`) and would need updating.
- Large result pages are truncated by the fetcher (`char_limit=120000`). A render that fills the whole budget, or that carries the fetch host's head+tail truncation footer, is treated as partial: `ad_check` merges the fetched ads into the stored snapshot and reports new/changed ads but suppresses the `ended` bucket (`partial: true`), because ids missing from a clipped page have not necessarily stopped running.
- A fetch that returns at least `limit` ads is also treated as partial: the tail past the limit was sliced off, so absent ids prove nothing there either. `ad_check` fetches the default `limit` of 20 ads per watch, which means **any watch with 20 or more live ads reports `partial: true` and never reports `ended` ads**. That is deliberate — a false "ended" is worse than a missed one — but it is a real ceiling: keep keyword watches narrow enough to stay under 20 results, and read `new`/`changed` (which stay accurate) rather than relying on retirements.
- No pagination in v1: one page of results per query, capped at 20 ads for `ad_check`.

## License

MIT — see [LICENSE](LICENSE).
