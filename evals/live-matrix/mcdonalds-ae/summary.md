# McDonald's × AE — FAIL

- folder: `evals/live-matrix/mcdonalds-ae`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5169 chars) with no card markers or empty-state text
- page names: —
- seconds: 23.7

## Advertiser search
- count: 20  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 19.96

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=16.92
- check2: new=27 ended=0 changed=0 partial=False error=None seconds=13.83
- artifacts: {"error": "parse_failed"} (ok=False)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: none  ok: False

## Hydration
- attempts: 15  failed: 0

## Failures
- search_error: parse_failed: render (5169 chars) with no card markers or empty-state text
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (27, 0, 0)
- artifacts_error: parse_failed
