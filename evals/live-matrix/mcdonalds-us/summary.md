# McDonald's × US — FAIL

- folder: `evals/live-matrix/mcdonalds-us`
- advertiser filter: `McDonald's`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: McDonald's, Monopoly GO, Whatnot, Dan Lok, Uber Eats
- seconds: 13.94

## Advertiser search
- count: 19  resolved: {'page_name': "McDonald's", 'score': 0.8}  error: None
- page names: McDonald's
- seconds: 6.31

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=19.19
- check2: new=None ended=None changed=None partial=True error=None seconds=20.71
- artifacts: {"error": "parse_failed"} (ok=False)
- artifacts check2: {"error": "parse_failed"} (ok=False)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 12  failed: 0

## Failures
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (None, None, None)
- artifacts_error: parse_failed
- artifacts2_error: parse_failed
