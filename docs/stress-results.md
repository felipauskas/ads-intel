# Stress test results — pre-publication gate

Audit date: 2026-11-09 (local +04, UTC+04:00)
Repo: `~/coding-projects/ads-intel`
HEAD: `440c513` (`fix(p3): meta surfacing, text bounds, narrow watch_remove, hygiene`) — re-run after the harness tamper-target fix (see addendum)
Host: macOS 27.2, Python 3.14.10 (`./.venv/bin/python`), binary tree clean apart from this branch's own commit.

Everything below is a local run. No push, no remote, no publish.

Harness: `scripts/stress_e2e.py` (stdlib only, no pytest dependency).

```
.venv/bin/python scripts/stress_e2e.py            # 50 offline iterations + concurrency + corruption
.venv/bin/python scripts/stress_e2e.py -n 200     # more iterations
.venv/bin/python scripts/stress_e2e.py --live     # real web_extract, run once
```

Offline mode needs no network: the only host seam (`web_extract`) is a stub that
returns the recorded render in `tests/fixtures/library_page.md`. URL building,
parsing, snapshotting, diffing and report writing all run for real. Every
iteration gets its own data directory (`store._data_dir` rebound to a fresh
temp dir, the same isolation the pytest fixtures use) and its own watch query,
so a failure names its own `iter-NNN`.

---

## 1. Offline end-to-end — 50/50 PASS

Per iteration: parse fixture → `ad_search` → `ad_watch add` → `ad_check`
(baseline) → `ad_check` (settle) → tamper one creative → `ad_check` (change) →
verify artifacts and digest counts.

```
workdir: <tmpdir>/ads-intel-stress-_21219b6   (per-run temp dir; host path elided)
repo:    <repo>
python:  3.14.10 (<repo>/.venv/bin/python)

== offline iterations: 50 ==
iter 001 PASS    15.0ms baseline=20 settle=0/0/0 changed=1
…
iter 050 PASS    13.4ms baseline=20 settle=0/0/0 changed=1

offline summary: iterations=50 failures=0 max_ms=15.0 total_s=0.67

== concurrency ==
threads=10 ops/thread=100 elapsed=97.02ms json_files=2 corrupt=0 exceptions=0
watch entries: expected=10 got=10 lost=0 snapshot_ads=1

== corruption resilience ==
corruption: PASS (degraded as contracted, no crash)

RESULT: PASS (0 failing section(s))
EXIT=0
```

Second run, `-n 20`: `20/20 PASS`, `max_ms=15.2`, `total_s=0.27`,
`RESULT: PASS (0 failing section(s))`, `EXIT=0`.

What each iteration asserted (all held 50/50):

| Step | Expectation |
|---|---|
| fixture parse | 28 ads, unique ids |
| `ad_search` | `count == 20` (default limit), dispatched `web_extract` once, URL carries `country=US` and the iteration's unique `q=` |
| baseline `ad_check` | `20 new / 0 ended / 0 changed`, `partial=True` (28 parsed > limit 20), snapshot holds 20 ads |
| settle `ad_check` | `0 / 0 / 0`, snapshot unchanged (no shrink from the partial run) |
| tampered `ad_check` | exactly `0 / 0 / 1`, `changed[0].id` is the tampered id |
| artifacts | HTML + digest exist, both inside the isolated data dir, banner reads `0 new / 0 ended / 1 changed`, digest `new/ended/changed == 0/0/1` and `total == snapshot size` |

Max single-iteration wall time: **15.0 ms**; 50 iterations: **0.67 s**. Each
iteration creates 3 artifact files plus a
snapshot, so the cost is dominated by `fsync`.

## 2. Full pytest suite, 3 consecutive runs

```
470 passed, 1 warning in 3.90s
470 passed, 1 warning in 4.36s
470 passed, 1 warning in 3.90s
```

**3/3 × 470 passed, 0 failed, no flakes, no ordering dependence.** (The warning
is pytest's own `callspec` deprecation notice, not a plugin failure.)

## 3. Live mode — 4/4 PASS (real host `web_extract`)

`--live` drives the plugin's own dispatch seam, which calls the real
`web_extract` tool in the Hermes runtime environment. The harness starts one
persistent bridge process using the command reported by
`hermes --print-runtime-command` (isolated interpreter + `hermes_bootstrap`, so
the configured extract backend and its dependencies are present). Requests and
responses are one JSON line each; log lines before the result marker are kept
and shown if the bridge fails. A fetch is retried at most once and every
attempt is recorded.

Run: `2026-11-06 13:16 +04`, `EXIT=0`.

| Query | Market | ads returned | search | check #1 (new/ended/changed) | check #2 (settle) | partial | artifacts |
|---|---|---|---|---|---|---|---|
| KFC | US | 10 | 3.56 s | 20 / 0 / 0 | 0 / 0 / 0 | yes | HTML+digest |
| KFC | AE | 10 | 2.67 s | 20 / 0 / 0 | 0 / 0 / 0 | yes | HTML+digest |
| BMW | US | 10 | 3.36 s | 20 / 0 / 0 | 0 / 0 / 0 | yes | HTML+digest |
| Nike | US | 10 | 3.33 s | 20 / 0 / 0 | 0 / 0 / 0 | yes | HTML+digest |

Rendered characters per fetch: KFC/US 40,024; KFC/AE 40,718; BMW/US 58,344;
Nike/US 48,836 — all well under the plugin's 120,000-char budget, and all
reported `partial=True` only because the 20-ad default limit truncated the
listing (28+ parsed). Check #1 and #2 share one host-cached fetch (0.01 s), which
is why the second check is 0.01 s rather than another network call.

Raw:

```
== live ==
KFC/US PASS count=10 search=3.56s check1=0.01s (20, 0, 0) check2=0.01s (0, 0, 0) partial=True artifacts=True
  fetch 3.56s chars=40024
  fetch 0.01s chars=40024
  fetch 0.01s chars=40024
KFC/AE PASS count=10 search=2.67s check1=0.02s (20, 0, 0) check2=0.01s (0, 0, 0) partial=True artifacts=True
  fetch 2.67s chars=40718
  …
BMW/US PASS count=10 search=3.36s check1=0.02s (20, 0, 0) check2=0.01s (0, 0, 0) partial=True artifacts=True
  fetch 3.36s chars=58344
  …
Nike/US PASS count=10 search=3.33s check1=0.02s (20, 0, 0) check2=0.01s (0, 0, 0) partial=True artifacts=True
  fetch 3.33s chars=48836
  …
live status: PASS
RESULT: PASS (0 failing section(s))
```

Notes from building the live path (harness environment, not product defects):

- Running the bridge under the plugin's `.venv` cannot fetch: that venv has no
  web dependencies, so the configured `firecrawl` backend fails and the keyless
  rescue returns a non-library page (5,175 chars, no card markers) or errors.
  Three live attempts were reported **BLOCKED** for that reason before the
  bridge was switched to `hermes --print-runtime-command`. They are recorded
  here as harness failures, not product failures.
- No live result in this document comes from those attempts; the table above is
  the single successful live run.

## 4. Concurrency / atomicity — PASS

10 threads × 25 rounds, each round doing `watch_add` → `watch_list` →
`save_snapshot` (shared key) → `load_snapshot`, all against one data dir.

```
threads=10 ops/thread=100 elapsed=97.02ms json_files=2 corrupt=0 exceptions=0
watch entries: expected=10 got=10 lost=0 snapshot_ads=1
```

Every JSON file was re-parsed after the run: **0 corrupt, 0 exceptions**. The
10 distinct adds all landed. Pushed harder out-of-band (16×200 and 24×300
rounds): still 0 exceptions, 0 corrupt files, 0 lost entries. Note this is
empirical: `watch_add` is a read-modify-write without a lock, so the atomic
*file* write guarantees no torn JSON but does not formally guarantee no lost
update under contention. No lost update was observed at these volumes.

## 5. Corruption resilience — PASS

| Injected fault | Observed | Contract |
|---|---|---|
| watchlist = `{not json at all,,,` | `watch_list() → []`, `ad_watch list → []`, `ad_check → results: []` | degrade, never crash |
| add after corrupt watchlist | `watch_add` rewrites a valid list | recovers |
| snapshot = invalid UTF-8 / non-JSON bytes | `load_snapshot → {"ads": {}}` | degrade |
| snapshot = valid JSON but a list | `load_snapshot → {"ads": {}}` | degrade |

No exception escaped any path; no tool returned an error object where the store
contract says "empty".

---

## 6. Flakes and product changes

- **Flakes: none.** 50/50 and 20/20 offline iterations, 3/3 pytest runs, and the
  recorded 4/4 live queries (live was not re-run in this pass).
- **Product bugs found: none.** No production file was changed, so no
  regression test was added.
- Only added files: `scripts/stress_e2e.py` and this document.

Known limits of the harness (deliberate, not findings):

- Offline mode exercises the recorded Nike render only; other markets and real
  markup drift are covered by live mode.
- Concurrency is thread-based in one process, i.e. it stresses the atomic-write
  path, not cross-process scheduling.
- Live mode depends on the host's extract backend and its cache; a cold fetch
  costs ~3–4 s here and later fetches are cache hits.

## Addendum 2026-11-06 (post-review fix, HEAD `a9b75a0`)

Independent review found the advertiser filter ran after the 20-ad keyword slice (brand past position 20 reported `name_not_matched`; Nike lost its 4th ad). Fixed in `42f5438` (advertiser paths fetch the full parse, resolve, then slice) + `a9b75a0` (`name_not_matched` now carries `partial`). Suite is now **84 passed** (was 78 at the run above). Re-run: pytest ×3 = 84/84/84, offline stress 50/50 PASS, validate green, live AE+advertiser flow PASS (KFC/AE: 27 ads resolved at 0.80, settle 0/0/0).

## Addendum 2026-11-06 (free field enrichment, Tasks 1–4)

Field/filter enrichment landed on top of the tree measured above (new per-ad
fields, `active_status`/`media_type` filters, richer diff signature and report
badges). Re-run on the working tree before commit:

- `pytest -q` → **129 passed** (was 84 at the last addendum). 0 failed.
- `scripts/stress_e2e.py` (offline) → **PASS**, 50/50 iterations, 0 failures,
  max 9.8 ms, total 0.46 s; concurrency 10×100 → 0 corrupt, 0 exceptions;
  corruption section PASS.
- `hermes plugins validate .` → **Validation passed** (one informational note
  that `scripts/stress_e2e.py` patches a module attribute in-process; unchanged
  from the earlier run).

Live mode was not re-run in this pass, so the live table above remains the
recorded 4/4 run on the pre-enrichment tree. The new fields do not add a host or
a request; the filters are query-string parameters on the same GET.

## Addendum 2026-11-09 (harness fix, HEAD `440c513`)

Integration review found the committed harness **RED** while the product was fine.
`scripts/stress_e2e.py:328` tampered `expected[0]["id"]`, but that first fixture
ad has `creative_text == ""`. The P2 diff deliberately skips keys empty on either
side (`partial=True`), so `"" -> "tampered copy"` is classed `unknown` and the
changed bucket stays empty — 20/20 iterations failed on the harness's own
assumption, not on product behaviour.

Fix: the tamper target is now the first **delivered** ad whose `creative_text` is
non-empty (`next(... for ad in expected[:delivered] if ad.get("creative_text")`),
mirroring `tests/test_demo.py`; the iteration fails loudly with
`no delivered ad carries creative_text` if no such ad exists. No production file
was touched.

Re-run on the working tree (tree otherwise identical to `440c513`):

- `.venv/bin/python scripts/stress_e2e.py -n 50` → **RESULT: PASS**, 50/50
  iterations, 0 failures, `max_ms=15.0`, `total_s=0.67`; concurrency 10×100 →
  0 corrupt files / 0 exceptions / 0 lost watch entries; corruption section PASS.
- `.venv/bin/python scripts/stress_e2e.py -n 20` → **RESULT: PASS**, 20/20,
  `max_ms=15.2`, `total_s=0.27`.
- `.venv/bin/python -m pytest tests -q` → **470 passed**, 3 consecutive runs.
- `hermes plugins validate .` → **Validation passed** (same informational
  isolation note about `scripts/stress_e2e.py` and `evals/live_eval.py`).

Live mode was not re-run; the 4/4 table above remains the record.
