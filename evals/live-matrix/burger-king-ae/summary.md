# Burger King × AE — FAIL

- folder: `evals/live-matrix/burger-king-ae`
- advertiser filter: `Burger King`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5171 chars) with no card markers or empty-state text
- page names: —
- seconds: 16.35

## Advertiser search
- count: 2  resolved: {'page_name': 'Burger King Arabia', 'score': 0.8}  error: None
- page names: Burger King Arabia
- seconds: 14.51

## Watch checks
- check1: new=2 ended=0 changed=0 partial=True error=None seconds=8.44
- check2: new=0 ended=0 changed=0 partial=True error=None seconds=18.79
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: AED  found: none  ok: False

## Hydration
- attempts: 13  failed: 0

## Failures
- search_error: parse_failed: render (5171 chars) with no card markers or empty-state text
