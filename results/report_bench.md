# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **20.0%** (6 pairs) |
| Median error | 0.330 px |
| Mean error | 14.315 px |
| p95 error | 86.285 px |
| Worst-case error | 148.57 px |
| Median error, correctly-located pairs only | 0.216 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 80.0% |
| 4 px | 80.0% |
| 2 px | 76.7% |
| 1 px | 76.7% |
| sub-pixel (0.5 px) | 63.3% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 699.8 ms |
| p95 | 815.8 ms |
| Mean | 704.9 ms |

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
| 10.2..10.5 | 7 | 0.842 | 29% | 71% |
| 10.5..11 | 8 | 0.216 | 12% | 88% |
| 9.01..9.61 | 8 | 0.332 | 25% | 62% |
| 9.61..10.2 | 7 | 0.284 | 14% | 86% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.0444..0.604 | 7 | 0.108 | 14% | 86% |
| -1.21..-0.0444 | 7 | 0.188 | 0% | 100% |
| -1.99..-1.21 | 8 | 0.663 | 25% | 62% |
| 0.604..1.88 | 8 | 0.501 | 38% | 62% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 21 | 0.188 | 5% | 95% |
| med | 9 | 40.082 | 56% | 33% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 119..258 | 8 | 0.153 | 0% | 88% |
| 258..471 | 7 | 0.438 | 14% | 86% |
| 471..656 | 7 | 0.180 | 0% | 100% |
| 656..944 | 8 | 23.310 | 62% | 38% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 331..507 | 7 | 0.438 | 43% | 57% |
| 507..781 | 7 | 0.595 | 14% | 71% |
| 781..953 | 8 | 0.343 | 25% | 75% |
| 99.8..331 | 8 | 0.114 | 0% | 100% |
