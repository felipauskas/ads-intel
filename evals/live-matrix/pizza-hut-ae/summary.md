# Pizza Hut × AE — FAIL

- folder: `evals/live-matrix/pizza-hut-ae`
- advertiser filter: `Pizza Hut`

## Keyword search (`active_status=active`, limit 20)
- count: 13  complete: True  fetched: 13  error: None
- page names: Al Nahda Gift Center, Pizza Hut
- seconds: 12.88

## Advertiser search
- count: 10  resolved: {'page_name': 'Pizza Hut', 'score': 0.8}  error: None
- page names: Pizza Hut
- seconds: 6.49

## Watch checks
- check1: new=10 ended=0 changed=0 partial=False error=None seconds=5.6
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=6.26
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: none  ok: False

## Hydration
- attempts: 8  failed: 0

## Failures
- currency_missing: AED absent from AE ad text
