# Pizza Hut × GB — FAIL

- folder: `evals/live-matrix/pizza-hut-gb`
- advertiser filter: `Pizza Hut`

## Keyword search (`active_status=active`, limit 20)
- count: 10  complete: False  fetched: 10  error: None
- page names: Read well, Camp de Rêves, The Blood Pressure Journal, Carers Card UK, Pizza Hut, LauraJordan.com
- seconds: 14.17

## Advertiser search
- count: None  resolved: None  error: parse_failed: render (5215 chars) with no card markers or empty-state text
- page names: —
- seconds: 13.98

## Watch checks
- check1: new=5 ended=0 changed=0 partial=True error=None seconds=11.74
- check2: new=None ended=None changed=None partial=True error=None seconds=13.54
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 13  failed: 0

## Failures
- advertiser_error: parse_failed: render (5215 chars) with no card markers or empty-state text
- check2_not_settled: (None, None, None)
