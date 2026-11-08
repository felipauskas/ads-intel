# McDonald's × AE — FAIL

- folder: `evals/live-matrix/mcdonalds-ae`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (2079 chars) with no card markers or empty-state text
- page names: —
- seconds: 20.55

## Advertiser search
- count: None  resolved: None  error: parse_failed: render (5169 chars) with no card markers or empty-state text
- page names: —
- seconds: 14.17

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=17.82
- check2: new=None ended=None changed=None partial=True error=None seconds=16.32
- artifacts: {"error": "parse_failed"} (ok=False)

## Currency spot-check
- expected: AED  found: none  ok: False

## Hydration
- attempts: 16  failed: 0

## Failures
- search_error: parse_failed: render (2079 chars) with no card markers or empty-state text
- advertiser_error: parse_failed: render (5169 chars) with no card markers or empty-state text
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (None, None, None)
- artifacts_missing: html/digest
