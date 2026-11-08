# Domino's Pizza × SA — FAIL

- folder: `evals/live-matrix/dominos-pizza-sa`
- advertiser filter: `Domino's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5173 chars) with no card markers or empty-state text
- page names: —
- seconds: 23.68

## Advertiser search
- count: None  resolved: None  error: name_not_matched
- page names: —
- seconds: 21.84

## Watch checks
- check1: new=None ended=None changed=None partial=True error=name_not_matched seconds=14.55
- check2: new=None ended=None changed=None partial=True error=name_not_matched seconds=11.09
- artifacts: {"error": "name_not_matched"} (ok=False)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 13  failed: 0

## Failures
- search_error: parse_failed: render (5173 chars) with no card markers or empty-state text
- check1_error: name_not_matched
- check2_error: name_not_matched
- artifacts_missing: html/digest
