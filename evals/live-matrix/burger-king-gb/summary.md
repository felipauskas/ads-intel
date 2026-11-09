# Burger King × GB — FAIL

- folder: `evals/live-matrix/burger-king-gb`
- advertiser filter: `Burger King`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: dead_render: shell: render (5219 chars) with no card markers or empty-state text
- page names: —
- seconds: 30.53

## Advertiser search
- count: 5  resolved: {'page_name': 'Burger King UK', 'score': 0.8}  error: None
- page names: Burger King UK
- seconds: 6.87

## Watch checks
- check1: new=5 ended=0 changed=0 partial=True error=None seconds=35.74
- check2: new=0 ended=0 changed=2 partial=True error=None seconds=13.03
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 15  failed: 12  transport: 0  dead render: 12 (shell 12, blocked 0, markup_changed 0)

## Failures
- search_error: parse_failed: dead_render: shell: render (5219 chars) with no card markers or empty-state text
- check2_not_settled: (0, 0, 2)
