# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **30.0%** (9 pairs) |
| Median error | 0.422 px |
| Mean error | 117.372 px |
| p95 error | 604.888 px |
| Worst-case error | 795.00 px |
| Median error, correctly-located pairs only | 0.228 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 70.0% |
| 4 px | 70.0% |
| 2 px | 70.0% |
| 1 px | 70.0% |
| sub-pixel (0.5 px) | 60.0% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 48.1 ms |
| p95 | 70.1 ms |
| Mean | 61.9 ms |

## Environment

| Field | Value |
|---|---|
| python version | 3.14.3 |
| platform | Windows 11 (AMD64) |
| processor | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| opencv version | 5.0.0 |
| timing method | time.perf_counter() around load+localize, per pair, single-threaded |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 101..282 | 8 | 0.331 | 25% | 75% |
| 282..497 | 7 | 88.191 | 57% | 43% |
| 497..764 | 7 | 0.386 | 29% | 71% |
| 764..934 | 8 | 0.407 | 12% | 88% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 283..584 | 7 | 0.167 | 0% | 100% |
| 54.4..283 | 8 | 67.527 | 50% | 50% |
| 584..786 | 7 | 0.665 | 43% | 57% |
| 786..930 | 8 | 0.453 | 25% | 75% |
