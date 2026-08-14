# Evaluation report

Pairs evaluated: **40**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **20.0%** (8 pairs) |
| Median error | 0.251 px |
| Mean error | 7.531 px |
| p95 error | 44.278 px |
| Worst-case error | 95.17 px |
| Median error, correctly-located pairs only | 0.192 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 80.0% |
| 4 px | 80.0% |
| 2 px | 80.0% |
| 1 px | 77.5% |
| sub-pixel (0.5 px) | 72.5% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 374.3 ms |
| p95 | 436.2 ms |
| Mean | 380.3 ms |

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
| 272..378 | 10 | 0.520 | 30% | 60% |
| 378..709 | 10 | 0.218 | 10% | 90% |
| 56.9..272 | 10 | 0.296 | 20% | 80% |
| 709..909 | 10 | 0.192 | 20% | 80% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 124..333 | 10 | 0.192 | 30% | 70% |
| 333..455 | 10 | 0.358 | 30% | 70% |
| 455..687 | 10 | 0.274 | 20% | 70% |
| 687..928 | 10 | 0.244 | 0% | 100% |
