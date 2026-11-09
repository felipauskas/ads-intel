# McDonald's × EG — PASS

- folder: `evals/live-matrix/mcdonalds-eg`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: McDonald's, Mega Technology, اسلامي نبض حياتي, Franquicia IA, Ligue 1 McDonald's, Monopoly GO, BYT Vacuum Machine
- seconds: 9.88

## Advertiser search
- count: 15  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 6.38

## Watch checks
- check1: new=15 ended=0 changed=0 partial=False error=None seconds=7.64
- check2: new=0 ended=0 changed=0 partial=False error=None seconds=6.53
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: EGP/جنيه  found: جنيه  ok: True

## Hydration
- attempts: 5  failed: 1  transport: 0  dead render: 1 (shell 1, blocked 0, markup_changed 0)

## Failures
- none
