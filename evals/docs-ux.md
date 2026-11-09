# EVAL D — docs UX (README only)

Scope: `README.md` at commit `96c0b3d`. No code was read. Every statement below is graded on what the README alone tells a new user.

Method: treat the README as the only artefact. For each of the four questions, record whether a competent reader could answer it without opening the source, and note the exact place the doc leaves them stuck.

## Scorecard

| Question | Answerable from README? | Confident? | Notes |
| --- | --- | --- | --- |
| 1. What tools exist? | Yes | High | Three tools, named and headed. |
| 2. Fields each returns? | Partly | Low for 2 of 3 | `ad_search` is table-documented; `ad_watch` and `ad_check` return shapes are never specified. |
| 3. Limits? | Yes | High | Dedicated `## Limitations` plus inline ceilings. |
| 4. How to install? | Yes, with a caveat | Medium | Local `file://` flow only; the `insecure source` warning is pre-empted. |

## 1. What tools exist

Answered. The intro names all three in one sentence — `ad_search`, `ad_watch`, `ad_check` — and each gets its own `###` section with a short statement of purpose:

- `ad_search` — find ads a brand, advertiser or keyword is running.
- `ad_watch` — manage the local watchlist (`add` / `remove` / `list`).
- `ad_check` — fetch every watch entry, diff against the last snapshot, report changes.

The "Try it in 60 seconds" section maps plain-language prompts to each tool, which is the strongest part of the doc for a first-time reader: it answers "what do I type" before "what does it take". A reader finishes the first screen knowing there are three tools and roughly which one they want.

Minor: the doc never states whether these are the complete tool surface (they are, per the intro's "through three tools"), and the plugin name `ads-intel` survives in the prose with a stray `ad-intel` in the Keyword matching section (line 99: "`ad-intel`'s page-id and handle rungs"). A reader who has not seen the sibling project will read that as a typo or a fourth thing they are missing.

## 2. Fields each returns

Half-answered, and the gap is not signposted.

**`ad_search` — fully documented.** The return envelope is given as `{count, country, ads}` plus `advertiser` and `resolved` when filtering, and there is a 12-row field table with meaning and source per field: `id`, `page_name`, `status`, `first_seen`, `last_seen`, `creative_text`, `library_url`, `page_url`, `page_id`, `link_url`, `link_title`, `cta_text`, `images`, `has_video`, `same_creative_count`, `multiple_versions`. The "missing values are always `""` / `[]` / `0` / `false`, never absent keys" line is exactly the contract a caller needs, and it is stated once, in the right place. Error shapes are also named concretely (`invalid_country`, `invalid_active_status`, `invalid_media_type`, `name_not_matched` with `target`/`candidates`/`threshold`, `parse_failed: <detail>`), which is better than most READMEs manage.

**`ad_watch` — unspecified envelope.** The prose says what the actions do (add/remove/list), what is stored (`{query, country}` plus `advertiser` and any non-default filter), and that `remove` drops every entry for that query regardless of market. It never says what a call *returns*: no key list, no example payload, no error shapes. Does `add` echo the entry? Return a count? Return the whole watchlist? A caller writing against this doc has to guess.

**`ad_check` — semantics documented, structure not.** The diff vocabulary (`new` / `ended` / `changed` / `baseline` / `skipped`) is defined carefully, including the `fetch_empty` and `parse_failed` skip reasons and the `partial: true` suppression rule. But the response object itself is never shown. The doc mentions in passing that rows carry `partial` and (in the advertiser section) that a miss is "a row with `error` and `partial`", which implies per-entry rows — yet the reader is left to infer the container key, the row fields, and whether there is a top-level summary. There is no worked example of a `ad_check` result anywhere in the file.

**Verdict:** the field contract is excellent for one tool and absent for two. Since `ad_check` is the tool the whole watch loop exists for, this is the largest docs-UX hole in the README. It is also invisible: `## Tools` reads as if it covers all three uniformly, so a reader does not know to go looking elsewhere.

## 3. Limits

Answered, unusually well. A dedicated `## Limitations` section covers:

- **Markup fragility** — parser is one file (`sources.py`); total parse failure returns `parse_failed` and never writes an empty snapshot.
- **Truncation** — `char_limit=120000`; a full-budget render or a head+tail footer marks the read partial, merges ads, suppresses endings.
- **The 20-ad ceiling** — stated bluntly in bold: an unfiltered watch with 20+ live ads reports `partial: true`, endings are suppressed, `new`/`changed` stay accurate. The doc even gives the workaround (keep keyword watches narrow). An `advertiser` watch is **not** exempt: it filters the same rendered window (one page per query, `char_limit=120000`), so it is subject to the same 20-ad ceiling and `partial` flag rather than fetching the full listing.
- **No pagination in v1** — one page per query, surfaced via `complete` and `fetched` rather than failing silently.
- **Fields not available** — `platforms`, `page_likes`, `spend`, `impressions`, video file URLs; explicitly "reported as absent, not guessed".
- **Keyword vs. brand semantics** — a whole section on why `KFC` also matches `KFC UAE` mentions, and that `advertiser` is the fix.
- **Rate/legal posture** — one GET per watch per run, no retries, ToS not claimed, user responsible.

The strongest thing here is that the ceilings are framed as behaviour the caller can observe (`complete`, `partial`) rather than as apology prose. A reader can write correct code against this section.

Small friction: the 20-ad ceiling is restated three times (lines 104, 105, 106) with slightly different emphasis. It is the most important limit, so repetition is defensible, but the three paragraphs could be one and a reader skimming may think they are three separate limits.

## 4. How to install

Answered, but narrow. The flow is explicit and ordered:

```bash
cd /path/to/ads-intel
hermes plugins validate .
hermes plugins install "file://$PWD"
hermes plugins enable ads-intel
```

Good: it says up front that the plugin is **not published**, that there is no catalog entry, that the checkout must be a git repo (because Hermes installs from a `file://` URL), and it pre-empts the `insecure source` prompt so the user does not think they are being warned off a bad package. That is the right thing to disclose before the command, not after.

Gaps:

- **No prerequisite check.** No statement of Hermes version, Python version, or platform. A user on an old Hermes will find out from the tool call, not the README.
- **No verification step.** Nothing says how to confirm the install worked — e.g. that the three tools should appear in the session, or a first prompt that should succeed. The "Try it in 60 seconds" section is the nearest thing, but it starts with `validate`, not with "you should now see three tools".
- **No uninstall/upgrade path.** A local `file://` install that is later re-installed or removed has no documented command. Given the upgrade note in Disclosures (watchlist format migration), a user who upgrades has no stated procedure.
- **`cd /path/to/ads-intel` is a placeholder** — fine as a placeholder, but it is the only path shown, so a reader who does not already know where the checkout is has nothing to anchor on.

## What the README does better than expected

- Error shapes are enumerated, not hand-waved. Most docs say "returns an error"; this one names the codes.
- The empty-value contract (`""` / `[]` / `0` / `false`, keys always present) is stated once and applies to the whole field table — the single most useful sentence for anyone writing a consumer.
- The diff semantics have a worked definition per term, including the baseline case (first run reports everything as `new`) and the fail-safe case (a fetch failure is `skipped`, never "everything ended"). A reader cannot misread the first run as a bug.
- Disclosure section is honest about ToS and about the `~/.ads-intel-dev` fallback outside Hermes. It does not overclaim.

## Unanswered questions

Questions the README leaves open, ordered by how likely a new user hits them:

1. **What does `ad_watch` return?** No envelope, no keys, no example. (Highest impact — this is the first tool most users touch.)
2. **What does `ad_check` return?** Diff vocabulary is defined, but the response object, its row shape, and any top-level counts are never shown. No example output.
3. **Is `ad_search`'s `count` the number of ads returned or the number matched?** Given `complete: false` and `fetched`, these can differ; the doc defines `fetched` but never pins `count`.
4. **What are the `ad_check` row field names?** The doc mentions `partial` and `error` in prose but does not list the row schema.
5. **Does `ad_check` return per-entry rows keyed by query, or a flat list?** Implied per-entry; never stated.
6. **What Hermes version / Python version is required?** No prerequisite line anywhere.
7. **How do I verify the install worked?** No post-install check.
8. **How do I upgrade or uninstall a local `file://` plugin?** Upgrade migration is described for data, not for the install itself.
9. **What is the `resolved` object's exact shape?** Given as `{page_name, score}` — this one is actually answered.
10. **Is there a limit on watchlist size, or on ads per `advertiser` watch?** "Keeps every ad on the resolved page" with no upper bound.
11. **What happens if two watch entries resolve to the same query with different filters on `ad_check`?** Report keying is described for filenames; response keying is not.
12. **`ad-intel` (line 99) — typo or a different project the user needs?** Unclear from the README alone.

## Bottom line

Install and limits are documented to a standard most plugins do not reach. Tool *discovery* is clear. The failure is asymmetric return-value documentation: `ad_search` gets a full field table while `ad_watch` and `ad_check` — including the tool the product exists for — get behaviour prose and no schema. A reader can install this and know what it will not do, but cannot write a consumer against `ad_check` without opening `sources.py` or the store module. That is the single fix that would move this README from good to complete: one return-shape block and one example payload for each of the two undocumented tools.
