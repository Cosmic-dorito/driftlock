# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **20.0%** (6 pairs) |
| Median error | 0.301 px |
| Mean error | 15.177 px |
| p95 error | 21.225 px |
| Worst-case error | 361.56 px |
| Median error, correctly-located pairs only | 0.252 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 80.0% |
| 4 px | 80.0% |
| 2 px | 80.0% |
| 1 px | 80.0% |
| sub-pixel (0.5 px) | 66.7% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 47.8 ms |
| p95 | 74.0 ms |
| Mean | 61.2 ms |

## Environment

| Field | Value |
|---|---|
| python version | 3.14.3 |
| platform | Windows 11 (AMD64) |
| processor | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| opencv version | 5.0.0 |
| timing method | time.perf_counter() around load+localize, per pair, single-threaded |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 126..506 | 8 | 0.264 | 25% | 75% |
| 506..648 | 7 | 0.266 | 14% | 86% |
| 648..836 | 7 | 0.371 | 43% | 57% |
| 836..950 | 8 | 0.303 | 0% | 100% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 386..571 | 7 | 0.266 | 14% | 86% |
| 55.9..386 | 8 | 0.077 | 0% | 100% |
| 571..834 | 7 | 14.403 | 57% | 43% |
| 834..944 | 8 | 0.300 | 12% | 88% |
