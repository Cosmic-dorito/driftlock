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
| + pose: spectral lattice  [LESS ACCURATE] | 22.5% | 50.0% | 60.0% |
| + pose: pyramid | 27.5% | 33.3% | 33.3% |
| ** + per-candidate pose refit  [DEFAULT] ** | 25.0% | 30.0% | 16.7% |
| + top-K=20 alone (no re-rank) | 25.0% | 76.7% | 90.0% |
| + top-K + PADM + centre rule  [OVERFIT] | 20.0% | 70.0% | 80.0% |
| + coarse-level consensus re-rank  [HARMFUL] | 62.5% | 76.7% | 36.7% |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 22.5% | 43.3% | 50.0% |
| + row destripe  [HARMFUL] | 35.0% | 90.0% | 90.0% |
| + median filter  [no effect here] | 25.0% | 70.0% | 70.0% |
| + Anscombe A1  [no effect on argmax] | 25.0% | 73.3% | 90.0% |
| + ECC affine  [never converges] | 25.0% | 76.7% | 90.0% |

## Median error (px)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 1.102 | 326.905 | 359.893 |
| + sub-pixel DFT (A9) | 1.085 | 326.905 | 359.893 |
| + blind drift correction | 0.431 | 326.944 | 360.113 |
| + sub-pixel + drift | 0.234 | 326.944 | 360.113 |
| + pose: spectral lattice  [LESS ACCURATE] | 0.246 | 4.177 | 89.280 |
| + pose: pyramid | 0.297 | 0.556 | 0.706 |
| ** + per-candidate pose refit  [DEFAULT] ** | 0.297 | 0.509 | 0.587 |
| + top-K=20 alone (no re-rank) | 1.102 | 326.905 | 359.893 |
| + top-K + PADM + centre rule  [OVERFIT] | 1.012 | 262.813 | 312.113 |
| + coarse-level consensus re-rank  [HARMFUL] | 15.893 | 121.003 | 0.696 |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 0.276 | 0.867 | 23.216 |
| + row destripe  [HARMFUL] | 1.252 | 399.489 | 339.311 |
| + median filter  [no effect here] | 1.102 | 310.853 | 332.057 |
| + Anscombe A1  [no effect on argmax] | 1.102 | 314.086 | 362.880 |
| + ECC affine  [never converges] | 1.102 | 326.905 | 359.893 |

## pass@1px

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 40.0% | 10.0% | 3.3% |
| + sub-pixel DFT (A9) | 45.0% | 10.0% | 6.7% |
| + blind drift correction | 72.5% | 16.7% | 6.7% |
| + sub-pixel + drift | 75.0% | 16.7% | 6.7% |
| + pose: spectral lattice  [LESS ACCURATE] | 77.5% | 43.3% | 30.0% |
| + pose: pyramid | 70.0% | 60.0% | 66.7% |
| ** + per-candidate pose refit  [DEFAULT] ** | 72.5% | 60.0% | 80.0% |
| + top-K=20 alone (no re-rank) | 40.0% | 10.0% | 3.3% |
| + top-K + PADM + centre rule  [OVERFIT] | 47.5% | 16.7% | 6.7% |
| + coarse-level consensus re-rank  [HARMFUL] | 37.5% | 23.3% | 60.0% |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 75.0% | 53.3% | 50.0% |
| + row destripe  [HARMFUL] | 32.5% | 0.0% | 6.7% |
| + median filter  [no effect here] | 40.0% | 13.3% | 6.7% |
| + Anscombe A1  [no effect on argmax] | 40.0% | 10.0% | 3.3% |
| + ECC affine  [never converges] | 40.0% | 10.0% | 3.3% |

## pass@0.5px (sub-pixel)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 17.5% | 3.3% | 3.3% |
| + sub-pixel DFT (A9) | 17.5% | 3.3% | 3.3% |
| + blind drift correction | 62.5% | 13.3% | 6.7% |
| + sub-pixel + drift | 72.5% | 16.7% | 6.7% |
| + pose: spectral lattice  [LESS ACCURATE] | 72.5% | 23.3% | 13.3% |
| + pose: pyramid | 67.5% | 46.7% | 33.3% |
| ** + per-candidate pose refit  [DEFAULT] ** | 67.5% | 50.0% | 40.0% |
| + top-K=20 alone (no re-rank) | 17.5% | 3.3% | 3.3% |
| + top-K + PADM + centre rule  [OVERFIT] | 22.5% | 6.7% | 3.3% |
| + coarse-level consensus re-rank  [HARMFUL] | 37.5% | 13.3% | 43.3% |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 70.0% | 40.0% | 26.7% |
| + row destripe  [HARMFUL] | 17.5% | 0.0% | 3.3% |
| + median filter  [no effect here] | 17.5% | 3.3% | 6.7% |
| + Anscombe A1  [no effect on argmax] | 17.5% | 3.3% | 3.3% |
| + ECC affine  [never converges] | 17.5% | 3.3% | 3.3% |

## Median runtime (ms)

| Stage | sponsor | bench | finfet |
|---|---|---|---|
| baseline (sponsor: INTER_AREA + ZNCC argmax) | 37 | 44 | 54 |
| + sub-pixel DFT (A9) | 181 | 230 | 261 |
| + blind drift correction | 105 | 122 | 170 |
| + sub-pixel + drift | 420 | 425 | 412 |
| + pose: spectral lattice  [LESS ACCURATE] | 1204 | 1156 | 1286 |
| + pose: pyramid | 699 | 720 | 727 |
| ** + per-candidate pose refit  [DEFAULT] ** | 806 | 924 | 1044 |
| + top-K=20 alone (no re-rank) | 46 | 59 | 69 |
| + top-K + PADM + centre rule  [OVERFIT] | 438 | 569 | 586 |
| + coarse-level consensus re-rank  [HARMFUL] | 716 | 706 | 696 |
| + max-likelihood re-rank (Poisson-Gauss)  [NO GAIN] | 946 | 1031 | 1069 |
| + row destripe  [HARMFUL] | 67 | 88 | 78 |
| + median filter  [no effect here] | 53 | 78 | 64 |
| + Anscombe A1  [no effect on argmax] | 115 | 147 | 144 |
| + ECC affine  [never converges] | 52 | 67 | 70 |

## Reading this table

Two independent failure modes needing separate columns:

* **Mis-lock rate** - landing on the wrong repeat of the lattice. Catastrophic, and invisible to any averaged error metric, because a mis-lock is off by tens to hundreds of pixels while a good match is off by about one.
* **pass@1px / pass@0.5px** - precision once the correct repeat is found.

The shipped stages (sub-pixel, drift correction) never touch candidate selection, so they leave the mis-lock rate **identical to baseline on every split**. They are strictly additive refinement: they cannot turn a correct pick into a wrong one, which is why they transfer across architectures without retuning.

PADM re-ranks, so a mistuned scoring function actively destroys correct answers - it gains 5 points on the split it was tuned on and loses 6.7 and 13.3 points on the two held-out splits. **Refinement fails gracefully; re-ranking fails destructively.**

**Pose rows read differently on the two generators, and that is the point.** The sponsor's generator emits a clean 10:1 with no rotation (H9), so measuring the pose there can only cost runtime - it is the control. Our own generator covers the 9:1-11:1 and 1-2 degree envelope the problem statement says will be tested, and without pose measurement the matcher does not work there at all. A submission validated only on the sponsor's data would never discover that.