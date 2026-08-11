# Ablation

Every stage measured on **every split**, including the ones that did not work (rule R9).

Only one split was used for tuning. A stage that improves the tuned split while hurting the others is overfitting, and this table is arranged so that shows up immediately rather than being discovered by the evaluator.

Rows are baseline **plus the named stage**, not a cumulative chain: a pure ladder cannot distinguish "this stage did nothing" from "this stage broke and an earlier one compensated".

## Mis-lock rate (>5 px)

| Stage | verify(tuned) | dram(held-out) | finfet(held-out) |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 25.0% | 20.0% | 30.0% |
| + sub-pixel DFT (A9) | 25.0% | 20.0% | 30.0% |
| + blind drift correction | 25.0% | 20.0% | 30.0% |
| ** + sub-pixel + drift  [DEFAULT] ** | 25.0% | 20.0% | 30.0% |
| + top-K=20 alone (no re-rank) | 25.0% | 20.0% | 30.0% |
| + top-K + PADM + centre rule  [OVERFIT] | 20.0% | 26.7% | 43.3% |
| + row destripe  [HARMFUL] | 35.0% | 33.3% | 43.3% |
| + median filter  [no effect here] | 25.0% | 20.0% | 30.0% |
| + Anscombe A1  [no effect on argmax] | 25.0% | 20.0% | 30.0% |
| + ECC affine  [never converges] | 25.0% | 20.0% | 30.0% |

## Median error (px)

| Stage | verify(tuned) | dram(held-out) | finfet(held-out) |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 1.102 | 0.952 | 1.091 |
| + sub-pixel DFT (A9) | 1.085 | 1.032 | 1.161 |
| + blind drift correction | 0.427 | 0.503 | 0.664 |
| ** + sub-pixel + drift  [DEFAULT] ** | 0.238 | 0.301 | 0.422 |
| + top-K=20 alone (no re-rank) | 1.102 | 0.952 | 1.091 |
| + top-K + PADM + centre rule  [OVERFIT] | 1.012 | 1.107 | 1.584 |
| + row destripe  [HARMFUL] | 1.252 | 1.235 | 1.584 |
| + median filter  [no effect here] | 1.102 | 1.025 | 1.091 |
| + Anscombe A1  [no effect on argmax] | 1.102 | 0.862 | 1.091 |
| + ECC affine  [never converges] | 1.102 | 0.952 | 1.091 |

## pass@1px

| Stage | verify(tuned) | dram(held-out) | finfet(held-out) |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 40.0% | 50.0% | 43.3% |
| + sub-pixel DFT (A9) | 45.0% | 46.7% | 40.0% |
| + blind drift correction | 72.5% | 80.0% | 70.0% |
| ** + sub-pixel + drift  [DEFAULT] ** | 75.0% | 80.0% | 70.0% |
| + top-K=20 alone (no re-rank) | 40.0% | 50.0% | 43.3% |
| + top-K + PADM + centre rule  [OVERFIT] | 47.5% | 43.3% | 30.0% |
| + row destripe  [HARMFUL] | 32.5% | 40.0% | 30.0% |
| + median filter  [no effect here] | 40.0% | 46.7% | 43.3% |
| + Anscombe A1  [no effect on argmax] | 40.0% | 53.3% | 43.3% |
| + ECC affine  [never converges] | 40.0% | 50.0% | 43.3% |

## pass@0.5px (sub-pixel)

| Stage | verify(tuned) | dram(held-out) | finfet(held-out) |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 17.5% | 23.3% | 13.3% |
| + sub-pixel DFT (A9) | 17.5% | 20.0% | 16.7% |
| + blind drift correction | 62.5% | 46.7% | 33.3% |
| ** + sub-pixel + drift  [DEFAULT] ** | 72.5% | 66.7% | 60.0% |
| + top-K=20 alone (no re-rank) | 17.5% | 23.3% | 13.3% |
| + top-K + PADM + centre rule  [OVERFIT] | 22.5% | 20.0% | 6.7% |
| + row destripe  [HARMFUL] | 17.5% | 16.7% | 13.3% |
| + median filter  [no effect here] | 17.5% | 23.3% | 13.3% |
| + Anscombe A1  [no effect on argmax] | 17.5% | 26.7% | 13.3% |
| + ECC affine  [never converges] | 17.5% | 23.3% | 13.3% |

## Median runtime (ms)

| Stage | verify(tuned) | dram(held-out) | finfet(held-out) |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 16 | 17 | 17 |
| + sub-pixel DFT (A9) | 19 | 20 | 20 |
| + blind drift correction | 32 | 33 | 34 |
| ** + sub-pixel + drift  [DEFAULT] ** | 35 | 36 | 36 |
| + top-K=20 alone (no re-rank) | 18 | 19 | 19 |
| + top-K + PADM + centre rule  [OVERFIT] | 197 | 201 | 203 |
| + row destripe  [HARMFUL] | 27 | 27 | 28 |
| + median filter  [no effect here] | 20 | 20 | 20 |
| + Anscombe A1  [no effect on argmax] | 48 | 49 | 49 |
| + ECC affine  [never converges] | 19 | 19 | 20 |

## Reading this table

Two independent failure modes needing separate columns:

* **Mis-lock rate** - landing on the wrong repeat of the lattice. Catastrophic, and invisible to any averaged error metric, because a mis-lock is off by tens to hundreds of pixels while a good match is off by about one.
* **pass@1px / pass@0.5px** - precision once the correct repeat is found.

The shipped stages (sub-pixel, drift correction) never touch candidate selection, so they leave the mis-lock rate **identical to baseline on every split**. They are strictly additive refinement: they cannot turn a correct pick into a wrong one, which is why they transfer across architectures without retuning.

PADM re-ranks, so a mistuned scoring function actively destroys correct answers - it gains 5 points on the split it was tuned on and loses 6.7 and 13.3 points on the two held-out splits. **Refinement fails gracefully; re-ranking fails destructively.**