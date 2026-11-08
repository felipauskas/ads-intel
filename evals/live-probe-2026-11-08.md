# Live probe — ad_search / web_extract against the real Meta Ad Library

Run date: 2026-11-08 11:16–11:25 (+04, UTC+04:00).
Repo: `~/coding-projects/ads-intel`, HEAD `d3508ea`. Host macOS 27.2 (arm64), Python 3.14.10 (`./.venv/bin/python`). Live network, real `web_extract` host tool; `ad_search` invoked through the running Hermes plugin (`hermes plugins doctor ads-intel` → OK: 3 tools registered, standalone, v0.2.0).
No source or test file was modified. Added: this file + `evals/raw/`.

---

## Verdict

`ad_search` returns a **silent zero** for KFC (AE and US) and McDonald's (US) while the same host fetches and parses BMW fine. The zero is a **transport/render failure**, not "no ads": the page comes back as navigation chrome only (≈2.0–5.2 KB) with no card markers and no empty-state text.

| Probe | Result |
|---|---|
| `build_url("KFC", country="AE")` | `https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=AE&q=KFC&media_type=all&search_type=keyword_unordered` |
| `ad_search(query="KFC", country="AE")` (live) | `{"count": 0, "ads": []}` — **no error field** |
| `ad_search(query="McDonald's", country="US", limit=3)` (live) | `{"count": 0, "ads": []}` — no error field |
| `ad_search(query="BMW", country="US", limit=3)` (live) | `{"count": 3, "ads": [...]}` — works |
| Direct `web_extract([KFC-AE url], char_limit=120000)` | `results[0] = {url, title:"Ad Library", content, error:null}`; **content 5,145 chars**; `Library ID` ×0, `Sponsored` ×0, `"No ads"` ×0, `* * *` ×1, `Log in` ×1 |
| `parse_library_markdown(that content)` | raises `ParseError: long render (5145 chars) with no card markers` |
| Control: BMW US via same host tool | content 58,230 chars, `Library ID` ×30, `Sponsored` ×30, parses to **29 ads**, `meta={"complete": False, "fetched": 3, "total_returned": 29, "fetched_chars": 58230, "char_limit": 120000}` |
| Control: Burger King AE | content 77,888 chars, `Library ID` ×29 → renders fine |

---

## Exact result shape (live host contract)

`web_extract` returns exactly:

```json
{
  "results": [
    {
      "url": "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=AE&q=KFC&media_type=all&search_type=keyword_unordered",
      "title": "Ad Library",
      "content": "<markdown string>",
      "error": null
    }
  ]
}
```

Four keys per result; `error: null` on success. The stub in the tests (`{'results':[{'content': md}]}`) is a **subset** — no `url`, `title` or `error`. The repo tolerates that (`_content_from_payload`), so the tests are not wrong, just weaker than the live object.

`ad_search` live output shape (as exposed to the caller) is a **reduced 2-key object**:

```json
{"count": 0, "ads": []}
{"count": 3, "ads": [{"id","page_name","status","first_seen","last_seen","creative_text","library_url"}, ...]}
```

The repo's handler returns `{count, complete, fetched, country, ads}` (tools.py:160-169) — the live exposure trims `complete` / `fetched` / `country`, so **a caller cannot distinguish "complete empty listing" from "partial"**. Verified by calling `tools.ad_search` locally with a real dispatch: it emits the fuller 5-key dict, so the trimming happens in the plugin exposure layer, not in `tools.py`.

---

## The failure, step by step

1. The URL is correct (`sources.build_url` output is well formed; `hermes plugins doctor` passes).
2. The host returns HTTP-OK markdown, `error: null`, but the body is **chrome only**: header/nav, the full 250-country `<select>` list, the search box, footer. In the failed body the text after `Search by keyword or advertiser` jumps straight to `[Log in …]` → nav → footer. There is no results container, no `Library ID`, no `**Sponsored**`, and — importantly — **no empty-state wording** ("No ads" / "We didn't find any ads" both absent). A genuinely empty listing would say something.
3. Every failed render also keeps the **un-rewritten URL**. Successful renders come back at the canonical URL Facebook rewrites to (`…&is_targeted_country=false&…&sort_data[mode]=total_impressions&sort_data[direction]=desc`). Failure = URL unchanged → the SPA never re-rendered the results step. `resp_url == req_url` is therefore a usable **failure signal** (true for every failed probe, false for BMW US and Burger King AE).
4. Parsing then depends on body size, and both branches are wrong for production:
   - **5,145–5,210 chars** (`KFC AE`, `KFC US`, `McDonald's US`, `BMW AE`): above `_MAX_EMPTY_RENDER_CHARS = 5000` → `ParseError` → the handler would return `{"error": "parse_failed: …"}`.
   - **2,055–2,089 chars** (shorter shell, e.g. `q=kfc`, `q=KFC chicken`): **below 5000** → `parse_library_markdown` returns `[]` and `complete` is computed `True` (len < budget, 0 < limit, no truncation marker). This is the exact path that produces the live `{"count": 0, "ads": []}` with **no error** — a transport failure reported as a confident empty result.

Because the live tool reported `count: 0` with no `error`, the production fetch evidently hit the **short-shell** variant (< 5000 chars), not the 5,145 one. Both are the same bug viewed at different sizes.

---

## Cache caveat (matters for any retry / probe design)

The host caches extractions in `~/.hermes/profiles/partner/cache/web/extract-index.json` (157 entries; each maps URL → `.cache.md` file + `content_sha256` + `fetched_at`).

- Six consecutive `web_extract` calls for the same KFC-AE URL returned byte-identical 5,145-char bodies in **0.07 s total** → served from cache, not refetched.
- The index holds the failed and the good renders side by side: `country=AE&q=KFC` → 5,163 B file; `country=AE&q=BMW` → 5,163 B file (same shell); `country=US&q=BMW` → 58,879 B file (full render); `country=AE&q=KFC%20chicken` → 2,089 B file.
- So: **retrying the same URL proves nothing.** Any flake measurement or retry-on-failure logic must vary a harmless query parameter (or bust the cache) or it will keep replaying the recorded failure — and, worse, a cached failure is indistinguishable from a live one downstream.

---

## What is *not* the cause (ruled out)

| Hypothesis | Evidence |
|---|---|
| `build_url` wrong / URL malformed | URL is well formed; BMW and Burger King use the identical builder and succeed. |
| Country `AE` unsupported | Burger King AE returned 77,888 chars / 29 ads. |
| Query `KFC` / apostrophe escaping | `KFC` US fails the same way; `McDonalds` (no apostrophe) also fails; lowercase `kfc` fails differently (shorter shell). Not an escaping bug. |
| Login wall | No login prompt, no "Log in to continue"; nav is public. `Log in` appears once as a plain nav link, as on the working BMW page. |
| Rate limit / block | `error: null`, HTTP-OK; BMW fetched successfully seconds later from the same host. |
| Parser drift | Parser is fine — BMW parses to 29 ads from the same tool, same char budget. |
| Plugin install / manifest | `hermes plugins doctor ads-intel` → runtime discovery, manifest, import, registration all OK. |

The remaining cause is **render timing/hydration on the host's fetch**: the extractor sometimes snapshots the page before the results grid hydrates, returning the shell. It is not deterministic per query (BMW AE failed while BMW US succeeded; Burger King AE succeeded).

---

## Reproduced commands (verbatim)

```python
import sources
sources.build_url("KFC", country="AE")
# 'https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=AE&q=KFC&media_type=all&search_type=keyword_unordered'

from hermes_tools import web_extract
r = web_extract([sources.build_url("KFC", country="AE")], char_limit=120000)
# results[0]['content'] -> 5145 chars, 'Library ID' x0, error None

sources.fetch_ads_with_meta("KFC", limit=3, country="AE",
    dispatch=lambda n, a: web_extract(**a))
# ParseError: long render (5145 chars) with no card markers
```

`tools.ad_search({"query": "KFC", "country": "AE", "limit": 3})` with that dispatch →
`{"error": "parse_failed: long render (5145 chars) with no card markers", "cards_seen": 0}`
while the live tool returns `{"count": 0, "ads": []}` — confirming the live call hit the <5000-char shell.

---

## Raw artefacts (verbatim, not summarised)

- `evals/raw/web_extract-KFC-AE.json` — full `web_extract` response object for KFC/AE (5,145-char content, included as JSON).
- `evals/raw/web_extract-KFC-AE.md` — the content string alone, verbatim (starts `[_Meta Ad Library_](…)`, ends `[English (US)](https://www.facebook.com/language/)`; contains the whole country list, `* * *`, no ad card).
- `evals/raw/ad_search-live.json` — the three live `ad_search` payloads (KFC AE, McDonald's US, BMW US) exactly as returned.

## Suggested next step (not applied — no source edits made)

Treat a short/un-rewritten render as a **fetch failure, not an empty listing**: require either card markers, an explicit empty-state phrase, or `resp_url` carrying `is_targeted_country`/`sort_data` before letting 0 ads stand as `complete: True`; and retry with a cache-busting parameter before concluding. Also worth exposing `complete` in the live `ad_search` shape, since it is currently dropped.
