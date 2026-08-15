# Failure case — worst pair on this split

Pair `4` from `data/bench/manifest.csv`. Every number below is computed by `scripts/make_failure_case.py`.

![failure](failure_4.png)

Green is the prediction, red the truth, orange the runners-up with their scores.

## What happened

| Quantity | Value |
|---|---|
| Euclidean error | **148.57 px** |
| Predicted centre | (739.73, 374.98) |
| True centre | (726.43, 522.96) |
| Winning ZNCC | 0.7584 |
| Magnification / rotation of this pair | 9.019 / +1.07° |
| Ambiguity level (from the generator) | med |

## Root cause: candidate GENERATION

The true location is **not present anywhere in the top 120 candidates** — the nearest candidate to ground truth is 63.5 px away. No re-ranking could have recovered this pair, because the right answer was never on the list. That points at the pose or the forward model, not at the scoring.

## Why this is hard, in one sentence

The array is periodic by design, so a wrong repeat is a *structurally valid* match — it is not a blurry or partial match that a better similarity measure would reject, it is a different cell that genuinely looks the same to within the line-placement noise.

## What would fix it

Ranking, not generation. Candidate recall measured at K=20 is 92.5%, so a perfect re-ranker would cut the mis-lock rate to ~7.5%. Two attempts are recorded as measured negatives rather than quietly dropped: PADM residual re-scoring (overfit — ADR-0012) and coarse-level consensus (harmful — it assumed downsampling reveals landmarks, but the reference's 1000 nm footprint is smaller than a 2600 nm mat, so there is no landmark to reveal at any resolution).