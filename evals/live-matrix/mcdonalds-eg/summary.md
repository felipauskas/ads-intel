# McDonald's × EG — FAIL

- folder: `evals/live-matrix/mcdonalds-eg`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: dead_render: shell: render (5154 chars) with no card markers or empty-state text
- page names: —
- seconds: 32.25

## Advertiser search
- count: 13  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 23.47

## Watch checks
- check1: new=13 ended=0 changed=0 partial=False error=None seconds=23.5
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=17.95
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: EGP/جنيه  found: جنيه  ok: True  caveat: —

## Hydration
- attempts: 17  failed: 14  transport: 0  dead render: 14 (shell 14, blocked 0, markup_changed 0)

## Failures
- search_error: parse_failed: dead_render: shell: render (5154 chars) with no card markers or empty-state text
