# Pizza Hut × AE — FAIL

- folder: `evals/live-matrix/pizza-hut-ae`
- advertiser filter: `Pizza Hut`

## Keyword search (`active_status=active`, limit 20)
- count: 13  complete: True  fetched: 13  error: None
- page names: Al Nahda Gift Center, Pizza Hut
- seconds: 7.84

## Advertiser search
- count: 10  resolved: {'page_name': 'Pizza Hut', 'score': 0.8}  error: None
- page names: Pizza Hut
- seconds: 0.01

## Watch checks
- check1: new=10 ended=0 changed=0 partial=False error=None seconds=0.01
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=0.01
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: none  ok: False

## Hydration
- attempts: 4  failed: 0

## Failures
- currency_missing: AED absent from AE ad text
