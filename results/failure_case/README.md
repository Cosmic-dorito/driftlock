# Failure case — worst pair on this split

Pair `13` from `data/bench/manifest.csv`. Every number below is computed by `scripts/make_failure_case.py`.

![failure](failure_13.png)

Green is the prediction, red the truth, orange the runners-up with their scores.

## What happened

| Quantity | Value |
|---|---|
| Euclidean error | **628.24 px** |
| Predicted centre | (948.48, 342.50) |
| True centre | (765.61, 943.53) |
| Winning ZNCC | 0.8595 |
| Magnification / rotation of this pair | 9.909 / +1.14° |
| Ambiguity level (from the generator) | med |

## Root cause: candidate RANKING

The true location **was** among the candidates, at rank **2** with ZNCC 0.8582. It lost to a lattice-equivalent position by a margin of **0.0013** (0.15% of the winning score), while sitting 701.8 px away from it.

This is the failure mode the problem statement is really about, and the numbers state it precisely: the correct answer is available and the evidence separating it from an impostor is far smaller than the noise on the score. Verified independently as H7/H8 — the aperiodic fingerprint exists (impostor margin median 0.057) but on the real correlation surface the winner-versus-rival margin is a median of 0.016.

## Why this is hard, in one sentence

The array is periodic by design, so a wrong repeat is a *structurally valid* match — it is not a blurry or partial match that a better similarity measure would reject, it is a different cell that genuinely looks the same to within the line-placement noise.

## What would fix it

Ranking, not generation. Candidate recall measured at K=20 is 92.5%, so a perfect re-ranker would cut the mis-lock rate to ~7.5%. Two attempts are recorded as measured negatives rather than quietly dropped: PADM residual re-scoring (overfit — ADR-0012) and coarse-level consensus (harmful — it assumed downsampling reveals landmarks, but the reference's 1000 nm footprint is smaller than a 2600 nm mat, so there is no landmark to reveal at any resolution).