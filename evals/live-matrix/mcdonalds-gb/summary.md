# McDonald's × GB — FAIL

- folder: `evals/live-matrix/mcdonalds-gb`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: dead_render: shell: render (5217 chars) with no card markers or empty-state text
- page names: —
- seconds: 33.04

## Advertiser search
- count: 13  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 6.97

## Watch checks
- check1: new=13 ended=0 changed=0 partial=False error=None seconds=30.39
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=19.71
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None  caveat: —

## Hydration
- attempts: 15  failed: 12  transport: 0  dead render: 12 (shell 12, blocked 0, markup_changed 0)

## Failures
- search_error: parse_failed: dead_render: shell: render (5217 chars) with no card markers or empty-state text
