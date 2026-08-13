# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **13.3%** (4 pairs) |
| Median error | 0.201 px |
| Mean error | 45.735 px |
| p95 error | 344.524 px |
| Worst-case error | 707.27 px |
| Median error, correctly-located pairs only | 0.187 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 86.7% |
| 4 px | 86.7% |
| 2 px | 86.7% |
| 1 px | 83.3% |
| sub-pixel (0.5 px) | 66.7% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 445.4 ms |
| p95 | 505.9 ms |
| Mean | 461.5 ms |

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
| 10.4..11 | 8 | 0.194 | 12% | 88% |
| 9.04..9.45 | 8 | 0.547 | 12% | 75% |
| 9.45..9.82 | 7 | 0.123 | 0% | 100% |
| 9.82..10.4 | 7 | 0.404 | 29% | 71% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.274..0.776 | 7 | 0.404 | 0% | 100% |
| -1.96..-0.274 | 8 | 0.444 | 25% | 75% |
| 0.776..1.23 | 7 | 0.181 | 29% | 71% |
| 1.23..2 | 8 | 0.152 | 0% | 88% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 24 | 0.187 | 8% | 88% |
| med | 6 | 0.679 | 33% | 67% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 438..551 | 7 | 0.324 | 14% | 86% |
| 551..744 | 7 | 0.155 | 14% | 71% |
| 744..941 | 8 | 0.194 | 12% | 88% |
| 76.4..438 | 8 | 0.138 | 12% | 88% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 316..499 | 7 | 0.353 | 0% | 100% |
| 48..316 | 8 | 0.181 | 12% | 88% |
| 499..668 | 7 | 0.194 | 0% | 86% |
| 668..946 | 8 | 0.744 | 38% | 62% |
