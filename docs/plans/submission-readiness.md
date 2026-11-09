# ads-intel — submission readiness plan

Source: independent eval/test review 2026-11-09 (`EVAL-REVIEW-ads-intel.md`)
at commit 6679991. Execution via subagent-driven-development:
fresh implementer (TDD) -> spec-compliance review -> quality review per task.
Never two implementers on the same files concurrently.

## Workstreams

### A1 Eval integrity (lane: evals/live_eval.py, store.py)
D1: check1 artifacts are check2 output. live_eval.py:472 copies after both
checks; report path keyed only by query/country/advertiser (store.py:165).
Fix: version digest paths per check or copy after check1; copy_artifacts
(live_eval.py:286) must assert counts, not existence only.
Gate: offline repro - two ad_check calls give distinct check1/check2 paths;
digest sums match result.json (was 5 vs 192 new ads).

### A2 Resolver identity (lane: resolve.py, tests/test_resolve.py)
D2: resolve.py:133 sorts by score only; _COUNTRY_TOKENS strips qualifiers.
burger-king-eg -> Burger King Malaysia, dominos-pizza-ae -> Domino's Pizza
India, both wrong-market PASS. Fix: prefer exact/market-matching page;
surface ambiguity, let user choose; tests for multi-candidate/cross-market.
Gate: no wrong-market PASS; ambiguous cases do not silently pick.

### B1 Footer stripping (lane: sources.py, tests/test_sources.py, tests/fixtures/library_page.md)
D3: _clean_creative (sources.py:204-225) leaks page/host footers into
creative_text; 31/565 committed ads contain "System status", 8 embed local
paths; cache filename hash causes false "changed" diffs.
Gate: 0/565 contaminated; unchanged listing yields 0 false changed; golden
ad 1046730950862281 asserted.

### B2 Completeness semantics (lane: sources.py, diffing.py, README.md)
"complete" = rendered window only, no pagination (sources.py:789-802).
Relabel, suppress ended/new inference from window shifts, state limit.
Depends on B1.

### C1 Input hardening (lane: tools.py, store.py)
Reject NUL in advertiser (tools.py:240, store.py:182-193); limit:null ->
default (tools.py:145); label ad copy untrusted, cap size.

### C2 Coverage + CI
Cover D2/D3 cases, ad_watch invalid-country (tools.py:233), uncovered branches
(sources.py:240-242,593,620,652; store.py:59-64,116-117,226-231,294-295);
add CI config + README test command. Depends on A2, B1.

### D1 Docs/catalog truth
Fix retry disclosure (README 151/155 vs sources.py:721-735), scan-caution line
(README 26), stale counts; pin final SHA (catalog was 46253a1, 27 behind).
Depends on A1-C2.

### D2 Public repo + clean clone
Create public GitHub repo, push final SHA, verify clean clone + validate.
Depends on D1. Blocked until user confirms repo name/visibility.

### D3 Fresh live matrix
Re-run full 25-pair sweep at final SHA via one-command runner; commit one
raw successful render fixture. Depends on A1, A2, B1, B2.

### Final integration review
Consistency, full suite, stress harness, narrowed demo claim.
