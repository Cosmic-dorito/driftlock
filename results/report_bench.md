# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **16.7%** (5 pairs) |
| Median error | 0.337 px |
| Mean error | 53.945 px |
| p95 error | 475.746 px |
| Worst-case error | 511.68 px |
| Median error, correctly-located pairs only | 0.254 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 83.3% |
| 4 px | 83.3% |
| 2 px | 80.0% |
| 1 px | 76.7% |
| sub-pixel (0.5 px) | 63.3% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 393.1 ms |
| p95 | 439.0 ms |
| Mean | 404.5 ms |

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
| 10.2..10.5 | 7 | 0.428 | 14% | 86% |
| 10.5..11 | 8 | 0.428 | 38% | 62% |
| 9.01..9.61 | 8 | 0.163 | 12% | 75% |
| 9.61..10.2 | 7 | 0.254 | 0% | 86% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.0444..0.604 | 7 | 0.096 | 14% | 86% |
| -1.21..-0.0444 | 7 | 0.483 | 14% | 86% |
| -1.99..-1.21 | 8 | 0.335 | 12% | 75% |
| 0.604..1.88 | 8 | 0.477 | 25% | 62% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 21 | 0.192 | 5% | 95% |
| med | 9 | 2.177 | 44% | 33% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 119..258 | 8 | 0.144 | 12% | 75% |
| 258..471 | 7 | 0.254 | 0% | 100% |
| 471..656 | 7 | 0.334 | 14% | 86% |
| 656..944 | 8 | 1.286 | 38% | 50% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 331..507 | 7 | 0.123 | 29% | 71% |
| 507..781 | 7 | 0.564 | 14% | 71% |
| 781..953 | 8 | 0.365 | 12% | 75% |
| 99.8..331 | 8 | 0.144 | 12% | 88% |
