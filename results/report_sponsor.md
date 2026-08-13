# Evaluation report

Pairs evaluated: **40**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **22.5%** (9 pairs) |
| Median error | 0.275 px |
| Mean error | 9.438 px |
| p95 error | 57.876 px |
| Worst-case error | 95.17 px |
| Median error, correctly-located pairs only | 0.195 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 77.5% |
| 4 px | 77.5% |
| 2 px | 77.5% |
| 1 px | 75.0% |
| sub-pixel (0.5 px) | 70.0% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 388.1 ms |
| p95 | 451.9 ms |
| Mean | 396.0 ms |

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
| 272..378 | 10 | 0.956 | 40% | 50% |
| 378..709 | 10 | 0.234 | 10% | 90% |
| 56.9..272 | 10 | 0.297 | 20% | 80% |
| 709..909 | 10 | 0.194 | 20% | 80% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 124..333 | 10 | 0.219 | 40% | 60% |
| 333..455 | 10 | 0.347 | 30% | 70% |
| 455..687 | 10 | 0.283 | 20% | 70% |
| 687..928 | 10 | 0.264 | 0% | 100% |
