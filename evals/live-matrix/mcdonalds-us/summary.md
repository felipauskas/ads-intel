# McDonald's × US — PASS

- folder: `evals/live-matrix/mcdonalds-us`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: McDonald's, Monopoly GO, Whatnot, Dan Lok, Uber Eats
- seconds: 11.01

## Advertiser search
- count: 19  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 7.54

## Watch checks
- check1: new=19 ended=0 changed=0 partial=False error=None seconds=6.97
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=7.31
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 5  failed: 1  transport: 0  dead render: 1 (shell 1, blocked 0, markup_changed 0)

## Failures
- none
