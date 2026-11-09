# McDonald's × EG — FAIL

- folder: `evals/live-matrix/mcdonalds-eg`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5154 chars) with no card markers or empty-state text
- page names: —
- seconds: 25.54

## Advertiser search
- count: None  resolved: None  error: parse_failed: render (5154 chars) with no card markers or empty-state text
- page names: —
- seconds: 19.85

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=17.58
- check2: new=None ended=None changed=None partial=True error=None seconds=20.38
- artifacts: {"error": "parse_failed"} (ok=False)
- artifacts check2: {"error": "parse_failed"} (ok=False)

## Currency spot-check
- expected: EGP/جنيه  found: none  ok: False

## Hydration
- attempts: 16  failed: 0

## Failures
- search_error: parse_failed: render (5154 chars) with no card markers or empty-state text
- advertiser_error: parse_failed: render (5154 chars) with no card markers or empty-state text
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (None, None, None)
- artifacts_error: parse_failed
- artifacts2_error: parse_failed
