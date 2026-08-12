# Evaluation report

Pairs evaluated: **30**

## Headline

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **90.0%** (27 pairs) |
| Median error | 359.893 px |
| Mean error | 375.532 px |
| p95 error | 719.958 px |
| Worst-case error | 761.38 px |
| Median error, correctly-located pairs only | 1.151 px |

> The error distribution is bimodal: a correctly-located pair is off by about a pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore reported separately - a single average would hide the failure mode this problem is about.

## Threshold-wise pass rates

| Threshold | Pass rate |
|---|---|
| 5 px | 10.0% |
| 4 px | 6.7% |
| 2 px | 6.7% |
| 1 px | 3.3% |
| sub-pixel (0.5 px) | 3.3% |

## Runtime

| Metric | Value |
|---|---|
| Median (p50) | 31.6 ms |
| p95 | 36.3 ms |
| Mean | 32.2 ms |

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
| 10.4..11 | 8 | 377.213 | 88% | 0% |
| 9.04..9.45 | 8 | 382.543 | 100% | 0% |
| 9.45..9.82 | 7 | 346.743 | 100% | 0% |
| 9.82..10.4 | 7 | 332.519 | 71% | 14% |

## Stratified by `rotation_deg`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| -0.274..0.776 | 7 | 313.707 | 86% | 14% |
| -1.96..-0.274 | 8 | 423.546 | 88% | 0% |
| 0.776..1.23 | 7 | 322.881 | 86% | 0% |
| 1.23..2 | 8 | 497.259 | 100% | 0% |

## Stratified by `ambiguity_level`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| low | 24 | 377.213 | 92% | 0% |
| med | 6 | 334.835 | 83% | 17% |

## Stratified by `gt_x`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 438..551 | 7 | 313.707 | 86% | 0% |
| 551..744 | 7 | 337.150 | 86% | 14% |
| 744..941 | 8 | 356.952 | 88% | 0% |
| 76.4..438 | 8 | 458.127 | 100% | 0% |

## Stratified by `gt_y`

| Group | n | Median err (px) | Mis-lock rate | Pass@1px |
|---|---|---|---|---|
| 316..499 | 7 | 420.632 | 100% | 0% |
| 48..316 | 8 | 280.189 | 75% | 12% |
| 499..668 | 7 | 313.148 | 86% | 0% |
| 668..946 | 8 | 452.654 | 100% | 0% |
