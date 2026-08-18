# DriftLock

**Cross-magnification navigation-error recovery for wafer inspection tools.**
Applied Materials *Drift-Sense* problem statement — Hackathon 2026, organised as part of SEMICON India.

Locate a 100× reference pattern inside a 10× search image and return the target centre `(x, y)`,
to sub-pixel accuracy, on CPU, in a fraction of a second.

> Every metric in this README is **generated** from `results/` by `scripts/make_results_doc.py`,
> never typed by hand (correctness rule R2, enforced by `scripts/verify_submission.py`),
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

The full method, with the reasoning behind each stage, is in
[`docs/DECISIONS.md`](docs/DECISIONS.md) — one record per non-obvious choice, including the ones
that were measured and rejected.

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
`scikit-image`, `pillow`, `pandas`, `PyYAML`, `matplotlib` — eight direct, plus four transitive
packages pinned for reproducibility.

Two dependency files ship, and they answer different questions:

| File | Use it for |
|---|---|
| `requirements.txt` | **Reproducing the results.** The curated runtime set — install this. |
| `requirements-freeze.txt` | The complete `pip freeze` of the development environment, as the problem statement asks for. Exhaustive, and includes test and build tooling (`pytest`, `ruff`, `python-pptx`) that the localizer never imports. |

- **No GPU required.** The deterministic path that produces the submitted coordinates runs on CPU.
- **`torch` is optional**, lazily imported, and used only by the flag-gated re-ranker
  (`requirements-optional.txt`). `pip uninstall torch` leaves every graded command working.
- **No network access at runtime, and no weights to download** — nothing is trained, so there is no model to ship or load.

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
| `--json` | `{"x":312.42,"y":489.07,"score":0.91,"ambiguity_index":1.31,"runtime_ms":78}` |
| `--visualize OUT.png` | Side-by-side overlay: reference and search, with the prediction, the truth when known, and the runner-up candidates boxed |
| `--verbose` | Per-stage timings to **stderr** |

### `.npy` inputs, and converting them to PNG

**The inference script reads `.npy` pairs directly — no conversion step is required before scoring.**

```bash
python localize.py --reference ref.npy --search search.npy
```

The same pair as `.npy` and as `.png` returns byte-identical coordinates
([`tests/test_npy_io.py`](tests/test_npy_io.py) asserts this end to end), so it does not matter
which form the evaluation data arrives in. That is deliberate: the problem statement says an
inference script needing manual preparation cannot be scored, so conversion is never on the
critical path.

Conversion is provided separately, for **visual inspection**:

```bash
python scripts/npy_to_png.py --input ref.npy --output ref.png     # one file
python scripts/npy_to_png.py --input data/test --output png/ --recursive   # a whole tree
```

`--recursive` mirrors the input directory structure under `--output`, so two arrays sharing a
basename in different folders cannot collide. Float arrays are rescaled to 8-bit for display using
**the identical rule the loader applies** — values in `[0, 1]` are scaled by 255, values already
spanning `[0, 255]` are left alone — so the PNG shows exactly what the matcher received. Keep the
`.npy` as the source of truth if your data has meaning outside `[0, 255]`.

### Generate data and evaluate

```bash
python generate_dataset.py --num-samples 30 --split bench --seed 1234 --output-dir data
python evaluate.py --manifest data/bench/manifest.csv --predictions results/predictions.csv --out results/
```

#### Regenerating every reported split

`data/bench` is committed, so it needs no regeneration. The other two reporting splits are
regenerated from seed:

| Split | Command |
|---|---|
| `bench` (committed) | `python generate_dataset.py --num-samples 30 --split bench --seed 1234 --output-dir data` |
| `holdout_finfet` | `python generate_dataset.py --num-samples 30 --split holdout_finfet --seed 424242 --output-dir data --architectures finfet` |
| `optical` (bonus) | `python generate_dataset.py --num-samples 30 --split optical --seed 77001 --modality optical` |

The `sponsor` split comes from the organiser's own published generator, not ours; see
`scripts/fetch_reference_generator.sh`.

> ⚠️ **Scope of the determinism guarantee.** `tests/test_determinism.py` asserts that the same seed
> produces byte-identical images **on the same platform and library versions** — it runs the
> generator twice on one machine. It is *not* a cross-platform guarantee, and measurement says it
> does not hold across platforms: regenerating `bench` with seed 1234 on macOS/arm64 against the
> committed images generated on Windows/x86-64 reproduces the **ground-truth coordinates exactly**
> but leaves 93–98% of pixels differing (mean Δ ≈ 15 grey levels on the search image).
>
> The likely mechanism is that OpenCV's filtering and warping differ slightly between SIMD
> back-ends; that perturbs the input to `rng.poisson`, whose rejection sampler then draws a
> different number of variates and desynchronises the stream for every subsequent pixel. Consistent
> with the noisier search image diverging about three times as much as the reference.
>
> **Consequence for a reviewer:** regenerate on any platform and the *task* is identical — same
> layout, same ground truth, same difficulty — but the pixels are not the same pixels. To check our
> reported numbers against our exact images, use the committed `data/bench`.

### RGB optical extension (the problem statement's bonus)

```bash
python generate_dataset.py --num-samples 30 --split optical --seed 77001 --modality optical
python scripts/optical_bench.py --manifest data/optical/manifest.csv
```

`--modality optical` emits 3-channel brightfield pairs through a genuinely different forward model,
not a colourised SEM. An optical microscope resolves `0.61 λ/NA` = **373 nm** against a 64 nm DRAM
word-line pitch, so the cell lattice is *absent* rather than blurred — the modality images a coarser
layer, where mats and peripheral routing play the role the cell array plays in SEM. Contrast comes
from thin-film interference, and the per-channel PSF and chromatic aberration make the three
channels genuinely non-redundant.

**The localizer needs no changes**: `load_grayscale` folds colour to luminance, and the same
physics-based matcher reaches a median error of **0.10 px** on diffraction-limited RGB. Measuring
the colour projection from the reference instead of assuming Rec. 601 weights
([`src/driftlock/color.py`](src/driftlock/color.py)) halves mis-lock again and collapses the p95
error from 11.94 px to 0.51 px. See [ADR-0033](docs/DECISIONS.md) and
[`results/optical.csv`](results/optical.csv).

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
README.md              This file
requirements*.txt      Pinned dependencies (core / dev / optional)
generate_dataset.py    Synthetic SEM image-pair generator          [deliverable 2]
localize.py            Localization / inference entry point        [deliverable 2]
evaluate.py            Metrics, plots, robustness analysis         [deliverable 5]
src/synth/             Layout, SEM image formation, noise models
src/driftlock/         Preprocessing, lattice, matching, sub-pixel, confidence
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
| **sponsor `verify`** (40 pairs) | baseline | 25.0% | 1.102 | 40.0% | 17.5% | n/a | 20 ms |
| *their generator, fixed 10:1, no rotation* | **DriftLock** | **0.0%** | **0.179** | **97.5%** | **92.5%** | 90.0% | 632 ms (32x base) |
| **bench** (30 pairs) | baseline | 76.7% | 326.905 | 10.0% | 3.3% | n/a | 19 ms |
| *ours: 9–11:1 magnification, ±2° rotation, DRAM* | **DriftLock** | **13.3%** | **0.300** | **83.3%** | **66.7%** | 86.7% | 568 ms (29x base) |
| **holdout FinFET** (30 pairs) | baseline | 90.0% | 359.893 | 3.3% | 3.3% | n/a | 20 ms |
| *held-out architecture, never tuned on* | **DriftLock** | **3.3%** | **0.214** | **90.0%** | **76.7%** | 90.0% | 564 ms (29x base) |

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

1. **The remaining failures sit at a margin of about 0.01 of correlation or less, not at a tuning
   gap.** Given the generator's *exact* scale and rotation, the true site and the site the pipeline
   chose are *statistically indistinguishable* — the truth is ahead in **4 of 10**, p = **0.754**,
   and is nominally ahead on the mean. A perfect pose does not rescue the failures either: an
   oracle-pose plain argmax scores **70/100** against the shipped **89/100**. Reproduce with
   `python scripts/pose_ceiling.py`; details in [FINDINGS §35a and §37](docs/FINDINGS.md).
   The paired subset shrank to 3 pairs once the pose-evidence stage landed, so the "fraction of the
   deficit the refit closes" is no longer estimable and the script reports it as such rather than
   dividing by a near-zero denominator.
   *An earlier version of this note claimed a 0.065 deficit and 89% recovery. That did not
   reproduce — the figure it compared against was the maximum of the correlation surface rather than
   a score at a location, and a maximum over ~810,000 positions exceeds any nominated point by
   construction. The retraction is [FINDINGS §37](docs/FINDINGS.md); nothing shipped was affected.*
2. **Candidate generation is now the binding constraint.** Every pass rate is capped by the mis-lock
   rate, and each failure is classified by the stage that lost it in
   [`results/failure_decomposition.csv`](results/failure_decomposition.csv). Of the 8 remaining
   failures across 100 pairs, **3 were never candidates at all**, **0 were cut by the screen**, and
   **5 reached the final comparison and lost on correlation**.

   Two changes on 15 Aug produced that. Reading the refit's pose grid as evidence rather than taking
   its maximum ([ADR-0032](docs/DECISIONS.md)) cut the *outscored* bucket from 9 to 4. Widening the
   screen's cut from 10 to 30 ([ADR-0034](docs/DECISIONS.md)) then emptied the *screened* bucket,
   4 → 0 — and it only works in that order: the same knob had been measured as flat, because the
   candidates a wider cut recovers used to be handed to the plain maximum, which is the statistic
   that loses ties. Six *other* re-ranking criteria were built, measured and rejected before either
   of these; all six are in the ablation with their numbers, and the principle they establish
   ([ADR-0024](docs/DECISIONS.md)) is why ADR-0032 is a different *summary* of the existing score
   rather than a new criterion.

   *One honest negative:* ADR-0032 costs 3 pairs on the `bench` split while fixing 17 across the
   other four. Its independent evidence is +8/−3 on the 100 reporting pairs (p = 0.227); the pooled
   +17/−3 over 300 pairs (p = 0.0026) includes the tuning splits and is a reproducibility statement,
   not an independent one. **`absent` has not moved through any of this** — nothing built so far
   touches candidate generation, which is where the remaining headroom is.
3. **Runtime is above our own 300 ms target** (see the p50 column in the table above — this
   sentence deliberately does not restate the figure, because a hand-typed copy of a generated
   number is exactly what goes stale). This is a deliberate, measured trade: the narrow-refit
   configuration is faster for +4 points of held-out mis-lock, and is reachable by config
   (`refit_steps=2, refit_scale_span=0.006, refit_rotation_span=0.30, refit_screen_steps=0`). We
   chose accuracy. There is no published runtime limit to calibrate against yet, and the ablation
   reports both operating points.

   The figures above are **certified**: `scripts/benchmark_runtime.py` runs the baseline as a
   control in the same interleaved pass and refuses to publish absolute milliseconds unless both
   the control *and* the dispersion of the measurement are in normal range. That second gate exists
   because the control alone has a blind spot — a 19 ms baseline completes inside the CPU's boost
   window while a 400 ms call does not, so on this laptop the first heavy run after idle read 1.6×
   slow with a perfectly clean control ([FINDINGS §19b](docs/FINDINGS.md)).
4. **Drift correction assumes a square frame.** The two-axis cancellation uses
   `S_row + S_col·(H−1)/(W−1)`; it is exact for the 1000×1000 images the spec defines and
   approximate otherwise.
5. **Rotation beyond ±2° and scale outside 9:1–11:1 are not searched.** Both ranges come straight
   from the problem statement; `PipelineConfig.pose_scale_range` / `pose_rotation_range` widen them
   at linear cost.
6. **No positional dependence was detectable in this 100-pair sample.**
   [`results/position_strata.csv`](results/position_strata.csv) splits the same 100 evaluated pairs
   by distance from the field centre (targets span 32–547 px) and by proximity to the frame edge.
   Every stratum's Wilson interval overlaps every other and the pattern is non-monotone. That is a
   statement about what this sample can resolve, not a proof that position is irrelevant — the
   intervals are wide. It is also why the spec's closest-to-centre tie-break cannot help here
   ([ADR-0021](docs/DECISIONS.md)).
7. **Degradations are now stratified — and two of them hurt.**
   [`results/robustness.csv`](results/robustness.csv) sweeps 25 operating points across dose, read
   noise, scale, rotation and five degradations, deliberately running *past* the envelope the
   problem statement promises. Accuracy is essentially flat across a 32× dose range (0.0–16.7%) and
   across 0°/±1°/±2° of rotation. The two soft spots are **charging streaks (30.0%)** — which the
   spec names explicitly as a possible degradation — and **barrel distortion (33.3%)**, which it
   does not. Scale beyond the promised range is the envelope limit: 16.7% inside 9–11:1, 33.3% at
   8–12:1. This is validation only; nothing is tuned on those seeds.

   **Charging streaks are the dominant degradation-specific weakness, and we know why.** The failure
   decomposition inverts there: 23.3% of pairs lose the true location *before* it is ever a
   candidate, against 3.3% lost at final ranking — so it is a signal-recovery problem, not a
   ranking one. Raising `top_k` to 20 or 30 changes nothing, which says the
   correlation peak is **erased rather than demoted**. An artifact-aware correction was built and
   measured: it recovers one absent peak in thirty and regresses the primary benchmark, so it is
   not shipped ([FINDINGS §26](docs/FINDINGS.md)).
8. **Small differences between splits are not resolved, and we say so.**
   [`results/significance.csv`](results/significance.csv) carries Wilson intervals and a paired
   McNemar test. Two stress splits with *identical* generator parameters differing only by seed
   differ by several points on identical parameters, so cross-split gaps of a few points are
   directional only; the exact figure is derived into `results/significance.csv` rather than quoted
   here, because it moves whenever the sweep is regenerated. The comparison against the sponsor's
   baseline is quoted as a paired test on the same 100 pairs — **0 regressions, 55 fixes** — because
   that is the test the design actually supports.
9. **Phase congruency and ECC affine are broken, not evaluated.** Their ablation rows report an
   implementation failure — that is a different claim from "we tried it and it does not help".

Working assumptions about the evaluation data are tracked as **H1–H10** in [`docs/SPEC.md`](docs/SPEC.md)
and verified against 40 real pairs in [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## Development

```bash
make test        # unit tests
make verify      # spec checklist, no-absolute-paths scan, determinism check
make bench       # localize + evaluate over the bench set
make package     # dist/drift-lock-submission.zip in the sponsor's recommended layout
```

New to the project, or on a new machine? Read [`docs/internal/HANDOFF.md`](docs/internal/HANDOFF.md) — zero to running
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
