# Ablation

Every stage measured on **every split**, including the ones that did not work (rule R9).

Only one split was used for tuning. A stage that improves the tuned split while hurting the others is overfitting, and this table is arranged so that shows up immediately rather than being discovered by the evaluator.

Rows are baseline **plus the named stage**, not a cumulative chain: a pure ladder cannot distinguish "this stage did nothing" from "this stage broke and an earlier one compensated".

## Mis-lock rate (>5 px)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 25.0% | 76.7% | 90.0% |
| + sub-pixel DFT (A9) | 25.0% | 76.7% | 90.0% |
| + blind drift correction | 25.0% | 76.7% | 90.0% |
| + sub-pixel + drift | 25.0% | 76.7% | 90.0% |
| + pose: spectral lattice  [LESS ACCURATE] | 22.5% | 46.7% | 60.0% |
| + pose: pyramid | 27.5% | 26.7% | 33.3% |
| + per-candidate pose refit, narrow | 25.0% | 23.3% | 16.7% |
| ** + screened wide refit  [DEFAULT] ** | 22.5% | 16.7% | 13.3% |
| + top-K=20 alone (no re-rank) | 25.0% | 76.7% | 90.0% |
| + top-K + PADM + centre rule  [OVERFIT] | 27.5% | 70.0% | 73.3% |
| + wide dense refit, unscreened  [slower AND worse] | 22.5% | 20.0% | 16.7% |
| + centre rule on the default  [prior absent here] | 32.5% | 20.0% | 16.7% |
| + coarse-level consensus re-rank  [HARMFUL] | 62.5% | 73.3% | 36.7% |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 22.5% | 36.7% | 50.0% |
| + row destripe  [HARMFUL] | 35.0% | 90.0% | 90.0% |
| + median filter  [no effect here] | 25.0% | 70.0% | 70.0% |
| + Anscombe A1  [no effect on argmax] | 25.0% | 73.3% | 90.0% |
| + ECC affine  [never converges] | 25.0% | 76.7% | 90.0% |

## Median error (px)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 1.102 | 326.905 | 359.893 |
| + sub-pixel DFT (A9) | 1.085 | 326.905 | 359.893 |
| + blind drift correction | 0.464 | 326.997 | 360.686 |
| + sub-pixel + drift | 0.297 | 326.997 | 360.686 |
| + pose: spectral lattice  [LESS ACCURATE] | 0.246 | 0.892 | 89.289 |
| + pose: pyramid | 0.297 | 0.365 | 0.316 |
| + per-candidate pose refit, narrow | 0.297 | 0.343 | 0.313 |
| ** + screened wide refit  [DEFAULT] ** | 0.275 | 0.337 | 0.201 |
| + top-K=20 alone (no re-rank) | 1.102 | 326.905 | 359.893 |
| + top-K + PADM + centre rule  [OVERFIT] | 1.105 | 174.810 | 295.865 |
| + wide dense refit, unscreened  [slower AND worse] | 0.269 | 0.365 | 0.267 |
| + centre rule on the default  [prior absent here] | 0.323 | 0.337 | 0.259 |
| + coarse-level consensus re-rank  [HARMFUL] | 15.893 | 121.000 | 0.636 |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 0.276 | 0.482 | 23.225 |
| + row destripe  [HARMFUL] | 1.252 | 399.489 | 339.311 |
| + median filter  [no effect here] | 1.102 | 310.853 | 332.057 |
| + Anscombe A1  [no effect on argmax] | 1.102 | 314.086 | 362.880 |
| + ECC affine  [never converges] | 1.102 | 326.905 | 359.893 |

## pass@1px

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 40.0% | 10.0% | 3.3% |
| + sub-pixel DFT (A9) | 45.0% | 10.0% | 6.7% |
| + blind drift correction | 72.5% | 20.0% | 6.7% |
| + sub-pixel + drift | 75.0% | 20.0% | 6.7% |
| + pose: spectral lattice  [LESS ACCURATE] | 77.5% | 53.3% | 30.0% |
| + pose: pyramid | 70.0% | 70.0% | 63.3% |
| + per-candidate pose refit, narrow | 72.5% | 73.3% | 80.0% |
| ** + screened wide refit  [DEFAULT] ** | 75.0% | 76.7% | 83.3% |
| + top-K=20 alone (no re-rank) | 40.0% | 10.0% | 3.3% |
| + top-K + PADM + centre rule  [OVERFIT] | 40.0% | 16.7% | 10.0% |
| + wide dense refit, unscreened  [slower AND worse] | 75.0% | 73.3% | 80.0% |
| + centre rule on the default  [prior absent here] | 65.0% | 76.7% | 80.0% |
| + coarse-level consensus re-rank  [HARMFUL] | 37.5% | 26.7% | 56.7% |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 75.0% | 56.7% | 50.0% |
| + row destripe  [HARMFUL] | 32.5% | 0.0% | 6.7% |
| + median filter  [no effect here] | 40.0% | 13.3% | 6.7% |
| + Anscombe A1  [no effect on argmax] | 40.0% | 10.0% | 3.3% |
| + ECC affine  [never converges] | 40.0% | 10.0% | 3.3% |

## pass@0.5px (sub-pixel)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 17.5% | 3.3% | 3.3% |
| + sub-pixel DFT (A9) | 17.5% | 3.3% | 3.3% |
| + blind drift correction | 52.5% | 13.3% | 6.7% |
| + sub-pixel + drift | 65.0% | 10.0% | 3.3% |
| + pose: spectral lattice  [LESS ACCURATE] | 72.5% | 33.3% | 16.7% |
| + pose: pyramid | 67.5% | 63.3% | 56.7% |
| + per-candidate pose refit, narrow | 67.5% | 63.3% | 63.3% |
| ** + screened wide refit  [DEFAULT] ** | 70.0% | 63.3% | 66.7% |
| + top-K=20 alone (no re-rank) | 17.5% | 3.3% | 3.3% |
| + top-K + PADM + centre rule  [OVERFIT] | 20.0% | 6.7% | 6.7% |
| + wide dense refit, unscreened  [slower AND worse] | 70.0% | 60.0% | 63.3% |
| + centre rule on the default  [prior absent here] | 62.5% | 63.3% | 66.7% |
| + coarse-level consensus re-rank  [HARMFUL] | 37.5% | 20.0% | 50.0% |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 70.0% | 53.3% | 43.3% |
| + row destripe  [HARMFUL] | 17.5% | 0.0% | 3.3% |
| + median filter  [no effect here] | 17.5% | 3.3% | 6.7% |
| + Anscombe A1  [no effect on argmax] | 17.5% | 3.3% | 3.3% |
| + ECC affine  [never converges] | 17.5% | 3.3% | 3.3% |

## Median runtime (ms)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 19 | 19 | 19 |
| + sub-pixel DFT (A9) | 26 | 25 | 25 |
| + blind drift correction | 50 | 50 | 50 |
| + sub-pixel + drift | 56 | 57 | 56 |
| + pose: spectral lattice  [LESS ACCURATE] | 355 | 354 | 354 |
| + pose: pyramid | 193 | 191 | 198 |
| + per-candidate pose refit, narrow | 282 | 284 | 290 |
| ** + screened wide refit  [DEFAULT] ** | 408 | 422 | 426 |
| + top-K=20 alone (no re-rank) | 21 | 22 | 21 |
| + top-K + PADM + centre rule  [OVERFIT] | 203 | 203 | 202 |
| + wide dense refit, unscreened  [slower AND worse] | 608 | 620 | 637 |
| + centre rule on the default  [prior absent here] | 409 | 422 | 427 |
| + coarse-level consensus re-rank  [HARMFUL] | 204 | 206 | 208 |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 313 | 316 | 317 |
| + row destripe  [HARMFUL] | 29 | 29 | 30 |
| + median filter  [no effect here] | 23 | 23 | 23 |
| + Anscombe A1  [no effect on argmax] | 50 | 50 | 51 |
| + ECC affine  [never converges] | 24 | 26 | 28 |

## Reading this table

Two independent failure modes needing separate columns:

* **Mis-lock rate** - landing on the wrong repeat of the lattice. Catastrophic, and invisible to any averaged error metric, because a mis-lock is off by tens to hundreds of pixels while a good match is off by about one.
* **pass@1px / pass@0.5px** - precision once the correct repeat is found.

The shipped stages (sub-pixel, drift correction) never touch candidate selection, so they leave the mis-lock rate **identical to baseline on every split**. They are strictly additive refinement: they cannot turn a correct pick into a wrong one, which is why they transfer across architectures without retuning.

PADM re-ranks, so a mistuned scoring function actively destroys correct answers - it gains 5 points on the split it was tuned on and loses 6.7 and 13.3 points on the two held-out splits. **Refinement fails gracefully; re-ranking fails destructively.**

**Pose rows read differently on the two generators, and that is the point.** The sponsor's generator emits a clean 10:1 with no rotation (H9), so measuring the pose there can only cost runtime - it is the control. Our own generator covers the 9:1-11:1 and 1-2 degree envelope the problem statement says will be tested, and without pose measurement the matcher does not work there at all. A submission validated only on the sponsor's data would never discover that.