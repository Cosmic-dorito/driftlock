# Evaluation report

Pairs evaluated: **40**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **25.0%** (10 pairs) |
| Median error | 0.238 px |
| Mean error | 14.981 px |
| p95 error | 64.335 px |
| Worst-case error | 271.73 px |
| Median error, correctly-located pairs only | 0.162 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 75.0% |
| 4 px | 75.0% |
| 2 px | 75.0% |
| 1 px | 75.0% |
| sub-pixel (0.5 px) | 72.5% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 50.5 ms |
| p95 | 72.5 ms |
| Mean | 59.6 ms |

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
| 272..378 | 10 | 0.535 | 40% | 60% |
| 378..709 | 10 | 0.234 | 20% | 80% |
| 56.9..272 | 10 | 0.285 | 20% | 80% |
| 709..909 | 10 | 0.197 | 20% | 80% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 124..333 | 10 | 0.162 | 30% | 70% |
| 333..455 | 10 | 0.329 | 40% | 60% |
| 455..687 | 10 | 0.281 | 30% | 70% |
| 687..928 | 10 | 0.263 | 0% | 100% |
