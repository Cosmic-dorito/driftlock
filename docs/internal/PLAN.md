# PLAN — DriftLock

**Deadline 16 Aug 2026. Today 12 Aug 2026 — 4 days.** Execution is sequential, one stage at a time.

> **This plan was rewritten on 12 Aug** after the first round of measurements. The original was
> written before any code existed and made several guesses that turned out to be wrong. What
> replaced them is recorded in `FINDINGS.md`; what they cost is recorded here so the same mistakes
> are not repeated.

---

## Where we actually are

| Metric | Sponsor baseline | DriftLock now | Ceiling identified |
|---|---|---|---|
| Mis-lock rate | 25.0% | **20.0%** | **7.5%** (K=20 candidate recall) |
| Median error | 1.102 px | **0.220 px** | 0.062 px (oracle drift) |
| pass@1 px | 40% | **80%** | ~92% if mis-lock is fixed |
| pass@0.5 px | 18% | **78%** | ~92% if mis-lock is fixed |
| Runtime p50 | 30 ms | 224 ms | 300 ms budget |

Full detail in `RESULTS.md`. Two facts drive everything below:

1. **Every pass rate is pinned at 80% by the 20% mis-lock rate.** Precision is already excellent
   (0.143 px median among located pairs). Further precision work cannot move the headline numbers.
2. **Rotation and scale are completely untested**, because the sponsor's generator produces neither
   — while the spec says 9:1–11:1 and 1–2° *will* be tested.

---

## What the plan got wrong, and the lesson

Recording this because the corrections were expensive and the pattern is repeatable.

| Original assumption | What measurement showed | Lesson |
|---|---|---|
| Preprocessing (Anscombe, phase congruency, destriping) would drive accuracy | All three gave nothing or actively hurt; destriping made mis-lock *worse* because DRAM word lines are horizontal | A correction aimed at an artefact must be checked against the **signal**, not just the artefact |
| Sub-pixel refinement was the route to the 1 px threshold | Worth only 40%→45%; the real barrier was a coordinate-frame offset from raster drift | Diagnose *why* the error exists before optimising against it |
| The lattice would be used as a "ruler" for pose | Never needed — there is no rotation or scale in this data to measure | Do not build for a degradation you have not confirmed is present |
| Blind drift estimation was infeasible (abandoned once) | Works well; the first two attempts failed for *fixable* reasons, not fundamental ones | Distinguish "this approach failed" from "this is impossible" |
| Python 3.11 required | 3.14 fine; `cp314` wheels exist across the stack | Test the environment, do not assume it |

**The meta-lesson, which now governs the remaining work:** the two largest wins (PADM, drift
correction) both came from *measuring the specific failure mode first*, and every stage built from
a general prior about "what usually helps in vision" was wasted. So: **measure, then build.**

---

## Priorities for the remaining 4 days

Ordered by points-per-hour, not by interest.

### P0 — Our own generator · **30% of the score, currently at ZERO**

The largest single block of unclaimed points, and a **mandatory deliverable** ("separate,
documented Python code for dataset generation"). It is also the only way to test the rotation and
scale envelope the spec promises, so it de-risks the 50% bucket at the same time.

Must produce, in physically correct order: layout → SE edge brightening → charging shading → beam
PSF → **rotation (0–2°) and scale (9:1–11:1)** → raster drift → barrel distortion → Poisson shot
noise → Gaussian detector noise → speckle/S&P/streaks/vignette/gamma → quantise. Independent RNG
streams per acquisition; **fractional crop origins** so ground truth is continuous and sub-pixel
claims are honest; full metadata and seeds per pair; DRAM primary, FinFET secondary.

Five things ours does that the sponsor's cannot: SE edge brightening (theirs paints flat gray
levels), true rotation, true scale variation, continuous ground truth, richer aperiodic content.
Each needs a citation (30% bucket is judged on *literature-based* justification).

**Exit:** ≥30 committed bench pairs, determinism test passing, `verify_submission.py` dataset
checks green.

### P1 — Fix the mis-lock rate · unblocks every pass rate

The binding constraint. Candidate recall says 92.5% of the answers are already in the top-20, so
this is a **ranking** problem with a 12.5-point gap to the ceiling.

Ordered by expected value:

1. **Learned re-ranker.** Now strongly justified rather than speculative: the answer is in the set,
   the negatives are exactly definable (lattice-equivalent positions), and hand-designed scoring has
   demonstrably plateaued. Small model, CPU, lazy `torch`, `--no-rerank` must always work.
2. **Fix PADM's residual SNR.** It captures ~a fifth of the available gain. The residual is
   noise-dominated at dose 200; denoising the search image *before* decomposition is untested and
   cheap.
3. **Re-test Anscombe here.** It was a null result against an integer argmax, but the re-ranker
   scores *continuous* residual correlations, which is exactly where variance stabilisation should
   matter. Genuinely untested rather than refuted.

**Exit:** mis-lock < 12%, verified on both generators.

### P2 — Robustness across the promised envelope

Once P0 exists: measure across 9:1–11:1 scale, 1–2° rotation, dose sweeps, gamma, vignetting,
speckle and salt-and-pepper. Any of these could be in the evaluation set and **none is currently
tested**. Expect failures; fix the ones that appear.

### P3 — Deliverables

README with results and honest limitations; the 12-slide deck on the sponsor's structure; complete
`REFERENCES.md` with all five columns verified; `verify_submission.py --strict` clean; clean-machine
dry run.

### P4 — Only if everything above is done

CRLB analysis, conformal prediction intervals, SOTA matcher comparison, RGB extension, demo video.
These are strong differentiators but they are worth nothing if P0 is missing.

---

## Schedule

| Day | Focus | Gate |
|---|---|---|
| **12 Aug** | P0 generator: DRAM layout, SEM physics, noise, rotation/scale, manifest | 30 bench pairs generated, determinism test green |
| **13 Aug** | P1 re-ranker + PADM SNR; FinFET; cross-generator eval | mis-lock < 12% |
| **14 Aug** | P2 robustness sweep; failure analysis; fix what breaks | **CORE FREEZE 18:00** — submittable package exists |
| **15 Aug** | P3 deck, README, references, packaging, clean-machine dry run | `--strict` clean |
| **16 Aug** | Submit in the morning, buffer intact | — |

**Freeze discipline:** after 14 Aug 18:00 the default code path does not change. P4 work is
additive and flag-gated only.

---

## Method — what the pipeline does now

Config-driven, every stage a flag, so the ablation table is a sweep rather than forked code paths.

1. **Forward model (A3).** `INTER_AREA` downscale of the reference. Not a convenience — the search
   is `(canvas ⊛ PSF) ↓10 area-average` and the reference is `(crop ⊛ PSF)` with the *same* PSF, so
   area-averaging is exactly the missing operator. Verified: ZNCC at truth averages 0.835.
2. **Top-K candidates (A6).** K=20, NMS at the lattice pitch. Never the argmax — the correct answer
   is the runner-up often enough to matter (worst case: behind by 0.0124 ZNCC, a 1.3% margin).
3. **PADM re-scoring (A7).** Remove lattice harmonics in Fourier; score candidates on the aperiodic
   residual. *The lattice tells you where within a cell; the residual tells you which cell.*
4. **Closest-to-centre rule (A8).** The spec's tie-break, implemented literally and visibly.
5. **Sub-pixel DFT (A9).** Upsampled cross-correlation, `normalization=None` (the default silently
   returns zero shift on blurred images — ADR-0009).
6. **Blind drift correction.** Correlate rows separated by a fixed gap to recover the raster drift,
   then map the coordinate back to the undrifted frame. The single largest precision gain.

**The thesis, now supported by measurement rather than asserted:** we don't match images, we invert
the microscope. The two largest wins both came from modelling acquisition physics — the periodic
decomposition and the drift inversion — while every stage motivated by generic vision priors gave
nothing.

---

## Non-negotiables

- Single-pair mode prints exactly one line to stdout; all logs to stderr.
- Batch mode runs an evaluator's manifest with **zero source edits**.
- Eight direct dependencies; `torch` optional and lazily imported; `pip uninstall torch` leaves everything working.
- No network at runtime, no model downloads, weights committed.
- Deterministic: same seed → identical output, on any machine.
- No absolute paths (`verify_submission.py` fails the build on them — a literal spec checklist item).
- Every number in the deck traceable to `results/`.
- No citation nobody opened.
