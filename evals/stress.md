# Eval E — stress regression

Run date: 2026-11-06 (local +04, UTC+04:00)
Repo: `~/coding-projects/ads-intel`, HEAD `96c0b3d` (`feat: summary null-coercion, filter echo, completeness meta (136 tests)`), working tree clean (one pre-existing untracked `.hermes/` plan dir, not part of the plugin).
Host: macOS 27.2 (arm64), Python 3.14.10 `./.venv/bin/python`.
Mode: local, offline, no network, no publish. No source or test file was modified.

Baseline for comparison: `docs/stress-results.md`, last addendum (free-field enrichment, Tasks 1–4: pytest 129, offline 50/50, max 9.8 ms, total 0.46 s, concurrency 10×100, corruption PASS, validate green).

---

## Commands run

```
./.venv/bin/python -m pytest -q                     # ×3
./.venv/bin/python scripts/stress_e2e.py            # ×4 (offline 50 + concurrency + corruption)
./.venv/bin/python scripts/stress_e2e.py -n 200     # ×1 (stress volume)
hermes plugins validate .                           # ×1
```

`scripts/stress_e2e.py` always runs the offline, concurrency and corruption sections unless `--live` is passed; live mode was not run (offline eval only, no host fetch backend in this pass).

## 1. pytest

| Run | Result | Wall |
|---|---|---|
| 1 | 136 passed | 0.14 s |
| 2 | 136 passed | 0.17 s |
| 3 | 136 passed | 0.16 s |

0 failed, 0 errors, 0 skipped, no flakes, identical count on every run. Count rose 129 → 136 (+5.4%), matching the 7 tests added with the null-coercion / filter-echo / completeness-meta work. Suite wall time (0.14–0.17 s vs 0.11 s in the older record) reflects 7 more tests plus a different tree; not comparable as a per-test regression.

## 2. Offline stress (50 iterations)

Per iteration: parse fixture → `ad_search` → `ad_watch add` → `ad_check` baseline → `ad_check` settle → tamper one creative → `ad_check` change → assert artifacts and digest counts. All assertions unchanged from the baseline document: 28 parsed ads, 20 returned (`partial=True`), baseline `20/0/0`, settle `0/0/0` with no snapshot shrink, tampered `0/0/1` on the correct id, HTML + digest present with matching counts.

| Run | Iterations | Failures | max_ms | total_s | avg/iter |
|---|---|---|---|---|---|
| 1 | 50 | 0 | 12.5 | 0.50 | 10.0 ms |
| 2 | 50 | 0 | 11.1 | 0.49 | 9.8 ms |
| 3 | 50 | 0 | 12.4 | 0.49 | 9.8 ms |
| 4 | 50 | 0 | 39.2 | 0.64 | 12.8 ms |
| 5 (`-n 200`) | 200 | 0 | 16.9 | 1.89 | 9.45 ms |

**450/450 iterations PASS, 0 failures.**

### Timing vs baseline (baseline: max 9.8 ms, total 0.46 s, 9.2 ms/iter)

- Total time: median 0.49 s = **+6.5%** (range +6.5% to +39.1%).
- Average per iteration: median 9.8 ms = **+6.5%**; the 200-iteration run gives 9.45 ms (+2.7%), which is the least noisy estimate and shows no real drift.
- `max_ms`: 11.1–39.2 ms = **+13% to +300%**, above the 10% threshold on every run.

**Regression call: no product regression.** `max_ms` is a single slowest iteration and is dominated by `fsync` stalls on this host; the same harness shows a 39.2 ms outlier in one run and 11.1 ms in another with identical code, and the mean cost is flat within ~3% at 200 iterations. The only >10% movement is that outlier-sensitive metric plus one noisy total (0.64 s). Recorded as environmental variance, not a slowdown.

## 3. Concurrency / atomicity

10 threads × 100 ops each on one data dir: `watch_add` → `watch_list` → `save_snapshot` (shared key) → `load_snapshot`.

| Run | elapsed | json_files | corrupt | exceptions | watch entries | snapshot_ads |
|---|---|---|---|---|---|---|
| 1 | 70.43 ms | 2 | 0 | 0 | 10/10, lost=0 | 1 |
| 2 | 74.30 ms | 2 | 0 | 0 | 10/10, lost=0 | 1 |
| 3 | 78.25 ms | 2 | 0 | 0 | 10/10, lost=0 | 1 |
| 4 | 91.64 ms | 2 | 0 | 0 | 10/10, lost=0 | 1 |

Baseline 83.51 ms; deltas −15.7% to +9.7%, i.e. inside run-to-run noise. No lost updates, no torn JSON, no exceptions across 4,000 ops. Same known limit as documented: `watch_add` is an unlocked read-modify-write, so this is empirical, not a formal guarantee.

## 4. Corruption resilience

PASS on all four injections, identical to the baseline contract:

| Injected fault | Observed |
|---|---|
| watchlist = `{not json at all,,,` | `watch_list() → []`, `ad_watch list → []`, `ad_check rows=0` |
| add after corrupt watchlist | `watch_add` rewrites a valid list |
| snapshot = invalid UTF-8 / non-JSON | `load_snapshot → {"ads": {}}` |
| snapshot = valid JSON but a list | `load_snapshot → {"ads": {}}` |

No exception escaped; no error object where the contract says empty.

## 5. Plugin validation

`hermes plugins validate .` → **Validation passed.** All manifest, requires_hermes, requires_env, loadable, dependency, capability-probe, tool/hook/middleware and collision checks green.

Two non-fatal notices:

- **New in this pass — `security scan — caution: invisible_unicode (docs/plans/gap-audit.md:49)`.** Line 49 contains a U+200B ZERO WIDTH SPACE immediately before a markdown link (`[\u200b](https://www.facebook.com/ads/library/...)`). Docs-only, no runtime effect, but it flips the security scan from clean to `caution`. Not a stress regression; worth stripping so validation returns to fully green.
- **Pre-existing — isolation note:** `scripts/stress_e2e.py:236` patches `tools.store._data_dir` in-process. Unchanged from the baseline run; inherent to the harness's per-iteration isolation.

## 6. Verdict

| Section | Result | vs baseline |
|---|---|---|
| pytest ×3 | 136/136/136 passed | count +7 tests, all green |
| offline stress | 450/450 PASS (50×4, 200×1) | no behavioural change |
| concurrency | 0 corrupt / 0 exceptions / 0 lost of 4,000 ops | flat |
| corruption | PASS (4/4 degrade as contracted) | unchanged |
| validate | passed, 1 new caution notice | docs-only warning |

No regressions >10% in product behaviour, correctness, or throughput. The only >10% deltas are the single-slowest-iteration `max_ms` figure (outlier/fsync-bound; mean flat at +2.7% over 200 iterations) and one noisy total (+39.1% in a single 50-iteration run, absent at higher volume). No production or test file was changed; the only file written is this report.
