# Evaluation report

Pairs evaluated: **40**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **25.0%** (10 pairs) |
| Median error | 1.102 px |
| Mean error | 15.463 px |
| p95 error | 64.241 px |
| Worst-case error | 271.71 px |
| Median error, correctly-located pairs only | 0.900 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 75.0% |
| 4 px | 75.0% |
| 2 px | 75.0% |
| 1 px | 40.0% |
| sub-pixel (0.5 px) | 17.5% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 64.1 ms |
| p95 | 70.5 ms |
| Mean | 64.6 ms |

## Environment

| Field | Value |
|---|---|
| python version | 3.14.3 |
| platform | Windows 11 (AMD64) |
| processor | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| opencv version | 5.0.0 |
| cv2 threads | 22 |
| timing method | time.perf_counter() around load+localize, per pair, OpenCV using 22 thread(s), no warm-up discarded |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 272..378 | 10 | 1.707 | 40% | 20% |
| 378..709 | 10 | 0.900 | 20% | 60% |
| 56.9..272 | 10 | 1.032 | 20% | 30% |
| 709..909 | 10 | 0.953 | 20% | 50% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 124..333 | 10 | 0.516 | 30% | 70% |
| 333..455 | 10 | 0.955 | 40% | 50% |
| 455..687 | 10 | 1.052 | 30% | 40% |
| 687..928 | 10 | 1.369 | 0% | 0% |
