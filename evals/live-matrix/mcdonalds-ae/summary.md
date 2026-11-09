# McDonald's × AE — FAIL

- folder: `evals/live-matrix/mcdonalds-ae`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: اسلامي نبض حياتي, McDonald's, Dan Lok
- seconds: 30.99

## Advertiser search
- count: 20  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 12.07

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=33.33
- check2: new=26 ended=0 changed=0 partial=False error=None seconds=28.17
- artifacts: {"error": "parse_failed"} (ok=False)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: none  ok: None  caveat: unknown: no price token in AE ad text

## Hydration
- attempts: 19  failed: 16  transport: 0  dead render: 16 (shell 16, blocked 0, markup_changed 0)

## Failures
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (26, 0, 0)
- artifacts_error: parse_failed
