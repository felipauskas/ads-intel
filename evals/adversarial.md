# Eval C — adversarial / injection

Run date: 2026-11-06 (local +04, UTC+04:00)
Repo: `~/coding-projects/ads-intel`, HEAD `96c0b3d` (`feat: summary null-coercion, filter echo, completeness meta (136 tests)`).
Host: macOS 27.2 (arm64), Python 3.14.10 `./.venv/bin/python`. Mode: local, offline (fake `web_extract` dispatch), no network. No source or test file was modified; only `evals/adversarial.md` and its probe were added.

Probe: `./.venv/bin/python evals/adversarial_probe.py` — 250 assertions, 233 pass, 17 fail grouped into 6 findings below.

Method: every report is parsed with `html.parser` and the tag/attribute tree is asserted structurally — forbidden tags (`script img iframe object embed svg math link base form input video audio source template`), `on*` attributes, `src`/`srcset`/`formaction`/`action`, `style` containing `expression|url(|javascript:`, and any `href` not starting `http(s)://`. Text payloads are additionally checked to decode back verbatim (no double-escaping). The strongest case was also opened in a real Chromium via CDP.

---

## Verdict

| Claim | Result |
|---|---|
| No script execution | **PASS** — real browser: `window.__xss === undefined`, `document.scripts.length === 0`, title unchanged, 0 `on*` attributes |
| No `<img>` / external resource | **PASS** — 0 `img`, 0 `iframe/object/embed/svg`, no `src=` produced by rendering |
| No parameter injection (`country`, `query`, filters) | **PASS** — strict `^[A-Z]{2}$` / enum validation; `q` is percent-encoded; `country=US&q=evil` rejected |
| No crashes | **FAIL on 1 reachable path** (`ad_search` `limit=inf`, F1); 3 internal-API crash classes not reachable through `ad_check` (F2–F4) |
| Fail-safe diffs | **PASS** — partial render suppresses `ended` and merges the baseline; parse failure/blank/corrupt snapshot never fabricate `ended` |
| No raw HTML injection in any text field | **PASS** — all 16 payloads in 5 fields escape structurally |

The report path itself is clean: no injection escape was found in 80 text-field cases, 21 URL cases, 4 attribute-id cases, and a full-report sweep. The failures are robustness/contract issues, not XSS.

---

## Payload corpus (exact inputs)

All of these were injected, one at a time, into `page_name`, `creative_text`, `status`, `first_seen`, `last_seen` (16 × 5 = 80 cases):

| # | Exact payload |
|---|---|
| 1 | `<script>alert(1)</script>` |
| 2 | `"><script>alert(document.domain)</script>` |
| 3 | `' onmouseover='alert(1)` |
| 4 | `<img src=x onerror=alert(1)>` |
| 5 | `"><img src=x onerror=alert(1)>` |
| 6 | `javascript:alert(1)` |
| 7 | `JaVaScRiPt:alert(1)` |
| 8 | `java\tscript:alert(1)` (literal TAB) |
| 9 | `data:text/html,<script>alert(1)</script>` |
| 10 | `vbscript:msgbox(1)` |
| 11 | `"><svg/onload=alert(1)>` |
| 12 | `&lt;script&gt;alert(1)&lt;/script&gt;` |
| 13 | `</title><script>alert(1)</script>` |
| 14 | `</style><script>alert(1)</script>` |
| 15 | `<!--<script>alert(1)</script>-->` |
| 16 | `\u2028\u2029<script>alert(1)</script>` (literal U+2028/U+2029) |

Result for every one: rendered as escaped text (`&lt;script&gt;…`), unchanged by the parser, no element or attribute created. `&lt;script&gt;` (case 12) round-trips to the literal text `&lt;script&gt;…`, i.e. exactly one escape pass — no double-escape bug.

`id` attribute cases (4): `1" onmouseover="alert(1)`, `<script>alert(1)</script>`, `1"><img src=x>`, `"><svg onload=1>` → decoded `data-ad-id` equals the input verbatim, no attribute break-out.

### Real-browser confirmation

`report.write_report` was given `query`, `meta.checked_at`, `page_name`, `creative_text`, `status`, `first_seen`, `last_seen`, `cta_text`, `link_title` = `<script>window.__xss=(window.__xss||0)+1;document.title="PWNED"</script>` and `creative_text` also `<img src=x onerror="window.__xss=(window.__xss||0)+2">`, with `library_url`/`link_url` = `javascript:window.__xss=9`. Opened `file:///…/report.html` in Chromium:

```
xss: "undefined"      title: 'Ad check — <script>…</script> (US)'
scripts: 0            imgs: 0        iframes: 0
handlers: 0           hrefs: []      body text: literal escaped payload
```

No dialog, no global mutation, no image request, no link.

---

## URL handling

`library_url` and `link_url` were each set to:

```
javascript:alert(1)
JaVaScRiPt:alert(1)
 javascript:alert(1)          (leading space)
java\tscript:alert(1)         (TAB)
data:text/html,<script>alert(1)</script>
vbscript:msgbox(1)
//evil.example/x
/\evil.example
http://ok.example/?q=<script>
https://ok.example/"><script>alert(1)</script>
```

| Input class | Observed |
|---|---|
| every non-`http(s)` scheme / protocol-relative / relative | dropped to `""`; no `href` emitted, CTA falls back to inert `<span class="cta-text">` |
| `http://ok.example/?q=<script>` | kept as href `http://ok.example/?q=<script>` (scheme valid; query is the advertiser's own URL, and `<` is escaped in the attribute) |
| `https://ok.example/"><script>…` | href attribute value round-trips exactly, `"` escaped as `&quot;`; no new attribute |

`page_url` is never emitted as an href today (checked: no `javascript:` href appears when only `page_url` is hostile).

## Parameter injection

`country` is validated by `_COUNTRY_RE = ^[A-Z]{2}$` in `sources.build_url` and again in `tools._requested_country`. All of these raise `ValueError("invalid_country")` / return `{"error":"invalid_country"}`:

```
US&q=evil   us   U1   USA   "U S"   "US\n"   "US\x00"   ""   None*   1   ["US"]   "ＵＳ" (fullwidth)   "US;"
```

\* `None` at the tool layer is treated as an omitted field (US), per the documented null rule; it does not inject.

`query` is percent-encoded byte-wise (`_quote_plus`, unreserved `A-Za-z0-9-_.~` only). Each of these produced a URL where `parse_qs` returns `country=["US"]` and `q=[<input verbatim>]`:

```
nike&country=XX   "a b+c"   %00   nike#frag   nike?x=1   "nike\r\nX: y"   nike'/x
```

`active_status` / `media_type` reject out-of-vocabulary values including `active&country=XX`, `video&x=1`, `ACTIVE`, `""` with `ValueError("invalid_active_status")` / `invalid_media_type`.

A 1,000,000-char query builds a 1,000,126-char URL without crashing (encoded, no injection). A lone surrogate `"\ud800"` raises `UnicodeEncodeError` inside the fetch try-block and surfaces as `{"error": "fetch_failed: …"}`, not a crash.

## Structural sweep and size

- All 16 payloads in all 5 text fields plus hostile `checked_at` in one report (`J.full_report`): 15,487 bytes, parser errors `[]`.
- `write_report` to disk + digest round-trip: HTML clean, digest valid JSON.
- 40k repetitions of `<script>` and `<img onerror=x>` in two fields: every occurrence escaped, no crash.
- `creative_text` = 2,000,000 × `A`: renders in 0.00 s, 2.0 MB output.
- 20,000 ads: renders in 0.05 s, 12.0 MB output, 20,000 `data-ad-id` present.
- `id` = 100,000 digits: renders (203 KB), no crash.
- `page_name`/`creative_text` = 300,000 × `|`: 903 KB output, no crash.
- Parser: 50,000 cards / 6.59 MB markdown parses in 0.34 s; a single 5 MB creative card in 0.01 s.

---

## Fail-safe diff verification

End-to-end through `tools.ad_check` with a fake dispatch and a temp data dir, one watch (`query="q"`, US):

| Step | Feed | Observed |
|---|---|---|
| seed | 3 cards (ids 1,2,3) | `new=3 ended=0 changed=0 partial=false` |
| partial | 1 card (id 1) + `[TRUNCATED] middle omitted` footer | `new=0 ended=0 changed=0 partial=true`; baseline still `{1,2,3}` (merged, not shrunk) |
| restored complete | 3 cards | `0/0/0`, no phantom "new" |
| one remains | 1 card | `ended=2` (ids 2,3), correctly reported |
| parse failure | `**Sponsored**` + `Library ID: nope` | row `{skipped:true, reason:"parse_failed", partial:true, artifacts:{error}}`; `ended` absent; baseline untouched |
| blank page | `Ad Library\n\n* * *\n\nFilters` | row `{skipped:true, reason:"fetch_empty", partial:true}`; baseline untouched |
| corrupt baseline | `{"ads": "notadict"}` in the snapshot file | row `error: "'str' object has no attribute 'items'"`, `partial:true`; no snapshot write, no false `ended` |

Status-flip semantics also hold: an ad that flips `active → inactive` is `ended` even while present (`diffing.diff_snapshots`), and a baseline that predates `link_url`/`cta_text` is not reported as `changed` when those fields appear (missing keys are excluded from the signature).

Corrupt on-disk state never raises out of `load_snapshot`/`watch_list`: `{bad json`, `[]`, `null`, `"str"`, `{"ads":"notadict"}` load as a dict/empty; `{bad`, `{"a":1}`, `[1,null,"x",{}]`, `[" "]`, `[[1]]` yield a list of valid entries only.

---

## Findings

### F1 — `ad_search` lets `OverflowError` escape (Medium, reachable)

Exact input (JSON as an MCP host would send it):

```json
{"query": "x", "limit": 1e309}
```

`json.loads` turns `1e309` into `float('inf')`; `tools.ad_search` does

```python
try:
    limit = int(args.get("limit", 20))
except (TypeError, ValueError):
```

`int(inf)` raises `OverflowError`, which is not caught, so the handler raises instead of returning `{"error": ...}`. Every other bad input in the 15-case tool matrix returns JSON. Repro:

```
python -c 'import tools; tools.ad_search({"query":"x","limit":float("inf")})'
# OverflowError: cannot convert float infinity to integer
```

Fix: add `OverflowError` to the tuple (or use `math.isfinite`), returning `{"error": "invalid limit"}`.

### F2 — `report.build_html` crashes on non-dict `diff`/`meta` (Low, internal API)

Exact inputs: `build_html("q", None, {...}, {...})`, `build_html("q", [], …)`, `build_html("q", "str", …)`, `build_html("q", {}, {...}, None)`.

`build_html` calls `diff.get(...)` / `meta.get(...)` directly, so `None`/`list`/`str` raise `AttributeError`. `write_report` normalizes (`diff = diff or {}`, `meta = dict(meta or {})`) and `ad_check` always passes dicts, so the tool path is safe — but the function is public and the `diff or {}` idiom in `write_report` suggests `None` was meant to be tolerated.

### F3 — `diffing.diff_snapshots` crashes on non-dict ads payload (Low)

Exact inputs: `diff_snapshots(None, {"ads": {}})`, `diff_snapshots({"ads": "notadict"}, {"ads": {}})`.

`old.get("ads") or {}` returns the string `"notadict"`, then `old_ads.items()` raises `AttributeError`. Within `ad_check` this is caught and surfaced as an error row (no snapshot write, no false `ended`), which is fail-safe but loses the check. A corrupt snapshot with `"ads": "junk"` is the only realistic producer.

### F4 — `same_creative_count` numeric extremes break report rendering (Low)

Exact inputs, injected as the ad's `same_creative_count`:

| Value | Exception |
|---|---|
| `float('inf')` (JSON `1e999`) | `OverflowError: cannot convert float infinity to integer` in `report._same_creative_count` |
| `10**5000` (integer > 4300 digits) | `ValueError: Exceeds the limit (4300 digits) for integer string conversion` when the badge formats it |

`_same_creative_count` catches `(TypeError, ValueError)` but not `OverflowError`; the digit-limit error comes from `f"{same}"` in `_render_badges`, not from `int()`. A 5000-digit *string* is caught (→ 0). Inside `ad_check` the report write fails into `artifacts: {error}` and the check still succeeds, so this is degradation, not tool failure.

### F5 — Short malformed bodies are read as "zero ads" instead of an error (Medium-low)

Exact dispatch payloads (raw strings returned by `web_extract`):

```
{not json
{"results": [{"content":
"just a string"
null
true
12345
```

Each returns `([], meta)` rather than raising. `fetch_ads_with_meta` sees a string starting with `{`/`[`, fails `json.loads`, and falls through to `parse_library_markdown(content)`; under 5,000 chars with no card markers that is by design an empty results page, so it returns `[]`.

Consequence: in `ad_check` a body-truncated/corrupted fetch that arrives as a short string is treated as a genuinely empty page. With a prior baseline it becomes `fetch_empty` (safe, baseline kept). With **no** prior baseline it seeds an empty snapshot and reports a successful 0-ad check — the corruption is silent. It cannot fabricate `ended` (empty ads short-circuits before diffing), so it is fail-safe for endings but masks transport failure.

Fix: when a payload begins with `{` or `[` but fails to decode, raise `FetchError("malformed json")` instead of retrying it as markdown. Markdown renders never begin with a bare `{`.

### F6 — String `partial:"false"` is truthy (Info, cosmetic)

`build_html` uses `partial = bool(meta.get("partial"))`, so `{"partial": "false"}` renders the amber "Partial listing" banner. `ad_check` builds this flag itself (`not complete`) and always passes a bool, so only a direct API caller with a string is affected. Same class: `{"partial": {"x": 1}}` → banner on.

### Non-findings (verified safe)

- Every `javascript:`/`data:`/`vbscript:`/protocol-relative URL is dropped, including mixed case, TAB-obfuscated, and leading-space forms.
- Attribute quoting (`data-ad-id`, `title`, `href`) survives embedded `"`, `'`, `<`, `>`, U+2028/9.
- `country` cannot smuggle `&q=`, whitespace, NUL, fullwidth letters, or a third character.
- `images` entries are http(s)-filtered and non-strings dropped; `page_id` is digits-only; `has_video`/`multiple_versions` use strict boolean parsing (`"false"` → `False`).
- Malformed JSON of ≥5,000 chars without markers raises `ParseError`; JSON arrays of non-dicts raise `ParseError`; `[]`/`{}`/`{"results": []}` raise `FetchError`.
- No `<script>` exists anywhere in the generated document; the CSS is a constant with no interpolation.

---

## Coverage counts

| Group | Assertions |
|---|---|
| A/A2 text-field XSS (5 fields × 16 payloads; + round-trip) | 80 + 15 |
| B URL schemes (`library_url`, `link_url`, `page_url`) | 21 |
| C `id`/attribute injection | 4 |
| D country / query / filter injection | 29 |
| E huge inputs (2 MB text, 20k ads, 100k-digit id, nested markup, 600 KB) | 5 |
| F malformed payloads / transport / hostile JSON ad fields | 30 |
| G non-dict diff/meta/digest shapes | 17 |
| H fail-safe diffs, corrupt snapshot/watchlist, template strings | 23 |
| I tool argument abuse | 15 |
| J full-report + on-disk sweep | 3 |
| K numeric-field abuse | 8 |

233/250 pass. The 17 failures are exactly F1 (1), F2 (5), F3 (2), F4 (3), F5 (6). No injection, no script execution, no image or event-handler emission in any case.
