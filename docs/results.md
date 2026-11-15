# Boomerang test results

Test set run on: (date, time) · Model: (BEDROCK_MODEL_ID) · Commit: (git rev-parse --short HEAD)

20 returns through the station: 10 honest, 10 fraud (2 each: empty box, rock or filler, same-model
swap, different item, new damage). Customers, prices and histories are synthetic demo data.

| Metric | Target | Result |
| --- | --- | --- |
| Frauds caught (YELLOW, RED or REVIEW) | ≥ 8 / 10 | |
| Honest returns flagged (RED or REVIEW) | ≤ 1 / 10 | |
| Wrong instant refunds on fraud | 0 | |
| Time per check, photo → LED | < 20 s | |
| Model cost per check | < $0.01 | |

How to fill it: `python scripts/run_testset.py` prints the first three rows and the median time.
`GET /stats` → `model.avg_cost_usd` gives the cost.

## Per-case results

(paste the case table printed by run_testset.py)

## Changes made to reach the targets

| Change | File | Why | Test added |
| --- | --- | --- | --- |
