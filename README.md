# DriftLock

**Cross-magnification navigation-error recovery for wafer inspection tools.**
Applied Materials *Drift-Sense* problem statement — Hackathon 2026, organised as part of SEMICON India.

Locate a 100× reference pattern inside a 10× search image and return the target centre `(x, y)`,
to sub-pixel accuracy, on CPU, in a fraction of a second.

> Every metric in this README is **generated** from `results/` by `scripts/make_results_doc.py`,
> never typed by hand (see [correctness rule R2](CLAUDE.md#correctness-rules--enforced-not-aspirational)),
> and `scripts/verify_submission.py` fails the build if it goes stale. Nothing is claimed here that
> has not been measured.

---

## The problem

A wafer inspection tool revisits the same relative site on another die. Stage drift, vibration and
thermal effects make it land slightly off. Recovery is visual: use a previously captured 100×
close-up as a reference and find that structure inside a wider, noisier 10× search image.

The difficulty is that semiconductor structures are **highly periodic**. On a DRAM cell array the
reference matches almost equally well at dozens of positions, so ordinary template matching returns
a confident answer that is off by exactly one cell pitch — and nothing downstream detects it. That is
a silent data-integrity failure, and it is the problem this project is actually about.

## Approach

> **We don't match images. We invert the microscope.**

The forward model is known: beam PSF → area-average decimation → geometric warp → Poisson shot noise
→ Gaussian read noise. So localization is not a similarity search but a **maximum-likelihood inverse
problem**. And the periodic lattice that defeats ordinary matching is used as a **ruler**: it yields
scale and rotation in closed form. The *aperiodic* residual — sub-array boundaries, per-cell
line-placement variation — then resolves *which* cell.

The full method, with the reasoning behind each stage, is in [`docs/PLAN.md`](docs/PLAN.md) and
[`docs/METHOD.md`](docs/METHOD.md).

---

## Setup

**Python 3.14** is what the team targets; the code declares `requires-python = ">=3.11"` and runs on
either. See [ADR-0002](docs/DECISIONS.md).

```bash
git clone <repo-url> semicon
cd semicon
python -m venv .venv
source .venv/Scripts/activate      # Git Bash on Windows
# source .venv/bin/activate        # Linux / macOS
# .\.venv\Scripts\Activate.ps1     # PowerShell
pip install -r requirements.txt
```

Or use the task runner, which does the same thing:

```bash
make setup          # Windows PowerShell: .\make.ps1 setup
```

Dependencies are few and pinned by design: `numpy`, `scipy`, `opencv-python-headless`,
`scikit-image`, `pillow`, `pandas`, `PyYAML`, `matplotlib`.

- **No GPU required.** The deterministic path that produces the submitted coordinates runs on CPU.
- **`torch` is optional**, lazily imported, and used only by the flag-gated re-ranker
  (`requirements-optional.txt`). `pip uninstall torch` leaves every graded command working.
- **No network access at runtime**, and no model downloads. Any weights are committed in `model/`.

---

## Usage

### Locate a single pair

Prints **exactly one line** to stdout — the coordinate, nothing else. All logs go to stderr, so the
output is safe to pipe into a benchmark harness.

```bash
python localize.py --reference data/bench/reference/00000.png --search data/bench/search/00000.png
```

```
312.42,489.07
```

### Locate a batch

The evaluator can point this at their own data with **no source-code changes**:

```bash
python localize.py --manifest data/test/manifest.csv --out results/predictions.csv
python localize.py --input-dir data/test/            --out results/predictions.csv
```

### Optional flags

| Flag | Effect |
|---|---|
| `--json` | `{"x":312.42,"y":489.07,"score":0.91,"confidence_radius_px":0.8,"runtime_ms":78}` |
| `--visualize OUT.png` | Overlay: crosshair on the search image plus the correlation surface |
| `--no-rerank` | Force the purely deterministic path |
| `--verbose` | Per-stage timings to **stderr** |

### Generate data and evaluate

```bash
python generate_dataset.py --num-samples 30 --split bench --seed 1234 --output-dir data
python evaluate.py --manifest data/bench/manifest.csv --predictions results/predictions.csv --out results/
```

---

## Coordinate convention

This is the single most important contract in the project, and the place where a silent bug is most
likely. It is stated here, enforced in one module, and covered by a deliberately asymmetric test.

- Origin `(0, 0)` is the **top-left** of the search image.
- **`x` increases to the right. `y` increases downward.**
- The output is the **centre** of the matched region, as a **float** (sub-pixel), in
  **search-image pixels**.
- Because reference and search differ by 10× magnification, the reference's content occupies roughly
  a **100×100 px** footprint inside the 1000×1000 search image.
- **If several valid matches exist, the one whose centre is closest to the search-image centre is
  selected**, as the problem statement requires.

`cv2` and numpy index arrays as `[row, col]` = `[y, x]`. That conversion happens in exactly one
place, `src/driftlock/io.py` ([ADR-0007](docs/DECISIONS.md)), and `tests/test_geometry.py` checks it
with an asymmetric ground truth — a symmetric test case cannot detect an x/y swap.

---

## Repository layout

```
CLAUDE.md              Shared project context (thesis, contracts, correctness rules)
README.md              This file
requirements*.txt      Pinned dependencies (core / dev / optional)
generate_dataset.py    Synthetic SEM image-pair generator          [deliverable 2]
localize.py            Localization / inference entry point        [deliverable 2]
evaluate.py            Metrics, plots, robustness analysis         [deliverable 5]
configs/               Generation and evaluation configuration
src/synth/             Layout, SEM image formation, noise models
src/driftlock/         Preprocessing, lattice, matching, sub-pixel, confidence
model/                 Committed weights (small; no Git LFS, no downloads)
data/bench/            The >=30 committed validation pairs + manifest   [deliverable 6]
results/               Metrics, predictions, figures, failure case      [deliverable 5]
tests/                 Unit tests, including API-contract and geometry tests
scripts/               Smoke test, submission verifier, packaging
docs/                  PLAN, SPEC, DECISIONS, PROGRESS, HANDOFF, METHOD, REFERENCES
reference/             The original Applied Materials problem statement
```

**Data policy.** `data/bench/` is committed because it *is* the required validation evidence. Larger
splits are **regenerated from recorded seeds** (`make data`) rather than committed — the generator is
deterministic, so seeds reproduce the images exactly. See [ADR-0008](docs/DECISIONS.md).

---

## Results

<!-- BEGIN GENERATED README RESULTS -->

| Split | Config | Mis-lock (>5px) | Median (px) | pass@1px | pass@0.5px | Screen recall | Runtime p50 |
|---|---|---|---|---|---|---|---|
| **sponsor `verify`** (40 pairs) | baseline | 25.0% | 1.102 | 40.0% | 17.5% | n/a | 67 ms |
| *their generator, fixed 10:1, no rotation* | **DriftLock** | **20.0%** | **0.251** | **77.5%** | **72.5%** | 90.0% | 1311 ms (19x base) |
| **bench** (30 pairs) | baseline | 76.7% | 326.905 | 10.0% | 3.3% | n/a | 67 ms |
| *ours: 9–11:1 magnification, ±2° rotation, DRAM* | **DriftLock** | **16.7%** | **0.342** | **76.7%** | **63.3%** | 86.7% | 1204 ms (18x base) |
| **holdout FinFET** (30 pairs) | baseline | 90.0% | 359.893 | 3.3% | 3.3% | n/a | 72 ms |
| *held-out architecture, never tuned on* | **DriftLock** | **10.0%** | **0.220** | **83.3%** | **70.0%** | 90.0% | 1189 ms (17x base) |

**Mis-lock is the headline metric.** The error distribution is bimodal — a pair is either located to about a pixel or lost to a different repeat of the lattice, tens to hundreds of pixels away — so an averaged error describes neither case. Precision is therefore a *conditional* claim: once the correct repeat is selected, localization is sub-pixel.

**Screen recall is reported because the screen is a hard gate.** The pipeline ranks candidates with a cheap narrow pose refit and gives only the top 10 the expensive wide one; the wide stage cannot recover a candidate the screen dropped, so this column upper-bounds what any downstream stage could achieve. Reporting the mis-lock rate without it would hide the bound rather than state it.

Two different things are being measured and should not be averaged together. On the **sponsor's** data the magnification is a clean 10:1 with no rotation, so it tests precision. On **ours** — the 9:1–11:1 and ±2° envelope the problem statement says will be tested — the baseline does not work at all (77–90% mis-lock). That axis is invisible to anyone validating only on the published generator, because it produces neither.

**Hardware:** Windows 11 (AMD64) · Intel64 Family 6 Model 170 Stepping 4, GenuineIn. **Python version:** 3.14.3, OpenCV 5.0.0, 22 thread(s).

**Timing method:** runtimes come from `scripts/benchmark_runtime.py`, which interleaves the splits round-robin and discards a warm-up. The **x-baseline** figure is the one to compare across machines: this laptop throttles by up to 3x for identical code over a long session and does not recover on idling, and across three states in one day the absolute p50 moved 400 -> 630 -> 1262 ms while the ratio to the baseline held at 20.0, 18.5 and 18.8. The baseline is therefore run as a control in the same interleaved pass.

> ⚠️ **The absolute milliseconds in this table were measured on a throttled machine** — the baseline control read far above its quiet-machine value — and are not representative. The x-baseline ratios are unaffected. Re-run `scripts/benchmark_runtime.py` on a rested machine before quoting the p50 figures.

<!-- END GENERATED README RESULTS -->

Full ablation including every stage that did **not** work: [`results/ablation.md`](results/ablation.md).
Failure case with root cause: [`results/failure_case/`](results/failure_case/).

## Assumptions and limitations

Stated plainly rather than left for a judge to find.

1. **Selection is not solved, and the screen is a hard gate.** Every pass rate is capped by the
   mis-lock rate. Each failure is classified by the stage that lost it, in
   [`results/failure_decomposition.csv`](results/failure_decomposition.csv): of the 16 failures
   across 100 pairs, **3 were never candidates at all** (no selection rule can recover those),
   **4 were cut by the screen** before the expensive geometry ran, and **9 reached the final
   comparison and lost on correlation**. Only the last group is addressable by better ranking, and
   **six** re-ranking criteria were built, measured and rejected trying — all six are in the
   ablation with their numbers, and the principle they establish is
   [ADR-0024](docs/DECISIONS.md).
2. **Runtime is above our own 300 ms target** (see the p50 column in the table above — this
   sentence deliberately does not restate the figure, because a hand-typed copy of a generated
   number is exactly what goes stale). This is a deliberate, measured trade:
   the narrow-refit configuration runs at ~296 ms for +4 points of held-out mis-lock, and is
   reachable by config (`refit_steps=2, refit_scale_span=0.006, refit_rotation_span=0.30,
   refit_screen_steps=0`). We chose accuracy. There is no published
   runtime limit to calibrate against yet, and the ablation reports both operating points.
3. **Drift correction assumes a square frame.** The two-axis cancellation uses
   `S_row + S_col·(H−1)/(W−1)`; it is exact for the 1000×1000 images the spec defines and
   approximate otherwise.
4. **Rotation beyond ±2° and scale outside 9:1–11:1 are not searched.** Both ranges come straight
   from the problem statement; `PipelineConfig.pose_scale_range` / `pose_rotation_range` widen them
   at linear cost.
5. **Degradations are now stratified — and two of them hurt.**
   [`results/robustness.csv`](results/robustness.csv) sweeps 22 operating points across dose, read
   noise, scale, rotation and five degradations, deliberately running *past* the envelope the
   problem statement promises. Accuracy is essentially flat across a 32× dose range and across
   0°/±1°/±2° of rotation. The two soft spots are **charging streaks (33.3%)** — which the spec
   names explicitly as a possible degradation — and **barrel distortion (43.3%)**, which it does
   not. Scale beyond the promised range is the envelope limit: 16.7% inside 9–11:1, 40.0% at
   8–12:1. This is validation only; nothing is tuned on those seeds.
6. **Small differences between splits are not resolved, and we say so.**
   [`results/significance.csv`](results/significance.csv) carries Wilson intervals and a paired
   McNemar test. Two stress splits with *identical* generator parameters differing only by seed
   measured 20.0% and 26.7%, so cross-split gaps of a few points are directional only. The headline
   configuration change is quoted as a paired comparison on the same 100 pairs — 0 regressions,
   6 fixes, exact p = 0.031 — because that is the test the design actually supports.
7. **Phase congruency and ECC affine are broken, not evaluated.** Their ablation rows report an
   implementation failure — that is a different claim from "we tried it and it does not help".

Working assumptions about the evaluation data are tracked as **H1–H10** in [`CLAUDE.md`](CLAUDE.md)
and verified against 40 real pairs in [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## Development

```bash
make test        # unit tests
make verify      # spec checklist, no-absolute-paths scan, determinism check
make bench       # localize + evaluate over the bench set
make package     # dist/drift-lock-submission.zip in the sponsor's recommended layout
```

New to the project, or on a new machine? Read [`docs/HANDOFF.md`](docs/HANDOFF.md) — zero to running
in under ten minutes.

### Reproducibility, checked rather than asserted

`make package` writes `dist/drift-lock-submission.zip`. Before each submission that zip is extracted
into an empty directory and run end to end, and **all 15 accuracy metrics must come out identical** —
not close, identical. `scripts/verify_submission.py --strict` additionally enforces that every
number in the deck traces to a file in `results/`, that the generated results blocks are not stale,
and that no absolute path appears in any source file.

This is not ceremony. It has caught real defects, including a deck slide built from two invented
coordinates and a stale fallback deck that the packaging script could have shipped in place of the
real one. Both are recorded in [`docs/FINDINGS.md`](docs/FINDINGS.md).

## Attribution

The sponsor's starter synthetic-data generator
([HF Space](https://huggingface.co/spaces/aayushraina21/drift-sense-synthetic-data)) is used **only**
as an independent cross-validation dataset and as the baseline we measure against. Its code is **not
vendored** here; `scripts/fetch_reference_generator.sh` clones it into gitignored `third_party/`.
All generator code in `src/synth/` is our own.

Sources supporting the structures, image formation, noise and transformations we model are listed
with DOIs in [`docs/REFERENCES.md`](docs/REFERENCES.md).

## License

MIT — see [LICENSE](LICENSE).
