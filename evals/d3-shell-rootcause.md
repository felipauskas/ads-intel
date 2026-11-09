# D3 shell-page root cause (analysis only, no live fetches)

Source: `evals/live-matrix/*` at a52be83 (25 pairs, 210 `web_extract` attempts, 924 s total).

## Verdict

**The extractor snapshots the page before the ad-library results grid hydrates.** The
shell is the ad library's own SPA chrome — nav header, full country picker, "Select ad
category", "Search by keyword or advertiser", `[Log In]`, and the complete page footer —
with the results region empty. There is no consent wall, no rate-limit page, no geo block,
and no login wall in it.

Ranked hypotheses:

1. **Pre-results snapshot / results request still in flight (proven-consistent).**
   `resp_url` shows Meta normalized the request to
   `...&is_targeted_country=false&...&sort_data[mode]=total_impressions&sort_data[direction]=desc`
   — i.e. the page's JS *did* boot and rewrite the URL. Only the results stage is missing.
   Fresh fetches spend 6.5 s (shell) vs 7.8 s (success): the successful ones waited ~1.3 s
   longer, the signature of a results response that arrived before the wait cap.
   Outcome is bimodal (full grid or zero cards, never a partial grid) because the grid
   renders atomically.
2. **Shell is deterministic, not a flaky capture.** 10/10 BK AE shells are exactly 5171
   chars; 13/13 McD AE shells exactly 5169. The 2-char delta equals the delta in the echoed
   query string (`Burger+King` vs `McDonald%27s`). The page is byte-stable between "chrome
   painted" and "results arrive", so any snapshot inside that window yields identical bytes.
3. **A second, earlier snapshot stage exists.** 2069/2074/2075-char shells (BK GB, BK US,
   PH SA) are the same page with the 3030-char country-picker block not yet painted
   (5156 − 3030 = 2126, less the header lines ≈ 2075). So the capture lands at stage 1
   (chrome only) or stage 2 (chrome + country list) and never at stage 3 (results).
4. **Retry budget, not detection, is the binding constraint.** p(success) on a *fresh*
   attempt = 45/132 = **0.34**. With 4 attempts a contested phase should fail (1−p)^4 = 19%
   of the time; observed 18/100 phases all-shell. And attempts are effectively **3**, not 4:
   78 of 100 phase-first attempts were 0.01 s host-cache hits, 52 of them replays of the
   shell cached during the `search` phase. `P(fail | 3 fresh) = 0.29`.

Refuted:
- **Consent wall** — no consent wording anywhere in the 5156-char render.
- **Rate limit / throttle** — failures occur on the *first* fetch after idle (BK GB search
  #1, 8.32 s, shell) and clear later in the same burst; a throttle would return an error or
  a checkpoint page, and `failed` is 0/210 (all HTTP 200 with content).
- **Geo block** — the same market both passes and fails (AE: KFC clean, McD/BK shell;
  US: KFC/Domino's/PH clean, McD/BK shell). The `country` param is honoured: the shell
  renders "United Arab Emirates" and the country list.
- **Host cache poisoning** — `cache_bust` genuinely forces a fresh fetch (5–10 s) and that
  fresh fetch still returns the shell. Cache is keyed on the *requested* URL, so it is not
  the cause, though it does waste one attempt per phase (above).
- **Vendor/edge serving a no-JS variant** — a non-JS retrieval would return in 1–2 s; the
  shell takes 6.5 s median, the same as a success. Every success also proves full client
  rendering is required, so there is no server-rendered variant to fall back to.

## Per-failure table

S = shell response, K = cache hit with full render, O = fresh full render.
`chars` = the shell sizes seen for that pair.

| pair | attempts (S/total) | shell chars | phase pattern | verdict |
|---|---|---|---|---|
| Burger King AE | 10/13 | 5171 | search SSSS; adv SSO; check1 SO; check2 SSSO | search phase lost; recovered later. FAIL |
| Burger King GB | 16/16 | 5219, 2075 | all four phases SSSS | never hydrated once: total loss |
| Burger King US | 13/15 | 5218, 2074 | search SSSS; adv SSSS; check1 SSO; check2 SSSO | search+adv lost; check1's 10 "new" ads are vs an empty baseline |
| Domino's SA | 9/12 | 5173 | search SSSS; adv SSSO; check1 SO; check2 SO | search lost; later renders clipped at 120k |
| McDonald's AE | 13/15 | 5169 | search SSSS; adv SSSO; check1 SSSS; check2 SSO | check1 lost → check2 reports 27 false "new" |
| McDonald's EG | 16/16 | 5154 | all four SSSS | total loss; no baseline at all |
| McDonald's SA | 11/13 | 5161 | search SSO; adv SO; check1 SSSS; check2 SSSS | baseline ok, both checks lost → artifacts_error |
| McDonald's US | 10/12 | 5216 | search SO; adv SO; check1 SSSS; check2 SSSS | both checks lost → artifacts_error |
| Burger King EG | 8/12 | 5156 | recovers in every phase | **not a shell failure**: `name_not_matched` (resolver) |
| Pizza Hut AE | 4/8 | 5167 | recovers in every phase | **not a shell failure**: `currency_missing` — the AE listing holds an OMR creative (`ph-omn-rlimo`) |

## Cost

87 fresh shell fetches × 6.54 s = **569 s, 62% of the 924 s run**. The retry loop is now the
dominant cost of the benchmark, and a shell is not a cheap failure: it burns a full render
wait.

Side effect on data quality: `partial` reflects only the *current* render's clipping. A pair
whose baseline is missing but whose later render is big reports a clean diff — McD AE's
`check2 = (27, 0, 0)` is 27 ads "new" purely because `check1` returned nothing.

Secondary: successes at 120,008–120,486 chars are clipped at `_CHAR_LIMIT = 120_000` (the
host returns head+tail), so `complete=False` and the middle cards are missing. Irrelevant to
the shells (5.1k ≪ 120k) but it makes large-listing diffs churn-prone between two clipped
renders.

## Mitigations, ranked by cost/risk

1. **Count shells as failures in the harness** (5 lines in `evals/live_eval.py`). Today
   `failed: 0 (0%)` because a shell is a 200 with content — the headline number hides the
   real defect rate. No behaviour change, makes regressions visible.
2. **Refuse to diff against a missing baseline.** On `parse_failed` for the baseline fetch,
   mark the run `baseline_missing` and suppress `new`/`ended` instead of computing them
   against `[]`. Kills the 27-false-new class (McD AE) — a correctness bug independent of
   retries, and the cheapest high-value fix.
3. **Never spend attempt 1 on a URL already known to shell** (≈10 lines in
   `sources.fetch_ads_with_meta`): keep a module-level set of canonical URLs that returned a
   shell this process and start those at `cache_bust`. Converts 3 effective attempts into 4:
   P(phase fail) 0.29 → 0.19, at zero extra fetch cost (it reclaims a wasted 0.01 s hit).
4. **Raise the budget to 6 fresh attempts with a wall-clock cap** (~60 s). P(phase fail)
   0.29 → 0.08; adds ~13 s per contested phase, roughly 2–3 min to this run. Biggest single
   lever, pure policy, no new dependencies.
5. **Back off 2–4 s between attempts.** *Speculation*: if Meta's results latency comes in
   bursts, immediate retries sample the same regime. Unknown payoff, pure added latency.
6. **URL-shape variants** (cheap to try in one probe, all *speculative*):
   a. send Meta's own canonical params up front (`is_targeted_country=false`,
      `sort_data[mode]=total_impressions&sort_data[direction]=desc`) so the requested URL
      equals the redirect target — removes one client-side rewrite from the critical path;
   b. on retry only, switch `search_type=keyword_unordered` → `keyword_exact_phrase` to
      change Meta's canonical URL/cache key — only worth it if the shell turns out to be
      edge-cached (not established);
   c. skip `m.facebook.com` / `web.facebook.com` — the failure is not redirect, UA or geo.
7. **Accept the rate.** p = 0.34 per attempt is Meta's, not the plugin's: `web_extract`
   takes only `urls` / `format` / `char_limit`, so the renderer's wait cannot be raised from
   here. Document ~10% pair-level flake and gate CI on transport errors.

## Not settled by this data

Whether the results response is *late* or *never* — from outside they are indistinguishable;
the +1.3 s on successful fetches argues for late. Cutting Meta's SSR path out of the
question entirely needs one instrumented run recording the provider name per attempt, which
`web_extract` does not return today.
