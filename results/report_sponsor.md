# Evaluation report

Pairs evaluated: **40**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **5.0%** (2 pairs) |
| Median error | 0.195 px |
| Mean error | 4.732 px |
| p95 error | 5.290 px |
| Worst-case error | 95.17 px |
| Median error, correctly-located pairs only | 0.179 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 95.0% |
| 4 px | 95.0% |
| 2 px | 95.0% |
| 1 px | 92.5% |
| sub-pixel (0.5 px) | 87.5% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 381.6 ms |
| p95 | 445.3 ms |
| Mean | 388.1 ms |

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
| 272..378 | 10 | 0.206 | 10% | 80% |
| 378..709 | 10 | 0.183 | 0% | 100% |
| 56.9..272 | 10 | 0.239 | 0% | 100% |
| 709..909 | 10 | 0.160 | 10% | 90% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 124..333 | 10 | 0.154 | 0% | 100% |
| 333..455 | 10 | 0.181 | 10% | 90% |
| 455..687 | 10 | 0.279 | 10% | 80% |
| 687..928 | 10 | 0.244 | 0% | 100% |
