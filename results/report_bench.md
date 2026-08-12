# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **33.3%** (10 pairs) |
| Median error | 0.556 px |
| Mean error | 107.448 px |
| p95 error | 632.271 px |
| Worst-case error | 893.90 px |
| Median error, correctly-located pairs only | 0.309 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 66.7% |
| 4 px | 66.7% |
| 2 px | 66.7% |
| 1 px | 60.0% |
| sub-pixel (0.5 px) | 46.7% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 231.2 ms |
| p95 | 253.3 ms |
| Mean | 239.1 ms |

## Environment

| Field | Value |
|---|---|
| python version | 3.14.3 |
| platform | Windows 11 (AMD64) |
| processor | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| opencv version | 5.0.0 |
| timing method | time.perf_counter() around load+localize, per pair, single-threaded |

## Stratified by `scale_ratio`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 10.2..10.5 | 7 | 1.112 | 29% | 43% |
| 10.5..11 | 8 | 3.129 | 50% | 50% |
| 9.01..9.61 | 8 | 0.311 | 25% | 75% |
| 9.61..10.2 | 7 | 0.390 | 29% | 71% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.0444..0.604 | 7 | 0.099 | 14% | 86% |
| -1.21..-0.0444 | 7 | 0.483 | 29% | 71% |
| -1.99..-1.21 | 8 | 1.047 | 25% | 50% |
| 0.604..1.88 | 8 | 62.798 | 62% | 38% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 21 | 0.322 | 19% | 81% |
| med | 9 | 102.305 | 67% | 11% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 119..258 | 8 | 0.436 | 25% | 75% |
| 258..471 | 7 | 0.535 | 43% | 57% |
| 471..656 | 7 | 0.322 | 14% | 86% |
| 656..944 | 8 | 143.965 | 50% | 25% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 331..507 | 7 | 23.290 | 57% | 43% |
| 507..781 | 7 | 0.982 | 29% | 57% |
| 781..953 | 8 | 0.585 | 25% | 62% |
| 99.8..331 | 8 | 0.367 | 25% | 75% |
