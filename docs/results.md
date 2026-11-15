# Boomerang test results

Final build tested 15 Nov 2026, 12:43–1:09 AM (Phoenix time) · Model: Amazon Nova Lite on Bedrock
(`us.amazon.nova-lite-v1:0`) · Code: commit `0f17ac3` on `wp3-endpoints`, merged to `main`

Every return was a real ship-out followed by a real return at the counter station (laptop webcam,
S3, MongoDB Atlas, Bedrock). Customers, prices and return histories are synthetic demo data.

## Final build: 17 labelled returns

| Metric | Target | Result |
| --- | --- | --- |
| Frauds caught (YELLOW, RED or REVIEW) | ≥ 8 / 10 | **8 / 8** (7 RED, 1 YELLOW) |
| Honest returns flagged (RED or REVIEW) | ≤ 1 / 10 | **1 / 9** |
| Wrong instant refunds on fraud | 0 | **0** |
| Time per check, photo → decision | < 20 s | about 6–12 s at the station; model step median 1.75 s |
| Model cost per check | < $0.01 | under $0.001 (measured average $0.0004 across all 59 model calls tonight) |

Fraud types tested, with what caught them:

| Fraud | Cases | Result | Caught by |
| --- | --- | --- | --- |
| Empty box | 1 | RED | weight (230 g → 40 g) and the object checks |
| Box with filler | 1 | RED | weight (31 g → 900 g) and the object checks |
| Tag swap (different tag on a look-alike) | 2 | RED | serial mismatch |
| Wrong object, correct tag and weight | 4 | 3 RED, 1 YELLOW | the two unbiased object checks |

Honest returns: 6 GREEN, 2 YELLOW, 1 REVIEW.
- The REVIEW was the local OpenCV photo comparison disagreeing (mouse); the retake went GREEN.
- Both YELLOWs were the mousepad: the object checks thought it looked different. Held for inspection,
  not refused.

"New damage" was planned but not tested: we had no items we could damage.

## How we got here: four measured rounds

Each round ran on a different version of the code, so the rounds are not added together.

| Round | Change | Honest | Flagged | Fraud | Caught | Instant refund on fraud |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | First full build | 12 | 3 | 12 | 7 | 5 |
| 2 | Tight weight tolerance, ship-out photo as reference, near-miss serials | 4 | 0 | 3 | 2 | 1 |
| 3 | Different-item rule | 10 | 1 | 7 | 4 | 3 |
| 4 | Unbiased object checks (final) | 9 | 1 | 8 | 8 | 0 |

(Round 4 = the 17 final-build returns above: a 5-case check, then the final run.)

## Changes made to reach the targets

| Change | File | Why (what the test set showed) | Test added |
| --- | --- | --- | --- |
| Weight tolerance 150 g / 15% → 10 g / 8%; any weight mismatch is never instant | `stages/risk.py`, `stages/policy.py` | A phone missing a third of its weight (340 g → 230 g) was refunded instantly; honest returns varied by ≤ 3 g | `test_phone_missing_a_third_of_its_weight_is_not_instant` |
| New damage is never instant | `stages/policy.py` | The risk score alone let visible damage through as GREEN | `test_new_damage_is_never_instant` |
| A 2-character serial miss = "can't tell" (YELLOW), not a swap | `stages/serial.py`, `main.py` | All 3 flagged honest returns were 2-character misreads of handwritten tags; real swaps were 5+ characters off | `test_honest_two_character_misreads_are_yellow_not_review` |
| Ship-out photo sent as a reference; model writes what it sees before deciding | `stages/vision.py` | The model said "same item" while its own notes said "Blue umbrella" | `test_model_gets_the_shipout_photo_as_reference` |
| Confident "different object" = RED | `stages/policy.py` | A correct 80%-confident "not the headphones" missed the old "> 80%" line | `test_model_says_different_object_at_80_percent_is_red` |
| Two unbiased object checks (blind description; side-by-side with the ship-out photo); both "different" = RED, one = YELLOW | `stages/vision.py`, `main.py` | With the product name in the prompt, the model described the expected item ("Power Bank") while an umbrella was held up | `test_both_object_checks_say_different_is_red` and 4 more |

## Known limits

- Small sample: 17 returns on the final build. These are measured results, not production accuracy.
- Weights were typed at the station (no scale in the photos), so scale reading was not tested.
- Store tags were handwritten; the model misreads some characters, which the near-miss rule absorbs.
- A different unit photographed with the original's tag and at the same weight cannot be told apart
  from photos alone; a real swap would carry a different tag or none.
