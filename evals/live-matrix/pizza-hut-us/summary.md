# Pizza Hut × US — FAIL

- folder: `evals/live-matrix/pizza-hut-us`
- advertiser filter: `Pizza Hut`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: Pizza Hut, T-Mobile, Sbmowing, The Blood Pressure Journal
- seconds: 11.27

## Advertiser search
- count: None  resolved: None  error: parse_failed: render (5214 chars) with no card markers or empty-state text
- page names: —
- seconds: 13.97

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=14.51
- check2: new=None ended=None changed=None partial=True error=None seconds=15.59
- artifacts: {"error": "parse_failed"} (ok=False)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 14  failed: 0

## Failures
- advertiser_error: parse_failed: render (5214 chars) with no card markers or empty-state text
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (None, None, None)
- artifacts_missing: html/digest
