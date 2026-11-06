# Stress test results — pre-publication gate

Audit date: 2026-11-06 (local +04, UTC+04:00)
Repo: `~/coding-projects/ads-intel`
HEAD: `0c2e6ec74e853efdb0773ea4d5c70ded33601f56` (`chore: local catalog entry pinned (unpublished, rule 5 pending)`)
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
workdir: /var/folders/zf/…/T/ads-intel-stress-ir4sfach
repo:    /Users/felipevleon/coding-projects/ads-intel
python:  3.14.10 (/Users/felipevleon/coding-projects/ads-intel/.venv/bin/python)

iter 001 PASS    10.7ms baseline=20 settle=0/0/0 changed=1
…
iter 050 PASS     8.2ms baseline=20 settle=0/0/0 changed=1

offline summary: iterations=50 failures=0 max_ms=10.7 total_s=0.38
RESULT: PASS (0 failing section(s))
EXIT=0
```

What each iteration asserted (all held 50/50):

| Step | Expectation |
|---|---|
| fixture parse | 28 ads, unique ids |
| `ad_search` | `count == 20` (default limit), dispatched `web_extract` once, URL carries `country=US` and the iteration's unique `q=` |
| baseline `ad_check` | `20 new / 0 ended / 0 changed`, `partial=True` (28 parsed > limit 20), snapshot holds 20 ads |
| settle `ad_check` | `0 / 0 / 0`, snapshot unchanged (no shrink from the partial run) |
| tampered `ad_check` | exactly `0 / 0 / 1`, `changed[0].id` is the tampered id |
| artifacts | HTML + digest exist, both inside the isolated data dir, banner reads `0 new / 0 ended / 1 changed`, digest `new/ended/changed == 0/0/1` and `total == snapshot size` |

Max single-iteration wall time: **10.7 ms**; 50 iterations: **0.38 s** (0.35 s on
the earlier identical run). Each iteration creates 3 artifact files plus a
snapshot, so the cost is dominated by `fsync`.

## 2. Full pytest suite, 5 consecutive runs

```
78 passed in 0.11s
78 passed in 0.10s
78 passed in 0.11s
78 passed in 0.13s
78 passed in 0.10s
```

**5/5 × 78 passed, 0 failed, no flakes, no ordering dependence.**

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
threads=10 ops/thread=100 elapsed=83.51ms json_files=2 corrupt=0 exceptions=0
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

- **Flakes: none.** 50/50 offline iterations, 5/5 pytest runs, 4/4 live queries.
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
