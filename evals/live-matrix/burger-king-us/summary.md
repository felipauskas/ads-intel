# Burger King × US — FAIL

- folder: `evals/live-matrix/burger-king-us`
- advertiser filter: `Burger King`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: Burger King, The Krazy Coupon Lady, DoorDash, WNC Dist. Shop, Wolt, Extra News
- seconds: 9.28

## Advertiser search
- count: 10  resolved: {'page_name': 'Burger King', 'score': 0.8}  error: None
- page names: Burger King
- seconds: 8.04

## Watch checks
- check1: new=9 ended=0 changed=0 partial=False error=None seconds=7.29
- check2: new=6 ended=5 changed=0 partial=False error=None seconds=7.01
- artifacts: {"html": "artifacts/html.html", "digest": "artifacts/digest.json"} (ok=True)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None  caveat: —

## Hydration
- attempts: 5  failed: 1  transport: 0  dead render: 1 (shell 1, blocked 0, markup_changed 0)

## Failures
- check2_not_settled: (6, 5, 0)
