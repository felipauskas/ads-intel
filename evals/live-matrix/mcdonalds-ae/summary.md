# McDonald's × AE — FAIL

- folder: `evals/live-matrix/mcdonalds-ae`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: dead_render: shell: render (5169 chars) with no card markers or empty-state text
- page names: —
- seconds: 27.93

## Advertiser search
- count: 20  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 21.97

## Watch checks
- check1: new=27 ended=0 changed=0 partial=False error=None seconds=17.69
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=34.79
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: none  ok: False

## Hydration
- attempts: 19  failed: 16  transport: 0  dead render: 16 (shell 16, blocked 0, markup_changed 0)

## Failures
- search_error: parse_failed: dead_render: shell: render (5169 chars) with no card markers or empty-state text
