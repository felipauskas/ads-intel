# Domino's Pizza × SA — FAIL

- folder: `evals/live-matrix/dominos-pizza-sa`
- advertiser filter: `Domino's Pizza`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5173 chars) with no card markers or empty-state text
- page names: —
- seconds: 17.8

## Advertiser search
- count: 7  resolved: {'page_name': "Domino's Pizza", 'score': 0.8}  error: None
- page names: Domino's Pizza
- seconds: 19.66

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=17.54
- check2: new=None ended=None changed=None partial=True error=None seconds=16.77
- artifacts: {"error": "parse_failed"} (ok=False)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 16  failed: 0

## Failures
- search_error: parse_failed: render (5173 chars) with no card markers or empty-state text
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (None, None, None)
- artifacts_missing: html/digest
