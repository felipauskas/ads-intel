# QSR live eval — aggregate

- pairs: 25  pass: 20  fail: 5

| Brand | CC | search count | advertiser | check1 (n/e/c) | check2 (n/e/c) | currency | status | reason |
|---|---|---|---|---|---|---|---|---|
| KFC | AE | 20 | resolved: KFC (0.8) | 17/0/0 | 0/0/0 | AED | PASS | — |
| KFC | SA | 20 | resolved: KFC (0.8) | 22/0/0 | 0/0/0 | — | PASS | — |
| KFC | EG | 19 | resolved: KFC Masr (0.8) | 14/0/0 | 0/0/0 | EGP,جنيه | PASS | — |
| KFC | US | 20 | resolved: KFC (0.8) | 7/0/0 | 0/0/0 | — | PASS | — |
| KFC | GB | 20 | resolved: KFC (0.8) | 2/0/0 | 0/0/0 | — | PASS | — |
| McDonald's | AE | None | resolved: McDonald's (0.8) | 27/0/0 | 0/0/0 | absent | FAIL | search_error: parse_failed: dead_render: shell: render (5169 chars) with no card markers or empty-state text |
| McDonald's | SA | 20 | resolved: McDonald's (0.8) | 3/0/0 | 0/0/0 | — | PASS | — |
| McDonald's | EG | 20 | resolved: McDonald's (0.8) | 15/0/0 | 0/0/0 | جنيه | PASS | — |
| McDonald's | US | 20 | resolved: McDonald's (0.8) | 19/0/0 | 0/0/0 | — | PASS | — |
| McDonald's | GB | 20 | resolved: McDonald's (0.8) | 12/0/0 | 0/0/0 | — | PASS | — |
| Burger King | AE | 14 | resolved: Burger King Arabia (0.8) | 2/0/0 | 0/0/0 | AED | PASS | — |
| Burger King | SA | 17 | resolved: Burger King Arabia (0.8) | 8/0/0 | 0/0/0 | — | PASS | — |
| Burger King | EG | 20 | name_not_matched | None/None/None | None/None/None | absent | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_error: name_not_matched; artifacts2_error: name_not_matched |
| Burger King | US | 20 | resolved: Burger King (0.8) | 10/0/0 | 0/0/0 | — | PASS | — |
| Burger King | GB | None | resolved: Burger King UK (0.8) | 5/0/0 | 0/0/2 | — | FAIL | search_error: parse_failed: dead_render: shell: render (5219 chars) with no card markers or empty-state text; check2_not_settled: (0, 0, 2) |
| Domino's Pizza | AE | 20 | resolved: Domino's Pizza (0.8) | 2/0/0 | 0/0/0 | AED | PASS | — |
| Domino's Pizza | SA | 20 | resolved: Domino's Pizza (0.8) | None/None/None | 7/0/0 | — | FAIL | check1_no_new_ads: (None, None, None); check2_not_settled: (7, 0, 0); artifacts_error: parse_failed |
| Domino's Pizza | EG | 20 | resolved: Domino's Pizza (0.8) | 4/0/0 | 0/0/0 | absent | PASS | — |
| Domino's Pizza | US | 20 | resolved: Domino's Pizza (0.8) | 18/0/0 | 0/0/0 | — | PASS | — |
| Domino's Pizza | GB | 19 | resolved: Domino's Pizza (0.8) | 13/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | AE | 11 | resolved: Pizza Hut (0.8) | 11/0/0 | 0/0/0 | absent | FAIL | currency_missing: AED absent from AE ad text |
| Pizza Hut | SA | 14 | resolved: Pizza Hut KSA (0.8) | 4/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | EG | 11 | resolved: Pizza Hut (0.8) | 9/0/0 | 0/0/0 | جنيه | PASS | — |
| Pizza Hut | US | 20 | resolved: Pizza Hut (0.8) | 18/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | GB | 20 | resolved: Pizza Hut (0.8) | 20/0/0 | 0/0/0 | — | PASS | — |

- web_extract attempts: 156  failed: 59 (38%) — transport 0, dead render 59 (shell 59, blocked 0, markup_changed 0)

## Dead renders (200 with content, no listing)

- McDonald's AE: 16 / 19 attempts (shell 16, blocked 0, markup_changed 0)
- McDonald's SA: 8 / 12 attempts (shell 8, blocked 0, markup_changed 0)
- McDonald's EG: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- McDonald's US: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- Burger King AE: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- Burger King EG: 4 / 8 attempts (shell 4, blocked 0, markup_changed 0)
- Burger King US: 4 / 8 attempts (shell 4, blocked 0, markup_changed 0)
- Burger King GB: 12 / 15 attempts (shell 12, blocked 0, markup_changed 0)
- Domino's Pizza AE: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- Domino's Pizza SA: 8 / 11 attempts (shell 8, blocked 0, markup_changed 0)
- Pizza Hut AE: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- Pizza Hut SA: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- Pizza Hut GB: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
