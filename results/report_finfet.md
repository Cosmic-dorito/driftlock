# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **10.0%** (3 pairs) |
| Median error | 0.220 px |
| Mean error | 31.626 px |
| p95 error | 116.490 px |
| Worst-case error | 707.28 px |
| Median error, correctly-located pairs only | 0.207 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 90.0% |
| 4 px | 90.0% |
| 2 px | 86.7% |
| 1 px | 83.3% |
| sub-pixel (0.5 px) | 70.0% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 410.7 ms |
| p95 | 495.8 ms |
| Mean | 424.5 ms |

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
| 10.4..11 | 8 | 0.257 | 0% | 88% |
| 9.04..9.45 | 8 | 0.546 | 12% | 75% |
| 9.45..9.82 | 7 | 0.123 | 0% | 100% |
| 9.82..10.4 | 7 | 0.207 | 29% | 71% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.274..0.776 | 7 | 0.198 | 0% | 100% |
| -1.96..-0.274 | 8 | 0.442 | 12% | 75% |
| 0.776..1.23 | 7 | 0.196 | 29% | 71% |
| 1.23..2 | 8 | 0.154 | 0% | 88% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 24 | 0.210 | 8% | 88% |
| med | 6 | 0.465 | 17% | 67% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 438..551 | 7 | 0.312 | 14% | 86% |
| 551..744 | 7 | 0.164 | 0% | 71% |
| 744..941 | 8 | 0.210 | 12% | 88% |
| 76.4..438 | 8 | 0.195 | 12% | 88% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 316..499 | 7 | 0.353 | 0% | 100% |
| 48..316 | 8 | 0.181 | 12% | 88% |
| 499..668 | 7 | 0.207 | 0% | 86% |
| 668..946 | 8 | 0.739 | 25% | 62% |
