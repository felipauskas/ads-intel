# Eval B — Functional parity (offline, fixture-driven)

**Verdict: PASS with 3 parity gaps** — all three tools work end-to-end from the
fixture with no network; one real behavioral mismatch (advertiser watch can
adopt an unstamped unfiltered baseline) and two contract/semantic gaps are
documented below with minimal repros.

- Repo: `/Users/felipevleon/coding-projects/ads-intel` @ `96c0b3d`
- Input: `tests/fixtures/library_page.md` only. Dispatch stub serves that
  render; the stub also applies the URL's `active_status`/`media_type`
  server-side filter to emulate the real library (the tool never filters
  client-side, it passes the params through).
- No network, no code changes. Harness ran under `.venv/bin/python`; data dir
  redirected to a temp dir via `store._data_dir`.
- Fixture facts (asserted): **28 ads** (24 `Inactive`/`ended`, 4 `Active`),
  **5 video**, **4 Nike** ads (`1785179045778580`, `962050096457659`,
  `1700063364126216`, `1841713136987087`), 16 distinct pages.

## Expected vs actual

| Scenario | Expected | Actual | Verdict |
| --- | --- | --- | --- |
| `ad_search{query:'nike', limit:50}` | all 28, complete | 28, `complete:true` | PASS |
| `ad_search{query:'nike'}` (default limit) | first 20, `complete:false` | 20, `complete:false`, `fetched:20` | PASS |
| `ad_search{advertiser:'Nike'}` | 4 Nike only, resolved 0.80 | 4, all `page_name=Nike`, `resolved:{page_name:'Nike',score:0.8}` | PASS |
| `ad_search{advertiser:'nike'}` | case-insensitive resolve | same 4, score 0.8 | PASS |
| `ad_search{advertiser:'Nike', limit:2}` | 2 of 4, `complete:false` | 2, `complete:false`, `fetched:2` | PASS |
| `ad_search{active_status:'inactive'}` | 24, URL `active_status=inactive` | 24, URL correct | PASS (see M2) |
| `ad_search{media_type:'video'}` | 5, all `has_video:true` | 5, all true, URL `media_type=video` | PASS |
| `ad_search{advertiser:'Nike', media_type:'video'}` | no Nike video ad exists → `name_not_matched` | `{"error":"name_not_matched",...}` | PASS |
| Invalid filter (`paused`, `carousel`) on `ad_watch add` | `invalid_*` before write | exact error, no watch entry | PASS |
| `ad_watch add` ×4 variants | non-defaults stored only | 4 distinct entries: `{query,country}`, `+advertiser`, `+active_status`, `+media_type` | PASS |
| `ad_check` first run (all 5 watches) | seed baseline | unfiltered new=20 `partial:true`; Nike new=4 `partial:false`; inactive new=20 `partial:true`; video new=5 `partial:false`; Nike+video `name_not_matched` | PASS |
| `ad_check` second run vs mutated fixture | new/ended/changed | Nike: new=1 ended=2 changed=1; unfiltered: new=0 ended=1 changed=1 (`partial:true`, missing ad suppressed, status flip reported); inactive: new=1 changed=1; video: none | PASS |
| Filtered watch vs existing unfiltered baseline | never adopt | Nike new=4/ended=0; inactive new=20/ended=0; video new=5/ended=0; unfiltered snapshot unchanged at 20 | PASS |
| Advertiser watch + **unstamped** unfiltered baseline | should not adopt | **adopts → 24 false `ended`** | **FAIL (M3, documented legacy exception)** |

Counts and diff buckets are correct in every non-legacy scenario. Status-flip
semantics are right: an id still present but flipped `Active`→`Inactive` is
reported as `ended`, not `changed`.

## 16-field audit

`ad_search` ads: **16/16 on every ad in all five scenarios**, no extra keys, no
`null`s, types as documented (`str` ×12, `list`, `bool`, `int`, `bool`).
Fields checked: `id, page_name, status, first_seen, last_seen, creative_text,
library_url, page_url, page_id, link_url, link_title, cta_text, images,
has_video, same_creative_count, multiple_versions`.

`ad_check` bucket summaries: **14/16** — see M1.

## Mismatches

### M1 — `ad_check` diff buckets drop 2 of the 16 fields (medium)

`tools._SUMMARY_KEYS` omits `last_seen` and `creative_text`, so every
`new`/`ended`/`changed` item is a 14-key object. A caller asking "what changed"
gets `changed_ads: 1` with no creative copy to show what changed, and no
`last_seen`; only `ad_search` has full parity.

Evidence — bucket keys observed:

```
cta_text, first_seen, has_video, id, images, library_url, link_title,
link_url, multiple_versions, page_id, page_name, page_url,
same_creative_count, status
```

Minimal repro:

```bash
cd /Users/felipevleon/coding-projects/ads-intel && .venv/bin/python - <<'PY'
import json, sys, tempfile
sys.path.insert(0, '.')
import tools
from pathlib import Path
d = Path(tempfile.mkdtemp())
tools.store._data_dir = lambda: d
md = Path('tests/fixtures/library_page.md').read_text()
class Ctx:
    def dispatch_tool(self, name, args):
        return {'results': [{'content': md}]}
tools.set_ctx(Ctx())
tools.ad_watch({'action': 'add', 'query': 'nike'})
row = json.loads(tools.ad_check({}))['results'][0]
print(sorted(row['new'][0]))
PY
```

Expected 16 keys; actual 14 (missing `last_seen`, `creative_text`). Note the
`schema` text only promises the "enriched fields" subset, so this is a
contract gap rather than a crash — but it is not 16-field parity.

### M2 — Filter vocabulary says `inactive`, surfaced `status` says `ended` (low/medium)

`ad_search{active_status:'inactive'}` returns 24 ads whose `status` is
`"ended"` for all of them (`sources._parse_block` maps `Inactive` → `ended`).
The same applies to `ad_check` buckets. A caller filtering `inactive` cannot
round-trip on `status == "inactive"`; the enum in `schemas.py` and the value in
the payload disagree.

Minimal repro:

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, '.')
import sources
from pathlib import Path
ads = sources.parse_library_markdown(Path('tests/fixtures/library_page.md').read_text())
print({a['status'] for a in ads}, sum(a['status'] == 'ended' for a in ads))
# {'active', 'ended'} 24  — the 24 cards whose render says "Inactive"
print(next(a['status'] for a in ads if a['id'] == '1785179045778580'))  # 'ended'
PY
```

The `Inactive` → `ended` mapping is at `sources.py:371`. `ad_search` just
returns those parsed ads when the library applies `active_status=inactive`.

Either surface `inactive` (and keep `ended` as the diff-internal token) or
document the mapping in the field table.

### M3 — Advertiser watch adopts an unstamped unfiltered baseline → false endings (medium; documented legacy exception)

With an unfiltered snapshot at the country-keyed path that predates the
`advertiser` stamp, adding `advertiser='Nike'` and running `ad_check` loads
that file (fallback guard only rejects files that *carry* an
`advertiser`/filter stamp). The 24 non-Nike ads are then reported `ended` on
the first filtered run. This is called out in README as a one-time upgrade
exception, but it contradicts the blanket "filtered watches never adopt
unfiltered baselines" requirement.

Evidence: `new_ads: 0, ended_ads: 24`, `ended` pages include Deanna Silva,
Depop, Hepsiburada, IControl, JD Sports, … — none are Nike.

Minimal repro:

```bash
.venv/bin/python - <<'PY'
import json, sys, tempfile; sys.path.insert(0, '.')
import tools, sources
from pathlib import Path
d = Path(tempfile.mkdtemp())
tools.store._data_dir = lambda: d
ads = {a['id']: a for a in sources.parse_library_markdown(Path('tests/fixtures/library_page.md').read_text())}
p = tools.store._snapshot_path('nike', 'US'); p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({'query': 'nike', 'ads': ads}))       # unstamped, pre-advertiser shape
class Ctx:
    def dispatch_tool(self, n, a): return {'results': [{'content': Path('tests/fixtures/library_page.md').read_text()}]}
tools.set_ctx(Ctx())
tools.ad_watch({'action': 'add', 'query': 'nike', 'advertiser': 'Nike'})
r = json.loads(tools.ad_check({}))['results'][0]
print(r['new_ads'], r['ended_ads'])                            # 0 24
PY
```

Status/media-filtered watches do **not** have this hole: `store._snapshot_candidates`
skips the unfiltered path entirely when a filter is non-default (verified:
`active_status=inactive` on the same unstamped baseline → new=20, ended=0).
Fix direction: refuse the unfiltered fallback whenever `advertiser` is set too,
or only adopt a legacy file when it carries an explicit legacy marker.

## Known limitations confirmed (not defects)

- **Unfiltered `ad_check` caps at 20:** with 28 fixture ads the first run seeds
  only 20 and reports `partial:true`; 8 ads are never tracked. Documented in
  README. `new`/`changed` stay accurate; `ended` is suppressed for absent ids.
- **Partial second run:** the removed Nike ad is *not* reported `ended` on the
  unfiltered watch (masked because the render is clipped), while the
  `Active→Inactive` flip *is* (`ended_ads:1`). Matches the documented fail-safe.
- **`advertiser=Nike, media_type=video` never seeds:** every check returns
  `name_not_matched` because the fixture has no Nike video ad. Correct, but a
  watch in this state produces no baseline and no report forever.
- `ad_watch remove` deletes all filter variants of a query (documented).

## Resolution (post-`b3a0c2c`)

- **M1 — fixed** in `aa61ac3`: `_SUMMARY_KEYS` carries all 16 fields
  (`last_seen`, `creative_text` included) and every bucket is 16 keys wide.
  Regression guard: `test_check_bucket_items_are_sixteen_fields` and
  `test_changed_and_ended_buckets_are_sixteen_fields`.
- **M2 — documented, `ended` kept as the surfaced status.** Surfacing
  `inactive` would change the diff vocabulary, reports and every existing
  baseline, so the smaller contract change won: the library's `Inactive`
  label continues to surface as `status: "ended"`, and the mapping is stated
  in README, `schemas.AD_SEARCH`/`AD_CHECK`, and locked by
  `tests/test_schemas.py`.
- **M3 — fixed** in `aa61ac3`: `store._snapshot_candidates` treats
  `advertiser` as scoped, so neither the unfiltered country-keyed file nor
  the pre-country `sha1(query)` fallback is offered to an advertiser watch.
  Regression guards: the tool-level advertiser test and the store-level
  stamped/unstamped/legacy tests.

## Blockers

None. All findings are reproducible offline from the fixture; no network or
credentials were used. No repository code was modified.
