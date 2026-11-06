# EVAL A — fresh install (new user, README only)

- **Date:** 2026-11-06 18:05–18:15 (+04)
- **Repo:** `ads-intel` @ `96c0b3d` (`feat/free-treg-fields`)
- **Environment:** macOS 27.2, Hermes Agent v0.23.0 (2026.9.24), Python 3.14.9
- **Method:** cloned the repo to a scratch directory (`git clone`, no untracked files), then created an empty Hermes profile (`hermes profile create evalfresh --no-alias --no-skills`) and followed only the README, from that checkout. No code edits.
- **Overall verdict: FAIL** — the documented install command is blocked and the README's only documented recovery is wrong (it promises a warning, not a block).

## Step results

| # | README step | Verdict |
| --- | --- | --- |
| 0 | `git clone` checkout | **PASS** |
| 1 | `hermes plugins validate .` | **PASS** (15/15 checks, 1 warning) |
| 2 | `hermes plugins install "file://$PWD"` | **FAIL** — blocked unless `--force` is added |
| 3 | `hermes plugins enable ads-intel` | **PASS** |
| 4 | "Search … ads from Notion in the US, limit 10" | **PASS (mechanical) / FAIL (intent)** |
| 5 | "Watch linear.app … then check … what changed" | **PASS (mechanical)** — noisy results, `partial: true` |
| 6 | "KFC's ads in the UAE, only from KFC's page" | **PASS (mechanical)** — market attribution questionable |

## Details

### 0. Checkout — PASS

Clean clone of `96c0b3d`; tracked files only. No install bootstrap needed (stdlib only, `python_dependencies: []`).

### 1. Validate — PASS

```
✓ manifest … ✓ declared tools … ✓ security scan — caution … Validation passed.
⚠ security scan caution: invisible_unicode (gap-audit.md:49)
◇ Isolation — in-process only: scripts/stress_e2e.py:236 patches tools.store._data_dir
```

15/15 checks pass. Two non-blocking warnings:

- **Invisible unicode:** the only warning validate prints is `docs/plans/gap-audit.md:49` (a U+200B zero-width space inside a copied library URL). It is documentation only.
- **Isolation:** `scripts/stress_e2e.py` pokes `tools.store._data_dir`, so the plugin is classified in-process rather than host-isolated. Not user-facing at runtime.

### 2. Install — FAIL as documented

Running the README command verbatim with no extra flags exits **1**:

```
Decision: BLOCKED — Blocked (community source + caution verdict, 212 findings).
Use --force to override.
```

This contradicts the README sentence: "`file://` installs prompt with an 'insecure source' warning … That warning is expected here." The user gets a **refusal**, not a warning, and the README never mentions `--force`.

Root cause of the 212 findings: the security scan runs over the whole checkout, including test fixtures and docs. `tests/fixtures/library_page.md` contains **209** U+200B characters copied from a live Meta render, plus the one in `docs/plans/gap-audit.md` (212 findings in total after scanner expansion). None are executable code, but together they turn the verdict to `caution`, and a non-catalog source + `caution` is auto-blocked.

With `--force` the install succeeds:

```
Warning: custom (unreviewed) source — not from the Hermes catalog.
Warning: Using insecure/local URL scheme.
Cloning file:///…/fresh-checkout … ✓ Installed
Plugin installed but not enabled.
```

So the plugin is installable, but the documented path is not. Suggested fixes (not applied — read-only eval): add `--force` to the README install block and explain why; or exclude `tests/fixtures/**` and `docs/plans/**` from the install security scan / strip the zero-width characters so the source scans clean. `--force` in the docs is the one-line fix.

### 3. Enable — PASS

```
✓ Plugin ads-intel enabled.
Gateway reloaded plugins — deferred: tools (next session).
```

`plugins list --plain --no-bundled` → `enabled  git  0.2.0  ads-intel`.
`plugins doctor ads-intel` → runtime discovery, manifest, import and registration all OK, 3 tools.
`plugins capabilities ads-intel` → declared capabilities: none (consistent with a zero-key, zero-network-credential plugin).

### 4. Try-it: Notion search — PASS mechanically, FAIL as advertised

The prompt ran and returned `count: 10`, `complete: false`. The tool works. But **zero of the ten ads are from Notion**: results are Shane Mahoney, Coursiv (×5), T-Pain, Career Unlocked, Masterly AI, Angelica Georges. Retrying with `advertiser: "Notion"` returned `name_not_matched` because Notion's page never appears in the keyword listing.

This is the documented keyword-search limitation, but the README's first 60-second example says "ads **from** Notion", which a new user will read as brand-filtered. It gives a bad first impression and is the weakest of the three samples. Recommend changing the sample to a brand that does appear in its own keyword results, or to `advertiser: "KFC"`, and keeping the Notion example only as a keyword-search illustration.

### 5. Try-it: watch + check — PASS mechanically

- `ad_watch add linear.app` → `[{query: "linear.app", country: "US"}]` written to `watchlist.json`.
- First `ad_check` → baseline, **20 new / 0 ended / 0 changed / 0 skipped**, `partial: true`.
- Second `ad_check` → **0/0/0**, `partial: true`, stable.
- Report artifacts written as documented: `reports/cf7558bc8a1822bc.html` (31 KB) and `reports/cf7558bc8a1822bc.digest.json`; snapshot `snapshots/cf7558bc8a1822bc.json`.
- Digest carries `total/new/ended/changed` plus `with_link`, `with_cta`, `with_images`, `with_same_creative`, `with_multiple_versions` — matches the README.

Caveat: the 20 ads are unrelated keyword hits (Ultimea, SM Appliance, Pocket FM…), not Linear. `partial: true` on every run at exactly 20 ads is expected per README but means a brand-new user's first watch reports 20 "new" ads of noise, and endings are suppressed forever on a watch that stays at the limit.

### 6. Try-it: KFC UAE with advertiser — PASS mechanically, questionable data

- Resolution: **PASS** — `KFC` → page `KFC`, score `0.80` (exact, threshold 0.80), no `name_not_matched`.
- Return: 20 ads, `complete: false`, all `page_name: KFC`.
- Data quality: creatives look **US-market**, not UAE — USD prices ($4.99, $10 bucket), `kfc.com` destinations, US holidays ("Finger Lickin' Fourth"), and one ad whose page URL is `facebook.com/kfcpolska` while `page_name` is `KFC`.

The request URL does include `country=AE`, so this is either Meta's public render behaviour or a parser/identity gap, not a malformed request. Still, "KFC's ads in the UAE" does not return verifiably UAE ads; the page-name-vs-page-URL mismatch on the Polska ad also means `advertiser` filtering can select a page whose URL belongs to a different market. Worth an explicit README note and a follow-up investigation; a new user will otherwise trust the country label.

## Other fresh-user observations

- **Python version is undocumented.** The repo's `python3` is 3.9.6; `python3 -m pytest` fails at collection with `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` because `store.py` uses `dict | None`. The plugin runs inside Hermes' Python 3.14, and `136 passed in 0.15s` under the project `.venv` (3.14.10), so runtime is fine — but a fresh contributor following the README has no stated minimum Python and no test instructions. Add "Python ≥ 3.10" and the test command.
- **No published catalog entry** is stated and matches reality; `file://` is the only path, so the install block is the only onboarding path and needs to be correct.
- Reports and snapshots land in `~/.hermes/profiles/<profile>/plugin-data/ads-intel/`, consistent with the Disclosures section.

## Bottom line

The plugin itself installs, enables, validates, registers three tools, and all three tool flows execute end-to-end with live data and no keys. The **onboarding path fails at step 2**: the README says to expect a warning but the installer hard-blocks with 212 findings and requires an undocumented `--force`. Fix that one line (and ideally the Notion sample and the Python version note) and this eval passes.

---

# EVAL A — fresh install, re-run after fixes

- **Date:** 2026-11-06 18:18–18:30 (+04)
- **Repo:** `ads-intel` @ `aa61ac3` (`fix: eval blockers …`, 173 tests)
- **Environment:** macOS 27.2, Hermes Agent v0.23.0 (2026.9.24), Python 3.14.9
- **Method:** identical to the original run — clean `git clone` of the repo into a scratch directory (no untracked files), new empty profile `evalfresh2` (`hermes profile create evalfresh2 --no-alias --no-skills`), README followed verbatim from that checkout. No code edits, no `--force`, no extra flags.
- **Overall verdict: PASS.** The documented install path now completes unblocked; all three try-its run end-to-end. The previous step-2 blocker is gone.

## Step results

| # | README step | Verdict |
| --- | --- | --- |
| 0 | `git clone` checkout | **PASS** |
| 1 | `hermes plugins validate .` | **PASS** — 15/15, security scan `safe`, no warnings |
| 2 | `hermes plugins install "file://$PWD"` | **PASS** — warning only, no `--force`, exit 0 |
| 3 | `hermes plugins enable ads-intel` | **PASS** |
| 4 | "Search … ads mentioning Notion in the US, limit 10" | **PASS** — works, and the README now states the keyword-search limitation up front |
| 5 | "Watch linear.app … then check … what changed" | **PASS (mechanical)** — baseline + stable diff; the agent still substitutes a noisy keyword watch |
| 6 | "KFC's ads in the UAE, only from KFC's own page" | **PASS (mechanical)** — resolves 0.80, only `page_name: KFC`; market-purity caveat now documented |

## Details

### 0–1. Checkout and validate — PASS

Clean clone at `aa61ac3`, tracked files only. Validate exits 0 with all 15 checks green:

```
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
◇ Isolation — in-process only: scripts/stress_e2e.py:236 patches tools.store._data_dir
Validation passed.
```

The 212 invisible-unicode findings from the first run are gone (`tests/fixtures/library_page.md` and `docs/plans/gap-audit.md` cleaned). The only remaining output is the informational `◇ Isolation` note about `scripts/stress_e2e.py`, which is explanatory, not a warning — the README's "expect a clean scan: no errors or warnings" is now accurate.

### 2. Install — PASS as documented

Verbatim install (no `--force`) exits **0**:

```
Warning: custom (unreviewed) source — not from the Hermes catalog.
Warning: Using insecure/local URL scheme.
Cloning file:///…/evalfresh2-checkout … ✓ Installed
Location: /Users/felipevleon/.hermes/profiles/evalfresh2/plugins/ads-intel
Plugin installed but not enabled.
```

This matches the README sentence exactly: a warning, not a block. The prior hard block and the undocumented `--force` are resolved.

### 3. Enable — PASS

```
✓ Plugin ads-intel enabled.
Gateway reloaded plugins — deferred: tools (next session).
```

`plugins list --plain --no-bundled` → `enabled  git  0.2.0  ads-intel`. `plugins doctor ads-intel` → runtime discovery, manifest, import and registration OK, 3 tools. `plugins capabilities ads-intel` → `declared: (none)`.

### 4. Try-it: Notion — PASS (expectation now matches behaviour)

The exact README prompt ran and returned 10 ads. Verified directly against the installed tool: `count: 10`, `complete: false`, `fetched: 10`, page names Shane Mahoney, Coursiv, T-Pain, Career Unlocked, Masterly AI, Angelica Georges — still zero Notion-owned ads, because it is a keyword search. That is no longer a mismatch: the README bullet now says "a **keyword** search: it returns any page whose ads mention Notion, not only Notion's own page" and documents `advertiser` + the expected `name_not_matched`. Mechanical and intent both pass; the sample is honest about what it shows.

### 5. Try-it: watch + check — PASS mechanically, sample still causes improvisation

Asked the documented prompt, the agent searched for Linear, concluded no Linear page is resolvable, and added a keyword watch on `linear` (US) instead of `linear.app`. Result:

- `watchlist.json` → `[{"query": "linear", "country": "US"}]`
- First `ad_check` seeded the baseline: 20 ads, report `reports/53c85fa2ec5d926a.html` (28 KB) + digest.
- Second `ad_check` → **0 new / 0 ended / 0 changed**, `partial: true`, stable.
- Digest fields: `total/new/ended/changed` plus `with_link: 17`, `with_cta: 17`, `with_images: 10`, `with_same_creative: 4`, `with_multiple_versions: 10` — matches the README.

The tool flow is correct and the baseline-then-diff semantics hold. Remaining UX nit (unchanged from the first run, not an install blocker): the sample brand does not resolve, so an agent improvises a noisy keyword watch rather than watching `linear.app`; every run is `partial: true` at the 20-ad render limit. A sample brand that resolves (e.g. KFC) would demonstrate the feature with less explanation.

### 6. Try-it: KFC UAE with advertiser — PASS mechanically, caveat now documented

Direct verification of the installed tool with `query: KFC, country: AE, advertiser: KFC, limit: 100`:

```
count: 27, complete: true, fetched: 27, country: AE,
resolved: {page_name: "KFC", score: 0.8}, page_names: ["KFC"]
```

Resolution and filtering are correct — no `name_not_matched`, no third-party pages. The agent's user-facing answer went further (paged the public library to 90 ads) and again surfaced US-market creatives in the `AE` listing ($4.99/$10 offers, `kfc.com`, "Finger Lickin' Fourth"). Unlike the first run, the README now carries an explicit paragraph saying `country` selects the listing and does not guarantee market-pure creatives. Intent is therefore no longer overpromised; the underlying Meta render behaviour is unchanged and correctly disclosed.

## Delta vs. first run

| Item | First run (`96c0b3d`) | This run (`aa61ac3`) |
| --- | --- | --- |
| Validate security scan | `caution`, 212 invisible-unicode findings | `safe`, no warnings |
| Install without `--force` | **BLOCKED**, exit 1 | **PASS**, exit 0, warning only |
| README `--force` / warning mismatch | Wrong (promised warning, delivered block) | Correct (warning as described) |
| Python 3.10+ requirement | Undocumented | Documented under Requirements |
| Notion sample | Advertised brand filter, returned keyword noise | Labelled keyword search, `name_not_matched` documented |
| KFC market purity | Undisclosed, misleading | Explicit "listing queried, not where it ran" note |
| Overall | **FAIL** | **PASS** |

No new blockers found. The only non-blocking observations are the `linear.app` sample (agent substitutes `linear`) and the permanent `partial: true` at the render limit — both UX/sample-quality issues, not install or tool failures. Nothing was edited in the repo except this eval log.
