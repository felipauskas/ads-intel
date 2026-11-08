# QSR live eval — aggregate

- pairs: 25  pass: 9  fail: 16

| Brand | CC | search count | advertiser | check1 (n/e/c) | check2 (n/e/c) | currency | status | reason |
|---|---|---|---|---|---|---|---|---|
| KFC | AE | 20 | resolved: KFC (0.8) | 17/0/0 | 0/0/0 | AED | PASS | — |
| KFC | SA | 20 | resolved: KFC (0.8) | 22/0/0 | 0/0/0 | — | PASS | — |
| KFC | EG | 19 | resolved: KFC (0.8) | 2/0/0 | 0/0/0 | EGP,جنيه | PASS | — |
| KFC | US | 20 | resolved: KFC (0.8) | 11/0/0 | 0/0/0 | — | PASS | — |
| KFC | GB | 20 | parse_failed: render (5199 chars) with no card markers or empty-state text | 10/0/0 | 0/0/10 | — | FAIL | advertiser_error: parse_failed: render (5199 chars) with no card markers or empty-state text; check2_not_settled: (0, 0, 10) |
| McDonald's | AE | None | parse_failed: render (5169 chars) with no card markers or empty-state text | None/None/None | None/None/None | absent | FAIL | search_error: parse_failed: render (2079 chars) with no card markers or empty-state text; advertiser_error: parse_failed: render (5169 chars) with no card markers or empty-state text; check1_no_new_ads: (None, None, None); check2_not_settled: (None, None, None); artifacts_missing: html/digest |
| McDonald's | SA | None | resolved: McDonald's (0.8) | 2/0/0 | 0/0/0 | — | FAIL | search_error: parse_failed: render (5161 chars) with no card markers or empty-state text |
| McDonald's | EG | 20 | resolved: McDonald's (0.8) | 13/0/0 | 0/0/0 | جنيه | PASS | — |
| McDonald's | US | 20 | resolved: McDonald's (0.8) | 19/0/0 | 0/0/0 | — | PASS | — |
| McDonald's | GB | 20 | resolved: McDonald's (0.8) | 12/0/0 | 0/0/0 | — | PASS | — |
| Burger King | AE | 11 | name_not_matched | None/None/None | None/None/None | AED | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Burger King | SA | 17 | name_not_matched | None/None/None | None/None/None | — | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Burger King | EG | 20 | name_not_matched | None/None/None | None/None/None | absent | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Burger King | US | 20 | resolved: Burger King (0.8) | 10/0/0 | 0/0/0 | — | PASS | — |
| Burger King | GB | 20 | name_not_matched | None/None/None | None/None/None | — | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Domino's Pizza | AE | 20 | name_not_matched | None/None/None | None/None/None | AED | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Domino's Pizza | SA | None | name_not_matched | None/None/None | None/None/None | — | FAIL | search_error: parse_failed: render (5173 chars) with no card markers or empty-state text; check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Domino's Pizza | EG | 20 | name_not_matched | None/None/None | None/None/None | absent | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Domino's Pizza | US | 20 | name_not_matched | None/None/None | None/None/None | — | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Domino's Pizza | GB | 17 | name_not_matched | None/None/None | None/None/None | — | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Pizza Hut | AE | 13 | resolved: Pizza Hut (0.8) | 10/0/0 | 0/0/0 | absent | FAIL | currency_missing: AED absent from AE ad text |
| Pizza Hut | SA | 6 | name_not_matched | None/None/None | None/None/None | — | FAIL | check1_error: name_not_matched; check2_error: name_not_matched; artifacts_missing: html/digest |
| Pizza Hut | EG | 10 | resolved: Pizza Hut (0.8) | 9/0/0 | 0/0/0 | جنيه | PASS | — |
| Pizza Hut | US | 20 | parse_failed: render (5214 chars) with no card markers or empty-state text | None/None/None | None/None/None | — | FAIL | advertiser_error: parse_failed: render (5214 chars) with no card markers or empty-state text; check1_no_new_ads: (None, None, None); check2_not_settled: (None, None, None); artifacts_missing: html/digest |
| Pizza Hut | GB | 10 | parse_failed: render (5215 chars) with no card markers or empty-state text | 5/0/0 | None/None/None | — | FAIL | advertiser_error: parse_failed: render (5215 chars) with no card markers or empty-state text; check2_not_settled: (None, None, None) |

- web_extract attempts: 157  failed: 0 (0%)
