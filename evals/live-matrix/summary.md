# QSR live eval — aggregate

- pairs: 25  pass: 17  fail: 8

| Brand | CC | search count | advertiser | check1 (n/e/c) | check2 (n/e/c) | currency | status | reason |
|---|---|---|---|---|---|---|---|---|
| KFC | AE | 20 | resolved: KFC (0.8) | 17/0/0 | 0/0/0 | AED, درهم | PASS | — |
| KFC | SA | 20 | resolved: KFC (0.8) | 22/0/0 | 0/0/0 | — | PASS | — |
| KFC | EG | 19 | resolved: KFC Masr (0.8) | 14/0/0 | 0/0/0 | EGP, جنيه | PASS | — |
| KFC | US | 20 | name_not_matched | None/None/None | None/None/None | — | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_error: name_not_matched; artifacts2_error: name_not_matched |
| KFC | GB | 20 | resolved: KFC (0.8) | 1/0/0 | 0/0/0 | — | PASS | — |
| McDonald's | AE | 20 | resolved: McDonald's (0.8) | None/None/None | 26/0/0 | unknown: no price token in AE ad text | FAIL | check1_no_new_ads: (None, None, None); check2_not_settled: (26, 0, 0); artifacts_error: parse_failed |
| McDonald's | SA | None | resolved: McDonald's (0.8) | 1/0/0 | None/None/None | — | FAIL | search_error: parse_failed: dead_render: shell: render (5161 chars) with no card markers or empty-state text; check2_not_settled: (None, None, None); artifacts2_error: parse_failed |
| McDonald's | EG | None | resolved: McDonald's (0.8) | 13/0/0 | 0/0/0 | جنيه | FAIL | search_error: parse_failed: dead_render: shell: render (5154 chars) with no card markers or empty-state text |
| McDonald's | US | None | resolved: McDonald's (0.8) | 19/0/0 | 0/0/0 | — | FAIL | search_error: parse_failed: dead_render: shell: render (5216 chars) with no card markers or empty-state text |
| McDonald's | GB | None | resolved: McDonald's (0.8) | 13/0/0 | 0/0/0 | — | FAIL | search_error: parse_failed: dead_render: shell: render (5217 chars) with no card markers or empty-state text |
| Burger King | AE | 14 | resolved: Burger King Arabia (0.8) | 2/0/0 | 0/0/0 | AED, درهم | PASS | — |
| Burger King | SA | 17 | resolved: Burger King Arabia (0.8) | 8/0/0 | 0/0/0 | — | PASS | — |
| Burger King | EG | 20 | name_not_matched | None/None/None | None/None/None | absent | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_error: name_not_matched; artifacts2_error: name_not_matched |
| Burger King | US | 20 | resolved: Burger King (0.8) | 9/0/0 | 6/5/0 | — | FAIL | check2_not_settled: (6, 5, 0) |
| Burger King | GB | 20 | resolved: Burger King UK (0.8) | 5/0/0 | 0/0/0 | — | PASS | — |
| Domino's Pizza | AE | 20 | resolved: Domino's Pizza (0.8) | 2/0/0 | 0/0/0 | AED | PASS | — |
| Domino's Pizza | SA | 20 | resolved: Domino's Pizza (0.8) | 7/0/0 | 0/0/0 | — | PASS | — |
| Domino's Pizza | EG | 20 | resolved: Domino's Pizza (0.8) | 4/0/0 | 0/0/0 | absent | PASS | — |
| Domino's Pizza | US | 20 | resolved: Domino's Pizza (0.8) | 18/0/0 | 0/0/0 | — | PASS | — |
| Domino's Pizza | GB | 19 | resolved: Domino's Pizza (0.8) | 13/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | AE | 11 | resolved: Pizza Hut (0.8) | 8/0/0 | 0/0/0 | OMR | PASS | — |
| Pizza Hut | SA | 14 | resolved: Pizza Hut KSA (0.8) | 4/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | EG | 11 | resolved: Pizza Hut (0.8) | 9/0/0 | 0/0/0 | جنيه | PASS | — |
| Pizza Hut | US | 20 | resolved: Pizza Hut (0.8) | 18/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | GB | 20 | resolved: Pizza Hut (0.8) | 20/0/0 | 0/0/0 | — | PASS | — |

- web_extract attempts: 171  failed: 77 (45%) — transport 0, dead render 77 (shell 77, blocked 0, markup_changed 0)

## Dead renders (200 with content, no listing)

- McDonald's AE: 16 / 19 attempts (shell 16, blocked 0, markup_changed 0)
- McDonald's SA: 15 / 17 attempts (shell 15, blocked 0, markup_changed 0)
- McDonald's EG: 14 / 17 attempts (shell 14, blocked 0, markup_changed 0)
- McDonald's US: 7 / 10 attempts (shell 7, blocked 0, markup_changed 0)
- McDonald's GB: 12 / 15 attempts (shell 12, blocked 0, markup_changed 0)
- Burger King AE: 7 / 11 attempts (shell 7, blocked 0, markup_changed 0)
- Burger King US: 1 / 5 attempts (shell 1, blocked 0, markup_changed 0)
- Pizza Hut US: 5 / 9 attempts (shell 5, blocked 0, markup_changed 0)
