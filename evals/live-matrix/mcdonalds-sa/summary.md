# McDonald's × SA — FAIL

- folder: `evals/live-matrix/mcdonalds-sa`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5161 chars) with no card markers or empty-state text
- page names: —
- seconds: 21.73

## Advertiser search
- count: 2  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 19.65

## Watch checks
- check1: new=2 ended=0 changed=0 partial=False error=None seconds=11.63
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=11.8
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 14  failed: 0

## Failures
- search_error: parse_failed: render (5161 chars) with no card markers or empty-state text
