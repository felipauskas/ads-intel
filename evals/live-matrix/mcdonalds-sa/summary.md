# McDonald's × SA — FAIL

- folder: `evals/live-matrix/mcdonalds-sa`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: dead_render: shell: render (5161 chars) with no card markers or empty-state text
- page names: —
- seconds: 34.95

## Advertiser search
- count: 1  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 18.51

## Watch checks
- check1: new=1 ended=0 changed=0 partial=False error=None seconds=12.44
- check2: new=None ended=None changed=None partial=True error=None seconds=35.52
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"error": "parse_failed"} (ok=False)

## Currency spot-check
- expected: —  found: none  ok: None  caveat: —

## Hydration
- attempts: 17  failed: 15  transport: 0  dead render: 15 (shell 15, blocked 0, markup_changed 0)

## Failures
- search_error: parse_failed: dead_render: shell: render (5161 chars) with no card markers or empty-state text
- check2_not_settled: (None, None, None)
- artifacts2_error: parse_failed
