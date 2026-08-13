# DriftLock — shared context

**Applied Materials "Drift-Sense" · SEMICON India Hackathon 2026 · submission deadline 16 Aug 2026.**
Team of 3, each running Claude Code on their own machine. This file is the shared brain: it is loaded
automatically on every machine, so nobody has to re-explain the project. **Keep it current.**

Full plan: `docs/PLAN.md`. Requirements: `docs/SPEC.md`. Decisions so far: `docs/DECISIONS.md`.
Current state: `docs/PROGRESS.md`. Cold start on a new machine: `docs/HANDOFF.md`.

---

## The problem in one paragraph

Given a **1000×1000 reference** image at 100× (1 nm/px) and a **1000×1000 search** image at 10×
(10 nm/px), return the centre `(x, y)` of the reference pattern inside the search image, in
search-image pixels. Because reference and search differ by 10× magnification, the reference's
footprint inside the search image is only **100×100 px**. The structures are highly periodic, so a
wrong location can look correct — that ambiguity is the actual problem.

## The thesis — every design choice follows from this

> **We don't match images. We invert the microscope.**

We know the forward model: beam PSF → area-average decimation → known geometric warp → Poisson shot
noise → Gaussian read noise. So localization is not a similarity search, it is a **maximum-likelihood
inverse problem** with a few nuisance parameters. And the periodic lattice, which everyone else
treats as the enemy, is a **ruler**: it gives pose in closed form. The *aperiodic* residual gives
identity — which cell.

If a proposed change does not follow from that framing, it probably does not belong.

---

## Non-negotiable contracts

Frozen on Day 0. Changing any of these requires telling the other two **before** you push.

### Coordinate convention — the #1 source of silent wrong answers

- Origin `(0, 0)` is **top-left**. `x` increases **right**, `y` increases **down**.
- Output is the **centre** of the matched region, as **float** (sub-pixel), in **search-image pixels**.
- `cv2` and numpy index `[row, col]` = `[y, x]`. **The conversion happens once, in `src/driftlock/io.py`, and nowhere else.**
- Every geometry test uses a **deliberately asymmetric** case (e.g. GT at `(300, 700)`).
  A symmetric test cannot catch an x/y swap, which is the bug most likely to sink this submission.

### CLI signatures

```bash
# Single pair — prints EXACTLY one line to stdout: "312.42,489.07". Nothing else.
python localize.py --reference ref.png --search search.png

# Batch — the evaluator must be able to run this with zero source edits.
python localize.py --manifest data/test/manifest.csv --out results/predictions.csv
python localize.py --input-dir data/test/ --out results/predictions.csv

# Optional flags, none required: --json --visualize OUT.png --no-rerank --verbose
python generate_dataset.py --num-samples N --split NAME --seed S --output-dir data
python evaluate.py --manifest M.csv --predictions P.csv --out results/
```

**stdout discipline:** in single-pair mode stdout carries the coordinate and nothing else. All logs,
warnings and progress go to **stderr**. Benchmark parsers break on chatty scripts.

### Manifest schema

`data/<split>/manifest.csv`. Deliberately a **superset of the sponsor's columns** so their manifests
load unchanged through the same reader.

```
id, reference_path, search_path, gt_x, gt_y, gt_box_x, gt_box_y, gt_box_w, gt_box_h,
architecture, preset, scale_ratio, rotation_deg, beam_spot_size_nm, dose_reference, dose_search,
detector_noise_sigma_ref, detector_noise_sigma_search, shear_amplitude_px, drift_jitter_px,
astigmatism_ratio, vignette_strength, gamma, barrel_distortion_k, charging_streak_prob,
charging_streak_intensity, speckle_sigma, salt_pepper_prob, edge_brightness_A, edge_sigma_nm,
linewidth_bias_nm, corner_rounding_px, mat_size_nm, strip_width_nm, boundary_bias,
ambiguity_level, seed
```

Paths in the manifest are **relative to the repo root**, always forward-slashed.
`predictions.csv` is `id, pred_x, pred_y, score, confidence_radius_px, runtime_ms`.

### Execution model — sequential, single track

We build **one thing at a time, in dependency order**, rather than splitting the work three ways.
The module boundaries below still hold as *structure*; they are no longer ownership assignments.

```
src/synth/        + generate_dataset.py    data generation
src/driftlock/    + localize.py            localization
                    evaluate.py            metrics, ablations, figures
```

**Order matters.** Each stage is gated on the one before it, so a wrong assumption cannot silently
propagate:

1. **Verify H1–H9** on real pairs from the sponsor's generator (below). Nothing is built until the
   ground rules are confirmed.
2. **Baseline + evaluation harness.** Reproduce the sponsor's baseline and measure it. That number
   is our floor and the ablation's first row — we cannot claim an improvement without it.
3. **Our generator**, so we control rotation, scale and continuous ground truth.
4. **Tier A matcher**, one stage at a time, each measured against the previous.
5. **Tier B** (analysis-by-synthesis, CRLB, conformal), then **Tier C** stretch work.

Because there is no parallelism to protect, the rule that replaces directory ownership is simply:
**do not start a stage until the previous one has a measured number in `results/`.**

---

## Facts about the sponsor's generator

Derived by reading the published starter resource
(HF Space `aayushraina21/drift-sense-synthetic-data`, which ships a full generator **and** a baseline).
It is the best available proxy for the evaluation data.

> ⚠️ **These are HYPOTHESES until empirically confirmed (rule R3).** They come from reading source
> code, not from running it. B confirms each on real generated pairs on Day 1 and records the outcome
> in `docs/DECISIONS.md`. **If one is refuted, the plan changes — say so immediately.**

| # | Hypothesis | Status |
|---|---|---|
| H1 | Reference footprint in the search image is exactly **100×100 px** | unverified |
| H2 | `gt = (x0/10 + 50, y0/10 + 50)` with `x0,y0` integer → GT on a 0.1 px grid | unverified |
| H3 | Noise is **Poisson** (shot, dose) **then Gaussian** (detector) — in that order | unverified |
| H4 | Same beam PSF on both images before the ↓10, so `INTER_AREA` is the **exact** forward operator | unverified |
| H5 | Search image additionally gets gamma, vignette, per-row shear+jitter, barrel distortion, speckle, salt-and-pepper, charging streaks | unverified |
| H6 | Mats (2600 nm) separated by strips (320 nm); each mat independently randomised; `boundary_bias=0.35` | unverified |
| H7 | Line positions are a random walk `pos += pitch + N(0, 1.5nm)` → **every cell has a unique fingerprint** | unverified |
| H8 | Contacts on an `(i+j)%2` checkerboard → the dangerous confusion is the **parity-preserving diagonal shift** (+1 word-line *and* +1 bit-line) | unverified |
| H9 | Their generator has **no rotation and no scale variation**, though the spec says 9:1–11:1 and 1–2° will be tested | unverified |

**The bar:** their baseline is `INTER_AREA` resize over 5 fixed scales → `matchTemplate` argmax →
`max_loc + tw/2`. No sub-pixel, no centre rule, no rotation, no ambiguity handling. Its output is
always `integer + 50.0`, so it carries a **~0.5 px quantization floor and cannot score on the
sub-pixel metric.** That is the gap we attack.

**Do not vendor their code.** `scripts/fetch_reference_generator.sh` clones it into gitignored
`third_party/`; attribute it in the README.

---

## Correctness rules — enforced, not aspirational

Three people and three Claude Code instances under deadline pressure is exactly the setup that
produces confident, plausible, wrong output. One fabricated citation or one number that doesn't match
the CSV destroys credibility for the whole submission.

- **R1 — No citation nobody opened.** `docs/REFERENCES.md` needs all five columns: claim, full
  citation, DOI/URL, verified-by initials, date. Missing any → not a citation, must not appear in the
  deck. If it can't be verified, delete the claim or restate it as our own reasoning.
- **R2 — No number typed by hand.** Every metric/table/figure is emitted by `evaluate.py` into
  `results/`. `scripts/verify_submission.py` fails the build on any deck number not found there.
  The likely failure is a **stale** number, not an invented one — regenerate and re-check last.
- **R3 — Verify foundations before building on them.** See the H1–H9 table above.
- **R4 — Convention bugs pass symmetric tests.** Asymmetric geometry tests, hand-derived expected
  values. **A test written by running the code and pasting its output tests nothing.**
- **R5 — Held-out discipline.** Calibration, training and evaluation seeds are disjoint and recorded.
  Never tune a threshold on the numbers being reported; if you do, that benchmark is dead.
- **R6 — Hedge claims to evidence.** "Sub-pixel" needs continuous GT. "Beats X" needs having *run* X.
  "Near the information limit" needs the computed CRLB. No unmeasured runtime claims — always state
  hardware, Python version and timing method.
- **R7 — No API used from memory.** Claude Code invents plausible signatures. Check against the
  **installed** version; anything imported must be exercised by a test or a real run before `main`.
- **R8 — Red-team pass on Day 3.** C re-derives B's headline numbers from raw outputs without reading
  B's summary. Anything that doesn't reproduce is pulled from the deck, not explained away.
- **R9 — Report what actually happened.** A component that underperforms goes in the ablation table
  as a negative result with its number. Failure analysis is worth 10%; honest negatives read as
  research maturity.

---

## Coding conventions

- **Python 3.14** (see ADR-0002 — verified, the whole stack has `cp314` wheels). `.venv` at repo root.
- **`pathlib` only.** No `os.path`, no string path concatenation, no `os.sep` assumptions.
  `ruff` has `PTH` enabled and will flag violations.
- **No absolute paths anywhere.** Derive from `Path(__file__).resolve().parents[n]` or take a CLI arg.
  `scripts/verify_submission.py` greps for `C:\`, `D:\`, `/home/` and **fails the build** — this is a
  literal item on the sponsor's checklist.
- **`opencv-python-headless`**, never `opencv-python` — the evaluator's box may have no display libs.
- **Determinism:** one seeded `np.random.Generator` threaded through; no global `np.random`.
  `PYTHONHASHSEED=0`; `cv2.setNumThreads(1)` before timing.
- **`torch` is optional and lazily imported** inside a try/except inside the function that needs it.
  `pip uninstall torch` must leave everything working. Never import it at module top level.
- Type hints on public functions. Docstrings say *why*, not *what*.
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `perf:`.
  Any commit that changes results also updates `results/`.

## Commands

```bash
make setup     # venv + pinned deps        (Windows: .\make.ps1 setup)
make data      # regenerate datasets from seeds
make bench     # full evaluation -> results/
make test      # pytest
make verify    # spec checklist + no-absolute-paths + determinism
make package   # dist/drift-lock-submission.zip in the spec's required layout
```

---

## Resuming work

**Read the `RESUME HERE` section at the top of `docs/HANDOFF.md` before doing anything.** It has the
current measured results, the shipped configuration, the one next action, and — importantly — the
list of approaches already tried and refuted with their numbers, so they do not get retried.

Two rules that have each been learned the hard way and cost real time when ignored:

1. **Validate on every split, not a convenient subset.** A stage checked on a subset has reversed a
   conclusion twice here (ADR-0012, ADR-0021).
2. **Do not re-rank candidates by a new criterion.** Six attempts, six failures (ADR-0024). The only
   selection stage that ever worked re-scores by the *same* criterion at a better geometry.

## Current gate

**Gate 6 cleared — a complete, verified, packaged submission exists.** Everything from here is
optional improvement. Live status in `docs/PROGRESS.md`; current numbers in `docs/RESULTS.md`
(generated from `results/`, never hand-edited).
