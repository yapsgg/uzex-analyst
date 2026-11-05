Each run found problems that shaped the next version. The question set and the checks also got stricter over time, so the scores aren't directly comparable.

| Run | Model | Questions run | Passed | What it showed, and what changed |
| --- | --- | --- | --- | --- |
| 1 | DeepSeek V4.1 Flash | 72 | 70 | Both failures were grading problems. Stopping to ask which company was meant is now a valid outcome |
| 2 | DeepSeek V4.1 Flash | 216 (72 × 3) | 213 | Gross turnover reported as valid deals, and replies in the wrong language. Added language checks |
| 3 | DeepSeek V4.1 Flash | 216 (72 × 3) | 209 | Unfiltered totals described as valid deals. `v_deals` now holds only deals that took place |
| 4 | DeepSeek V4.1 Flash | 216 (72 × 3) | 215 | Raw tool markup leaked into a reply, for the second time across runs |
| 5 | DeepSeek V4 Pro `0813` | 216 (72 × 3) | 215 | The one failure was an ambiguous question, since reworded. Pro became the default model |
| 6 | DeepSeek V4 Pro `0813` | 237 (79 × 3) | 154 of 159 valid | 78 requests hit an OpenRouter credit limit and don't count. Found a miscopied amount and a made-up figure |
| 7 | DeepSeek V4 Pro `0813` | 79 | 74 | Wrong year comparison and wrong totals from mental arithmetic. `run_sql` now returns totals and warns about partial years |
| 8 | DeepSeek V4 Pro `0813` | 17 riskiest | 16 | The failure was a false alarm from the number check, since fixed |
| 9 | DeepSeek V4 Pro `0813` | 79, on the live app | 78 | This report |
