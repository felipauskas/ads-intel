# McDonald's × US — FAIL

- folder: `evals/live-matrix/mcdonalds-us`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: dead_render: shell: render (5216 chars) with no card markers or empty-state text
- page names: —
- seconds: 33.7

## Advertiser search
- count: 19  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 12.02

## Watch checks
- check1: new=19 ended=0 changed=0 partial=False error=None seconds=6.17
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=6.61
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None  caveat: —

## Hydration
- attempts: 10  failed: 7  transport: 0  dead render: 7 (shell 7, blocked 0, markup_changed 0)

## Failures
- search_error: parse_failed: dead_render: shell: render (5216 chars) with no card markers or empty-state text
