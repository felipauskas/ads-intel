# Domino's Pizza × SA — FAIL

- folder: `evals/live-matrix/dominos-pizza-sa`
- advertiser filter: `Domino's Pizza`

## Keyword search (`active_status=active`, limit 20)
- count: 20  complete: False  fetched: 20  error: None
- page names: Kırık Mührün Gizemi, Domino's Pizza, Domino's Pizza India, Domino's Pizza España (Oficial), Probashir Astha- প্রবাসীর আস্থা, Empirio, Alibaba.com, Linguza: AI English Tutor, Carrefour Saudi كارفور السعودية, Crazy PizzaSaudi, Your Money Magic, ABOT Surpresa
- seconds: 12.59

## Advertiser search
- count: 7  resolved: {'page_name': "Domino's Pizza", 'score': 0.8}  error: None
- page names: Domino's Pizza
- seconds: 10.06

## Watch checks
- check1: new=None ended=None changed=None partial=True error=None seconds=33.78
- check2: new=7 ended=0 changed=0 partial=True error=None seconds=15.97
- artifacts: {"error": "parse_failed"} (ok=False)
- artifacts check2: {"html": "artifacts/check2/html.html", "digest": "artifacts/check2/digest.json"} (ok=True)

## Currency spot-check
- expected: —  found: none  ok: None

## Hydration
- attempts: 11  failed: 8  transport: 0  dead render: 8 (shell 8, blocked 0, markup_changed 0)

## Failures
- check1_no_new_ads: (None, None, None)
- check2_not_settled: (7, 0, 0)
- artifacts_error: parse_failed
