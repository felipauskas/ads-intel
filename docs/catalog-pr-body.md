# ads-intel — catalog submission (PR body)

> **DRAFT — local only, repo not yet published (rule 5 pending).**
> This file is not a PR yet: there is no public repo and no remote. The catalog
> entry exists locally as an unpublished draft (`plugin-catalog/ads-intel.yaml`).
> Do not submit until the repo is published and that entry is ready to land.

---

## What it does

`ads-intel` is a free, local, zero-API-key **competitive ad intelligence** plugin for
Hermes. It reads Meta's public Ad Library and exposes three tools:

| Tool | Purpose |
| --- | --- |
| `ad_search(query, limit, country, advertiser, active_status, media_type)` | Show who is running ads for a brand, advertiser or keyword. |
| `ad_watch(action, query, country, advertiser, active_status, media_type)` | Track a competitor or keyword over time (`add` / `remove` / `list`). |
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

The repo is **not published**; install from a local checkout.

```bash
cd /path/to/ads-intel          # the checkout that contains plugin.yaml
hermes plugins validate .      # manifest + tool schema check, installs nothing
hermes plugins install "file://$PWD" --force
hermes plugins enable ads-intel
```

**`--force` is required in non-interactive use.** This checkout carries a
`caution` security verdict (see below), and a `file://` source is unreviewed:
a non-interactive install — an agent, CI or a scripted shell — treats that
combination as **Blocked** and exits 1 rather than asking. In a real terminal
the same install blocks only until you answer the `[y/N] "install anyway?"`
prompt; `--force` answers it up front. The force is accepting the scan's
caution verdict, not silencing it: install still prints `Warning: custom
(unreviewed) source` and `Warning: Using insecure/local URL scheme`. The
caution is not a code finding — it is bidirectional marks in committed eval
evidence (Arabic ad copy under `evals/live-matrix/*/ads.json` and the rendered
HTML next to it). If you would rather install without `--force`, the only way
to clear the verdict is to stop shipping `evals/` (it is also imported by the
tests and `scripts/stress_e2e.py`, so those fixtures and imports must move
first). Neither path gives a warning-free install.

Validation on this tree (`hermes plugins validate .`, Hermes v0.23.0): every check
passes and the command ends in `Validation passed.` Two non-failing notices are
expected and should be quoted to reviewers rather than hidden:

```text
✓ security scan — caution
⚠ security scan caution: invisible_unicode (ads.json:139), invisible_unicode (ads.json:323), invisible_unicode (ads.json:349), invisible_unicode (ads.json:361), invisible_unicode (ads.json:65), invisible_unicode (ads.json:657), invisible_unicode (ads.json:695), invisible_unicode (html.html:56), invisible_unicode (html.html:57), invisible_unicode (html.html:58), invisible_unicode (html.html:62), invisible_unicode (html.html:72)
◇ Isolation — in-process only: evals/live_eval.py:202 patches tools.store._data_dir (a Hermes module attribute; the host's copy is not the one Hermes runs); scripts/stress_e2e.py:242 patches tools.store._data_dir (a Hermes module attribute; the host's copy is not the one Hermes runs)
Validation passed.
```

All 12 `invisible_unicode` findings are in committed eval evidence — Arabic ad copy
with bidirectional marks under `evals/live-matrix/*/ads.json` and
`evals/live-matrix/*/artifacts/html.html` — not in plugin code. The plugin scanner
has no ignore-file mechanism (only fixed directory exclusions), and excluding
`evals/` alone would not yield a clean scan: `tests/test_sources.py` reads
`evals/raw/web_extract-KFC-AE.md`, `tests/test_resolve.py` reads
`evals/live-matrix/*/ads.json`, `tests/test_live_eval.py` imports
`evals/live_eval.py`, and `scripts/stress_e2e.py` imports from
`evals.live_eval`, so those fixtures and imports would have to move first. The
decision — ship `evals/` and accept the documented caution, or relocate the
fixtures/imports — is still open; either way the caution is accurate and does not
block admission.
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
- Result pages are clipped at `char_limit=120000`; a clipped or limit-sliced fetch
  is partial, and partial runs suppress endings for ids missing from the clipped
  page while still reporting status flips on ads that did render. An `advertiser`
  watch resolves the page name against the full listing before filtering, so a
  brand page anywhere in the keyword hits is found and all of its ads are tracked.
- A markup change on Meta's side surfaces as `parse_failed` (search) /
  `reason: "parse_failed"` (check) instead of a false "all ads ended".
- No pagination in v1: one page per watch. Unfiltered `ad_check` keeps the first
  20 ads; an `advertiser` watch keeps every ad on the resolved page.

## Addendum 2026-11-06 (free field enrichment, Tasks 1–4)

The argument table above still names the original three arguments; this addendum
records what the same three tools now return without adding a surface.

- **New per-ad fields, all from the public render:** `page_url`, `page_id`,
  `link_url`, `link_title`, `cta_text`, `images`, `has_video`,
  `same_creative_count`, `multiple_versions`. Missing values are `""` / `[]` / `0`
  / `false`; the original seven fields are unchanged.
- **New optional filters:** `active_status` (`all|active|inactive`) and
  `media_type` (`all|image|video`) on `ad_search` and on `ad_watch add`. They are
  query-string parameters on the same single `www.facebook.com` GET, stored on the
  watch entry when non-default, and each filtered watch keeps its own snapshot and
  report key. Invalid values return `invalid_active_status` / `invalid_media_type`.
- **`ad_check` and reports:** the changed-ad signature now includes `link_url`,
  `link_title` and `cta_text` (compared only when both the old and new record
  carry them). Bucket summaries include the new fields. HTML cards show the CTA
  and destination link (absolute `http(s)` only) plus creative-grouping and
  image-count badges; the digest adds `with_link`, `with_cta`, `with_images`,
  `with_same_creative`, `with_multiple_versions`.
- **Still absent, deliberately:** `platforms` (publisher placements),
  `page_likes`, `spend`, `impressions` and direct video file URLs are not in the
  public logged-out render and are not returned, estimated or sourced elsewhere.
  `has_video` is only the render's video-playback signal.
- **Invariants unchanged:** no key, account, cookie, third-party service or extra
  host; one read-only GET per query in the normal case (up to 6 attempts only when
  a render fails to parse, each retry cache-busted, inside a 60-second wall-clock
  cap); stdlib only;
  `plugin_data_dir("ads-intel")` is still the only filesystem path. Suite: **443
  passed** (`.venv/bin/python -m pytest tests -q`). `hermes plugins validate .`
  passes with the expected `invisible_unicode` caution from committed eval data and
  the informational isolation note, both quoted above.
