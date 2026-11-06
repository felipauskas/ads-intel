# ads-intel — catalog submission (PR body)

> **DRAFT — local only, repo not yet published (rule 5 pending).**
> This file is not a PR yet: there is no public repo, no remote, and no
> `plugin-catalog/*.yaml` entry in this change. Do not submit until the repo is
> published and the catalog YAML lands in the separate local task.

---

## What it does

`ads-intel` is a free, local, zero-API-key **competitive ad intelligence** plugin for
Hermes. It reads Meta's public Ad Library and exposes three tools:

| Tool | Purpose |
| --- | --- |
| `ad_search(query, limit, country, advertiser)` | Show who is running ads for a brand, advertiser or keyword. |
| `ad_watch(action, query, country, advertiser)` | Track a competitor or keyword over time (`add` / `remove` / `list`). |
| `ad_check()` | Diff every watch against the last snapshot: new, ended, changed ads, plus an HTML report + JSON digest. |

Typical use: find a competitor's live creative, then get a weekly "what launched,
what stopped, what copy changed" diff without a paid ad-intel subscription.

## Hermes surfaces used

- **Tools only.** Three `provides_tools` entries, no slash commands, no hooks, no
  background jobs, no MCP server.
- **`ctx.dispatch_tool("web_extract", ...)`** — the only network path. One read-only
  GET per query to `https://www.facebook.com/ads/library/...`, performed by Hermes'
  built-in extractor, not by a bundled HTTP client.
- **`plugin_data_dir("ads-intel")`** — the only filesystem path. No paths outside it
  are read or written.
- Standard library only: `python_dependencies: []`, `capabilities: []`.

## Rule-13 disclosures

**Network host**

`www.facebook.com` (Meta Ad Library), one GET per query, only while a tool runs.
No other host is contacted; nothing is fetched while idle; no telemetry, no
analytics, no third-party API.

**Filesystem paths** (all under `plugin_data_dir("ads-intel")`)

| Path | Contents |
| --- | --- |
| `watchlist.json` | Tracked `{query, country}` entries (plus `advertiser` when set). |
| `snapshots/<sha1>.json` | Last-seen ads per `(query, country, advertiser)` key: id, page name, status, dates, creative text. |
| `reports/<sha1>.html` | Self-contained HTML report (`report.html` layout): inline CSS, no CDN, no scripts, no external images. |
| `reports/<sha1>.digest.json` | Machine-readable counts for the same run. |

Snapshot and report filenames hash the `(query, country, advertiser)` key, so markets
and filtered/unfiltered views never share an artifact. Untrusted page names and
creative copy are HTML-escaped; only `http(s)` URLs become links.

**Credentials**

No credentials. No API key, token, cookie, login, OAuth flow or environment variable
is required, read or stored. There is no account to create.

**Terms of service posture**

The plugin reads Meta's *public* Ad Library — no login, no cookies, no logged-in
scraping, no pagination, one sequential request per watch per `ad_check()`.
**Meta's terms do not authorise automated collection of the Ad Library, and this
plugin does not claim such authorisation.** It is a low-rate read-only client for
personal, small-scale research; the user is responsible for their own compliance.
This is disclosed in the README under "Terms of service posture" as well.

## Install + validate

The repo is **not published**; install from a local checkout.

```bash
cd /path/to/ads-intel
hermes plugins validate .
hermes plugins install "file://$PWD"    # local checkout; must be a git repo
hermes plugins enable ads-intel
```

Validation on this tree:

```
$ hermes plugins validate . --install-deps
Validation passed
```

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
  names only (`0.80` exact, `0.85` normalized ceiling, `0.60` substring), so an
  owned page with extra words (`KFC UAE` vs `KFC`) is not selected; a miss returns
  `name_not_matched`, never keyword noise.
- Result pages are clipped at `char_limit=120000`; a clipped or limit-sliced fetch
  is partial, and partial runs suppress endings for ids missing from the clipped
  page while still reporting status flips on ads that did render.
- A markup change on Meta's side surfaces as `parse_failed` (search) /
  `reason: "parse_failed"` (check) instead of a false "all ads ended".
- No pagination in v1: one page, 20 ads per watch for `ad_check`.
