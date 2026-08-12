# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **76.7%** (23 pairs) |
| Median error | 326.905 px |
| Mean error | 333.251 px |
| p95 error | 844.466 px |
| Worst-case error | 1028.85 px |
| Median error, correctly-located pairs only | 1.250 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 23.3% |
| 4 px | 23.3% |
| 2 px | 23.3% |
| 1 px | 10.0% |
| sub-pixel (0.5 px) | 3.3% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 32.1 ms |
| p95 | 35.6 ms |
| Mean | 32.4 ms |

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
| 10.2..10.5 | 7 | 130.630 | 71% | 14% |
| 10.5..11 | 8 | 389.334 | 88% | 0% |
| 9.01..9.61 | 8 | 392.297 | 100% | 0% |
| 9.61..10.2 | 7 | 1.571 | 43% | 29% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.0444..0.604 | 7 | 376.651 | 86% | 14% |
| -1.21..-0.0444 | 7 | 340.983 | 57% | 14% |
| -1.99..-1.21 | 8 | 326.905 | 75% | 12% |
| 0.604..1.88 | 8 | 287.127 | 88% | 0% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 21 | 263.891 | 71% | 14% |
| med | 9 | 456.698 | 89% | 0% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 119..258 | 8 | 356.325 | 88% | 0% |
| 258..471 | 7 | 263.891 | 71% | 29% |
| 471..656 | 7 | 130.630 | 71% | 14% |
| 656..944 | 8 | 502.518 | 75% | 0% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 331..507 | 7 | 391.035 | 86% | 14% |
| 507..781 | 7 | 340.983 | 86% | 0% |
| 781..953 | 8 | 220.496 | 62% | 12% |
| 99.8..331 | 8 | 326.905 | 75% | 12% |
