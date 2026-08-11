# Evaluation report

Pairs evaluated: **40**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **20.0%** (8 pairs) |
| Median error | 0.975 px |
| Mean error | 30.552 px |
| p95 error | 130.705 px |
| Worst-case error | 628.58 px |
| Median error, correctly-located pairs only | 0.715 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 80.0% |
| 4 px | 80.0% |
| 2 px | 80.0% |
| 1 px | 52.5% |
| sub-pixel (0.5 px) | 20.0% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 218.1 ms |
| p95 | 234.6 ms |
| Mean | 225.7 ms |

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
| 272..378 | 10 | 1.315 | 30% | 30% |
| 378..709 | 10 | 0.765 | 20% | 60% |
| 56.9..272 | 10 | 1.040 | 20% | 50% |
| 709..909 | 10 | 0.721 | 10% | 70% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 124..333 | 10 | 0.426 | 20% | 80% |
| 333..455 | 10 | 0.625 | 30% | 70% |
| 455..687 | 10 | 0.975 | 20% | 60% |
| 687..928 | 10 | 1.237 | 10% | 0% |
