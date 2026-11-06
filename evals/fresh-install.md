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
