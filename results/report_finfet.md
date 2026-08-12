# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **16.7%** (5 pairs) |
| Median error | 0.587 px |
| Mean error | 65.865 px |
| p95 error | 433.875 px |
| Worst-case error | 707.37 px |
| Median error, correctly-located pairs only | 0.525 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 83.3% |
| 4 px | 83.3% |
| 2 px | 83.3% |
| 1 px | 80.0% |
| sub-pixel (0.5 px) | 40.0% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 332.7 ms |
| p95 | 361.7 ms |
| Mean | 339.4 ms |

## Environment

| Field | Value |
|---|---|
| python version | 3.14.3 |
| platform | Windows 11 (AMD64) |
| processor | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| opencv version | 5.0.0 |
| cv2 threads | 22 |
| timing method | time.perf_counter() around load+localize, per pair, OpenCV using 22 thread(s), no warm-up discarded |

## Stratified by `scale_ratio`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 10.4..11 | 8 | 0.454 | 12% | 88% |
| 9.04..9.45 | 8 | 0.735 | 12% | 88% |
| 9.45..9.82 | 7 | 0.530 | 14% | 71% |
| 9.82..10.4 | 7 | 0.701 | 29% | 71% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.274..0.776 | 7 | 0.404 | 0% | 100% |
| -1.96..-0.274 | 8 | 0.783 | 25% | 62% |
| 0.776..1.23 | 7 | 0.194 | 43% | 57% |
| 1.23..2 | 8 | 0.587 | 0% | 100% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 24 | 0.464 | 12% | 83% |
| med | 6 | 0.756 | 33% | 67% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 438..551 | 7 | 0.525 | 14% | 71% |
| 551..744 | 7 | 0.780 | 29% | 71% |
| 744..941 | 8 | 0.720 | 12% | 88% |
| 76.4..438 | 8 | 0.530 | 12% | 88% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 316..499 | 7 | 0.530 | 0% | 100% |
| 48..316 | 8 | 0.452 | 25% | 75% |
| 499..668 | 7 | 0.644 | 0% | 100% |
| 668..946 | 8 | 1.038 | 38% | 50% |
