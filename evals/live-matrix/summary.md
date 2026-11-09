# QSR live eval — aggregate

- pairs: 25  pass: 15  fail: 10

| Brand | CC | search count | advertiser | check1 (n/e/c) | check2 (n/e/c) | currency | status | reason |
|---|---|---|---|---|---|---|---|---|
| KFC | AE | 20 | resolved: KFC (0.8) | 17/0/0 | 0/0/0 | AED | PASS | — |
| KFC | SA | 20 | resolved: KFC (0.8) | 22/0/0 | 0/0/0 | — | PASS | — |
| KFC | EG | 19 | resolved: KFC (0.8) | 2/0/0 | 0/0/0 | EGP,جنيه | PASS | — |
| KFC | US | 20 | resolved: KFC (0.8) | 7/0/0 | 0/0/0 | — | PASS | — |
| KFC | GB | 19 | resolved: KFC (0.8) | 2/0/0 | 0/0/0 | — | PASS | — |
| McDonald's | AE | None | resolved: McDonald's (0.8) | None/None/None | 27/0/0 | absent | FAIL | search_error: parse_failed: render (5169 chars) with no card markers or empty-state text; check1_no_new_ads: (None, None, None); check2_not_settled: (27, 0, 0); artifacts_error: parse_failed |
| McDonald's | SA | 20 | resolved: McDonald's (0.8) | None/None/None | None/None/None | — | FAIL | check1_no_new_ads: (None, None, None); check2_not_settled: (None, None, None); artifacts_error: parse_failed; artifacts2_error: parse_failed |
| McDonald's | EG | None | parse_failed: render (5154 chars) with no card markers or empty-state text | None/None/None | None/None/None | absent | FAIL | search_error: parse_failed: render (5154 chars) with no card markers or empty-state text; advertiser_error: parse_failed: render (5154 chars) with no card markers or empty-state text; check1_no_new_ads: (None, None, None); check2_not_settled: (None, None, None); artifacts_error: parse_failed; artifacts2_error: parse_failed |
| McDonald's | US | 20 | resolved: McDonald's (0.8) | None/None/None | None/None/None | — | FAIL | check1_no_new_ads: (None, None, None); check2_not_settled: (None, None, None); artifacts_error: parse_failed; artifacts2_error: parse_failed |
| McDonald's | GB | 20 | resolved: McDonald's (0.8) | 12/0/0 | 0/0/0 | — | PASS | — |
| Burger King | AE | None | resolved: Burger King Arabia (0.8) | 2/0/0 | 0/0/0 | absent | FAIL | search_error: parse_failed: render (5171 chars) with no card markers or empty-state text |
| Burger King | SA | 17 | resolved: Burger King Arabia (0.8) | 8/0/0 | 0/0/0 | — | PASS | — |
| Burger King | EG | 20 | name_not_matched | None/None/None | None/None/None | absent | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_error: name_not_matched; artifacts2_error: name_not_matched |
| Burger King | US | None | parse_failed: render (5218 chars) with no card markers or empty-state text | 10/0/0 | 0/0/0 | — | FAIL | search_error: parse_failed: render (5218 chars) with no card markers or empty-state text; advertiser_error: parse_failed: render (5218 chars) with no card markers or empty-state text |
| Burger King | GB | None | parse_failed: render (5219 chars) with no card markers or empty-state text | None/None/None | None/None/None | — | FAIL | search_error: parse_failed: render (5219 chars) with no card markers or empty-state text; advertiser_error: parse_failed: render (5219 chars) with no card markers or empty-state text; check1_no_new_ads: (None, None, None); check2_not_settled: (None, None, None); artifacts_error: parse_failed; artifacts2_error: parse_failed |
| Domino's Pizza | AE | 20 | resolved: Domino's Pizza (0.8) | 2/0/0 | 0/0/0 | AED | PASS | — |
| Domino's Pizza | SA | None | resolved: Domino's Pizza (0.8) | 7/0/0 | 0/0/0 | — | FAIL | search_error: parse_failed: render (5173 chars) with no card markers or empty-state text |
| Domino's Pizza | EG | 20 | resolved: Domino's Pizza (0.8) | 4/0/0 | 0/0/0 | absent | PASS | — |
| Domino's Pizza | US | 20 | resolved: Domino's Pizza (0.8) | 18/0/0 | 0/0/0 | — | PASS | — |
| Domino's Pizza | GB | 19 | resolved: Domino's Pizza (0.8) | 13/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | AE | 13 | resolved: Pizza Hut (0.8) | 10/0/0 | 0/0/0 | absent | FAIL | currency_missing: AED absent from AE ad text |
| Pizza Hut | SA | 15 | resolved: Pizza Hut KSA (0.8) | 4/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | EG | 11 | resolved: Pizza Hut (0.8) | 9/0/0 | 0/0/0 | جنيه | PASS | — |
| Pizza Hut | US | 20 | resolved: Pizza Hut (0.8) | 18/0/0 | 0/0/0 | — | PASS | — |
| Pizza Hut | GB | 20 | resolved: Pizza Hut (0.8) | 19/0/0 | 0/0/0 | — | PASS | — |

- web_extract attempts: 210  failed: 0 (0%)
