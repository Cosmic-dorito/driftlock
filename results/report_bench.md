# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **30.0%** (9 pairs) |
| Median error | 0.509 px |
| Mean error | 88.568 px |
| p95 error | 508.394 px |
| Worst-case error | 893.90 px |
| Median error, correctly-located pairs only | 0.291 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 70.0% |
| 4 px | 70.0% |
| 2 px | 70.0% |
| 1 px | 60.0% |
| sub-pixel (0.5 px) | 50.0% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 334.4 ms |
| p95 | 369.1 ms |
| Mean | 339.7 ms |

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
| 10.2..10.5 | 7 | 1.112 | 29% | 43% |
| 10.5..11 | 8 | 3.124 | 50% | 50% |
| 9.01..9.61 | 8 | 0.194 | 12% | 75% |
| 9.61..10.2 | 7 | 0.389 | 29% | 71% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.0444..0.604 | 7 | 0.099 | 14% | 86% |
| -1.21..-0.0444 | 7 | 0.483 | 29% | 71% |
| -1.99..-1.21 | 8 | 1.116 | 25% | 38% |
| 0.604..1.88 | 8 | 11.905 | 50% | 50% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 21 | 0.331 | 19% | 81% |
| med | 9 | 144.462 | 56% | 11% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 119..258 | 8 | 0.434 | 25% | 62% |
| 258..471 | 7 | 0.438 | 29% | 71% |
| 471..656 | 7 | 0.331 | 14% | 86% |
| 656..944 | 8 | 4.161 | 50% | 25% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 331..507 | 7 | 0.253 | 43% | 57% |
| 507..781 | 7 | 1.112 | 29% | 43% |
| 781..953 | 8 | 0.505 | 25% | 62% |
| 99.8..331 | 8 | 0.365 | 25% | 75% |
