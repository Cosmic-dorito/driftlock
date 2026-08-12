# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **33.3%** (10 pairs) |
| Median error | 0.706 px |
| Mean error | 106.000 px |
| p95 error | 651.929 px |
| Worst-case error | 883.54 px |
| Median error, correctly-located pairs only | 0.449 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 66.7% |
| 4 px | 66.7% |
| 2 px | 66.7% |
| 1 px | 66.7% |
| sub-pixel (0.5 px) | 33.3% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 266.3 ms |
| p95 | 289.2 ms |
| Mean | 276.5 ms |

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
| 10.4..11 | 8 | 0.453 | 25% | 75% |
| 9.04..9.45 | 8 | 0.814 | 25% | 75% |
| 9.45..9.82 | 7 | 0.922 | 43% | 57% |
| 9.82..10.4 | 7 | 0.780 | 43% | 57% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.274..0.776 | 7 | 0.906 | 43% | 57% |
| -1.96..-0.274 | 8 | 13.441 | 50% | 50% |
| 0.776..1.23 | 7 | 0.203 | 43% | 57% |
| 1.23..2 | 8 | 0.577 | 0% | 100% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 24 | 0.585 | 29% | 71% |
| med | 6 | 13.370 | 50% | 50% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 438..551 | 7 | 0.634 | 43% | 57% |
| 551..744 | 7 | 0.780 | 29% | 71% |
| 744..941 | 8 | 0.798 | 25% | 75% |
| 76.4..438 | 8 | 0.624 | 38% | 62% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 316..499 | 7 | 0.721 | 43% | 57% |
| 48..316 | 8 | 0.658 | 38% | 62% |
| 499..668 | 7 | 0.634 | 0% | 100% |
| 668..946 | 8 | 13.433 | 50% | 50% |
