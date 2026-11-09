# Pizza Hut × AE — PASS

- folder: `evals/live-matrix/pizza-hut-ae`
- advertiser filter: `Pizza Hut`

## Keyword search (`active_status=active`, limit 20)
- count: 11  complete: True  fetched: 11  error: None
- page names: Pizza Hut
- seconds: 5.54

## Advertiser search
- count: 8  resolved: {'page_name': 'Pizza Hut', 'score': 0.8}  error: None
- page names: Pizza Hut
- seconds: 0.01

## Watch checks
- check1: new=8 ended=0 changed=0 partial=False error=None seconds=0.01
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=0.01
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: OMR  ok: False  caveat: non_aed: OMR

## Hydration
- attempts: 4  failed: 0  transport: 0  dead render: 0 (shell 0, blocked 0, markup_changed 0)

## Failures
- none
