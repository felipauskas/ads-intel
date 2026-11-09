# Domino's Pizza × SA — FAIL

- folder: `evals/live-matrix/dominos-pizza-sa`
- advertiser filter: `Domino's Pizza`

## Keyword search (`active_status=active`, limit 20)
- count: None  complete: None  fetched: None  error: parse_failed: render (5173 chars) with no card markers or empty-state text
- page names: —
- seconds: 25.48

## Advertiser search
- count: 7  resolved: {'page_name': "Domino's Pizza", 'score': 0.8}  error: None
- page names: Domino's Pizza
- seconds: 24.27

## Watch checks
- check1: new=7 ended=0 changed=0 partial=True error=None seconds=9.61
- check2: new=0 ended=0 changed=0 partial=True error=None seconds=10.7
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 12  failed: 0

## Failures
- search_error: parse_failed: render (5173 chars) with no card markers or empty-state text
