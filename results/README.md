# What is in `results/`

Every number in the deck, `docs/RESULTS.md` and the README is generated into this directory and
read back from it (rule R2). Nothing here is hand-edited.

**This file deliberately contains no numbers.** It is a map, not a report — a map with figures in it
would be one more place for them to go stale, which is the failure this directory exists to prevent.

## The current reported result

Three splits are reported. Each has a prediction file, a metrics file and a human-readable report,
plus a `_baseline` counterpart produced by the sponsor's own method on the identical pairs.

| split | what it is | files |
|---|---|---|
| `sponsor` | the sponsor's generator, fixed 10:1, no rotation | `predictions_sponsor.csv`, `metrics_sponsor.csv`, `report_sponsor.md` |
| `bench` | ours: 9–11:1 magnification, ±2° rotation, DRAM | `predictions_bench.csv`, `metrics_bench.csv`, `report_bench.md` |
| `finfet` | held-out architecture, never tuned on | `predictions_finfet.csv`, `metrics_finfet.csv`, `report_finfet.md` |

`dev` and `dev2` are the tuning family. They are deliberately **not** reported here; they appear only
inside paired comparisons that say so explicitly.

## Analysis outputs

| file | produced by | what it answers |
|---|---|---|
| `ablation.md` | `scripts/run_ablation.py` | every stage on every split, including the ones that failed (R9) |
| `significance.csv` | `scripts/significance.py` | paired McNemar vs the baseline, Wilson intervals |
| `failure_decomposition.csv` | `scripts/failure_decomposition.py` | which stage lost each mis-lock |
| `failure_mechanism.csv` | same | for each outscored failure, the ZNCC and evidence margins |
| `refine_forensics.csv` | `scripts/refine_forensics.py` | how far each post-selection stage moves the answer (ADR-0036) |
| `robustness.csv` | `scripts/robustness_sweep.py` | 25 operating points on validation-only seeds |
| `position_strata.csv` | `scripts/position_strata.py` | does target position matter |
| `pose_ceiling.csv` | `scripts/pose_ceiling.py` | how separable truth and impostor are at the exact pose |
| `oracle_ceiling.csv` | `scripts/oracle_ceiling.py` | what a perfect pose would buy |
| `runtime.csv` | `scripts/benchmark_runtime.py` | interleaved timing, with its own health gates |
| `optical.csv` | `scripts/optical_bench.py` | the RGB bonus modality |
| `failure_case/` | `scripts/make_failure_case.py` | the required visualised failure case |

`scripts/audit_results.py` re-derives the headline metrics from `predictions_*.csv` and the
manifests **without importing anything from `src/` or `evaluate.py`**, so a defect in our own metric
code cannot reproduce itself. Run it after any change.

## Historical files — kept, not current

These are from earlier stages of the project and are **not** part of the reported result. They are
retained because several are cited in `docs/FINDINGS.md` as the measurement behind a decision, and
deleting them would leave those claims unsupported.

    metrics_verify.csv        predictions_verify.csv     report_verify.md
    metrics_tierA_sponsor.csv predictions_tierA.csv      report_tierA_sponsor.md
    metrics_baseline_sponsor.csv                         report_baseline_sponsor.md
    metrics_holdout_dense.csv predictions_holdout_dense.csv
    metrics_holdout_finfet.csv predictions_holdout_finfet.csv

They describe **older configurations on older splits** and their numbers will not match the current
headline. `metrics_verify.csv` in particular is an early sponsor-split run under a since-retired
label; read `metrics_sponsor.csv` instead.

## A note on the `ambiguity_index` column

Prediction files carry a fifth column reporting how dangerous the periodic ambiguity was for that
pair: the best score divided by the best score among candidates that are **not** plausibly the same
location. It is unitless and **higher is safer** — a value near 1 means a structurally different
position scored just as well.

It was previously named `confidence_radius_px`, which was wrong twice over: it is not a radius and
it is not in pixels, and the name implied the opposite polarity. It was renamed on 18 August.

**The three current reporting files** — `predictions_{sponsor,bench,finfet}.csv` — carry the new
name. **The historical files listed under "Historical files" above still carry the old one**, because
regenerating them would mean re-running superseded configurations purely to relabel a column that
nothing reads. `evaluate.py` keys off `pred_x`, `pred_y` and `runtime_ms` and never touches it, so
the two schemas coexist without consequence. Recorded here rather than left for a reader to trip on.
