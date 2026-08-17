# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **3.3%** (1 pairs) |
| Median error | 0.214 px |
| Mean error | 29.693 px |
| p95 error | 2.758 px |
| Worst-case error | 878.29 px |
| Median error, correctly-located pairs only | 0.207 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 96.7% |
| 4 px | 96.7% |
| 2 px | 93.3% |
| 1 px | 90.0% |
| sub-pixel (0.5 px) | 76.7% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 880.6 ms |
| p95 | 987.1 ms |
| Mean | 900.9 ms |

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
| 10.4..11 | 8 | 0.224 | 0% | 88% |
| 9.04..9.45 | 8 | 0.334 | 0% | 88% |
| 9.45..9.82 | 7 | 0.123 | 0% | 100% |
| 9.82..10.4 | 7 | 0.207 | 14% | 86% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.274..0.776 | 7 | 0.198 | 0% | 100% |
| -1.96..-0.274 | 8 | 0.288 | 0% | 88% |
| 0.776..1.23 | 7 | 0.196 | 14% | 86% |
| 1.23..2 | 8 | 0.154 | 0% | 88% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 24 | 0.202 | 0% | 96% |
| med | 6 | 0.465 | 17% | 67% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 438..551 | 7 | 0.314 | 0% | 100% |
| 551..744 | 7 | 0.164 | 0% | 71% |
| 744..941 | 8 | 0.214 | 12% | 88% |
| 76.4..438 | 8 | 0.135 | 0% | 100% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 316..499 | 7 | 0.353 | 0% | 100% |
| 48..316 | 8 | 0.181 | 12% | 88% |
| 499..668 | 7 | 0.207 | 0% | 86% |
| 668..946 | 8 | 0.373 | 0% | 88% |
