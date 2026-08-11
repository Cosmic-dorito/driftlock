# Decision log (ADRs)

One short record per non-obvious choice: what we decided, why, and what would change our mind.
Written **as we go** — this is the raw material for the PPT's method slides and the failure-analysis
section. Reconstructing it on Day 4 costs hours; writing it now costs minutes.

Format: `ADR-NNNN · date · status · decision · why · what would change our mind`.

---

## ADR-0001 · 2026-08-11 · accepted · Clean repo at root, submission tree emitted on demand

**Decision.** The git repo root is the working project (with `docs/`, `tests/`, `scripts/`).
`scripts/package_submission.py` emits `dist/drift-lock-submission.zip` containing exactly the folder
tree the sponsor recommends (`submission/` with `solution_presentation.pptx`, `README.md`,
`requirements.txt`, `generate_dataset.py`, `localize.py`, `configs/`, `src/`, `model/`, `results/`,
`references/`).

**Why.** The sponsor's layout is *recommended*, not mandatory, and it has no room for a decision log,
tests or tooling. Judges who browse the GitHub repo should see a professional project; the graded
artifact should have exactly the required shape. This gets both without duplicating code.

**What would change our mind.** If the organizers publish a hard requirement that the repository root
itself must be `submission/`, we restructure — the packaging script already proves we can produce it.

---

## ADR-0002 · 2026-08-11 · accepted · Standardize on Python 3.14, not 3.11

**Decision.** The team targets **Python 3.14** with pinned dependencies.

**Why.** The original plan recommended 3.11 out of caution about wheel availability on 3.14. That
caution was **wrong and was corrected by testing rather than assumption** (rule R7). On this machine
Python 3.14.3 resolves the entire stack from `cp314` wheels: `scikit-image` 0.26.0,
`opencv-python-headless`, `numpy` 2.4.4, `scipy` 1.18.0, and `torch` 2.12.1+cpu is already installed.
Standardizing on the interpreter that is actually present removes a setup step for three people and
an install risk on Day 0.

**What would change our mind.** Any dependency we later need that lacks a `cp314` wheel. The
`requires-python` floor stays at `>=3.11` so the code remains runnable on an evaluator's older
interpreter — we target 3.14 but do not *require* it.

**Follow-up.** The exact OpenCV major version is settled separately in ADR-0003.

---

## ADR-0003 · 2026-08-11 · accepted · Pin OpenCV 5.0.0.93 — verified, no downgrade needed

**Decision.** Pin `opencv-python-headless==5.0.0.93`. No need to fall back to the 4.x line.

**Why it mattered.** `pip` resolves OpenCV to **5.x** on Python 3.14, a major version bump, and we
depend on `matchTemplate`, `TM_CCOEFF_NORMED`, `findTransformECC` + `MOTION_AFFINE`, `INTER_AREA`
and `remap`. Rule R7 forbids trusting an API from memory, so we tested rather than assumed.

**Evidence (2026-08-11, OpenCV 5.0.0.93 / Python 3.14.3).**
- All 22 required symbols present.
- `minMaxLoc` still returns **`(x, y)`**, not `(row, col)` — verified with an asymmetric template
  origin `(x=60, y=40)`, since a symmetric case cannot detect a swap.
- `findTransformECC` recovers a known sub-pixel translation to **0.055 px** (`MOTION_TRANSLATION`)
  and **0.037 px** (`MOTION_AFFINE`) on band-limited data. Step A9 is sound.

All of the above is now locked in `tests/test_deps_api.py`, so environment drift fails a test
instead of surfacing as a mysterious accuracy regression.

**Note on benchmarking sub-pixel methods.** Our first measurement used white noise as the test image
and made ECC look 7× worse (0.26 px). Bilinear/bicubic warping of white noise aliases badly. Real
SEM frames are band-limited by the beam PSF, so **all sub-pixel benchmarks must use band-limited
test signals** or they will understate accuracy.

---

## ADR-0009 · 2026-08-11 · accepted · `phase_cross_correlation` must use `normalization=None`

**Decision.** Every call to `skimage.registration.phase_cross_correlation` in this codebase passes
**`normalization=None`**. The library default is `'phase'` and it is wrong for our data.

**Why.** Phase normalization whitens the spectrum by dividing by magnitude. On a strongly
band-limited image the high-frequency magnitudes are ≈0, so that division amplifies pure numerical
noise and swamps the true correlation peak — it silently returns approximately **zero shift**.

**Evidence (2026-08-11), true displacement 2.86 px, `upsample_factor=100`:**

| blur σ | `normalization='phase'` | `normalization=None` |
|---|---|---|
| 0.0 | 0.18 px | 0.16 px |
| 1.0 | 0.09 px | **0.02 px** |
| 3.0 | **2.80 px — fails** | 0.12 px |
| 6.0 | **2.84 px — fails** | 0.61 px |

**Why this is not hypothetical.** Our search images are blurred by the beam PSF and then
area-downsampled; the reference downscaled to a 100×100 template is smoother still. Left
undiscovered, this would have surfaced on Day 2 as "sub-pixel refinement makes results worse" and
cost hours to trace.

**What would change our mind.** If scikit-image changes the phase-normalization implementation.
`tests/test_deps_api.py` asserts the failure mode still exists, so an upstream fix will fail that
test loudly rather than silently — at which point re-benchmark both settings before touching this.

**Caveat to carry forward.** At blur σ=6 even `normalization=None` degrades to 0.61 px. Sub-pixel
accuracy is blur-dependent, so B should measure it on real generated pairs (Gate 2) rather than
assuming the 0.02 px best case generalises.

---

## ADR-0004 · 2026-08-11 · accepted · Write our own generator; cross-validate on the sponsor's

**Decision.** Build our generator from scratch (own code, own physics), **and** additionally evaluate
our matcher on data produced by the sponsor's published generator. Do not vendor their code; fetch it
into gitignored `third_party/` and attribute it.

**Why.** Synthetic augmentation is **30%** of the score, judged on realism, diversity, reproducibility
and literature-based justification — a fork reads as derivative in exactly the bucket where
originality is graded. Meanwhile, evaluating on *their* generator is the only honest evidence that we
have not overfit to our own data distribution. Their generator also cannot produce rotation or scale
variation, both of which the spec says will be tested, so ours must cover what theirs cannot.

**What would change our mind.** If the organizers state that the evaluation set comes verbatim from
the published generator, matching its distribution becomes more valuable than originality — but we
would still keep our own for the rotation/scale envelope.

---

## ADR-0005 · 2026-08-11 · accepted · DRAM primary, FinFET secondary

**Decision.** Lead with DRAM; also generate and report FinFET.

**Why.** Both are judged equally, but a DRAM cell array is periodic in **two** directions, which
maximises the periodic ambiguity the problem statement is actually about. FinFET top-down is largely
periodic in one direction and partly disambiguates itself. Solving the harder case implies the
easier. FinFET costs little extra because the rendering path is shared, and it buys diversity points
in the 30% bucket.

---

## ADR-0006 · 2026-08-11 · accepted · Deterministic coordinate, learning in the decision layer

**Decision.** The coordinate itself is produced by a deterministic estimator. Learned components are
confined to (a) confidence calibration and (b) re-ranking ambiguous candidates, and both are optional
at runtime. `torch` is lazily imported; `pip uninstall torch` must leave everything working.

**Why.** The 50% bucket rewards accuracy *and* runtime, and a deterministic CPU estimator wins both
without a GPU, a download, or a weights-loading failure mode on the evaluator's machine. An
inspection tool also cannot accept a stochastic answer to "where am I?". Learning genuinely adds
value in the decision layer, where a wrong answer is recoverable.

**What would change our mind.** If the deterministic path plateaus above the 1 px threshold on hard
ambiguous cases, the re-ranker moves from optional to core — but it stays behind a flag.

---

## ADR-0007 · 2026-08-11 · accepted · Coordinate conversion happens in exactly one place

**Decision.** All `(row, col) ↔ (x, y)` conversion lives in `src/driftlock/io.py`. No other module
converts. Geometry tests use a deliberately asymmetric ground truth.

**Why.** `cv2`/numpy index `[y, x]`; the spec wants `(x, y)`. An x/y swap is the single most likely
bug to silently produce plausible wrong answers, and a symmetric test case cannot detect it. One
conversion site means one place to test and one place to be wrong.

---

## ADR-0008 · 2026-08-11 · accepted · Commit the bench set, regenerate everything else from seeds

**Decision.** `data/bench/` (the ≥30-pair validation set the spec requires) is committed. All larger
splits are regenerated from recorded seeds via `make data` and are gitignored.

**Why.** The bench set *is* the required evidence and must travel with the submission. Committing
hundreds of megabytes of PNGs would make the repo hostile to clone and adds nothing — the generator
is deterministic, so seeds reproduce the data exactly. "Reproducible from seeds rather than shipped
as opaque blobs" is a reproducibility strength worth stating in the deck.

**Depends on.** `.gitattributes` marking `*.png binary`; without it Windows CRLF conversion corrupts
committed PNGs and silently breaks the byte-identical reproducibility claim.

---

## ADR-0010 · 2026-08-11 · accepted · The residual error is a drift-frame offset, not a matching error

**Finding.** After correlation finds the right lattice repeat, the remaining ~0.87 px error is
**not** imprecision in the match. The raster drift physically displaces the search image's content
(`apply_raster_drift` remaps row *r* by `shear·(r/999)` in x), while the ground truth is defined in
the **undrifted** frame. So the matcher is finding exactly where the content *is*, and the ground
truth records where it *would have been* without drift. That gap is unreachable by any improvement
to the similarity measure.

**Evidence.** Inverting the shear analytically, `x_corrected = x_found + shear·(y_found/999)`, over
40 sponsor pairs:

| | median (located) | mean | pass@1px | pass@0.5px |
|---|---|---|---|---|
| as found | 0.866 px | 0.827 | 45% | 18% |
| shear-corrected | **0.062 px** | 0.069 | **75%** | **75%** |

A 14× reduction, landing near the noise floor.

**⚠️ This used the TRUE shear from the manifest — an oracle. It is NOT a usable result yet.** At
inference we do not get the shear. Recorded here so the number is never quoted as an achievement
(R6); it is an upper bound that tells us what blind estimation is worth.

**Why it matters anyway.** It is the strongest confirmation yet of the project's thesis: the win
came from *inverting a known acquisition distortion*, not from a better matcher. It also explains
the baseline's pass-rate shape — flat 75% from 5 px down to 2 px, then collapsing to 40% at 1 px —
because nearly every correctly-located pair sits in a narrow band set by this one systematic offset.

**Next step (blocks Gate 4).** Estimate the shear blind. The reference is shear-free
(`image_reference` passes `shear_amplitude_px=0.0`) while the search is sheared, so the distortion
shows up as a difference in lattice basis vectors between the two — a shear tilts the vertical
bit-line direction by `atan(shear/1000)`. That is exactly step A5, "lattice as a ruler," and it is
now the highest-value remaining work.

**Caveat on feasibility.** For shear=1.5 px over 1000 rows the tilt is only 0.086°, against an FFT
angular resolution of roughly 0.057° at this image size. Measurable, but not comfortably — so this
needs a real measurement, not an assumption, and a fallback if the estimate is unreliable.

---

## ADR-0011 · 2026-08-11 · accepted · Negative results: stages that did not earn their place

Recorded per R9. Each was implemented, measured on 16–40 sponsor pairs, and kept out of the default
path. Reported in the ablation rather than quietly deleted.

| Stage | Effect | Why |
|---|---|---|
| Row destriping | mis-lock **18.8% → 31.2%** — actively harmful | Intended to remove charging streaks, which are constant along a row. But DRAM **word lines are horizontal**, so real signal is row-constant too, and subtracting the row median deletes it. Charging streaks are also disabled in this data, so it removes signal and buys nothing. **Keep, but only enable when streaks are actually present.** |
| Median filter | no measurable effect | `salt_pepper_prob=0` in this data — nothing to remove. Harmless; retain for robustness when impulse noise is present. |
| Generalized Anscombe (A1) | no change to the argmax | The transform is monotone, so it rescales scores without moving an integer peak. Its value should appear in *sub-pixel* refinement and in low-dose regimes, not in argmax accuracy. Needs re-testing after refinement works, on genuinely low-dose data. |
| Phase congruency (A2) | **100% mis-lock, median 324 px** — catastrophic | The implementation is wrong, not the idea. Disabled pending a fix or removal. Cited as broken rather than presented as an evaluated alternative. |
| PADM re-scoring (A7) | mis-lock 18.8% → 25% — currently harmful | The idea is sound and H7 confirms the fingerprint exists, but the current blend weight and residual bandwidth are untuned. Needs work before it can be claimed. |

**The honest summary at this point:** of the stages built so far, only sub-pixel refinement improved
anything (median 1.102 → 1.085, pass@1 40% → 45%), and the single largest effect came from a source
none of the planned stages addressed — the drift-frame offset in ADR-0010.

---

## ADR-0012 · 2026-08-12 · accepted · Only strictly-additive stages ship by default

**Decision.** A stage is enabled in the default pipeline only if it (a) improves results on splits
it was **not** tuned on, and (b) cannot make a correct result worse. PADM re-scoring fails both and
is disabled. Sub-pixel refinement and blind drift correction pass both and ship.

**Evidence.** Validated across three splits — the tuned split, a held-out seed, and a held-out
architecture:

| Configuration | verify (tuned) | held-out dram | held-out FinFET |
|---|---|---|---|
| baseline mis-lock | 25.0% | 20.0% | 30.0% |
| + top-K + PADM + centre | **20.0%** ✅ | **26.7%** ❌ | **43.3%** ❌ |
| + sub-pixel + drift | 25.0% | 20.0% | 30.0% |

**The structural principle, which is the durable part of this decision.** Sub-pixel refinement and
drift correction adjust a coordinate *after* a location has been chosen; they never touch candidate
selection. That makes them **strictly additive** — they cannot turn a correct pick into a wrong one,
and the mis-lock rate is provably identical to baseline on every split. PADM **re-ranks**, so a
mistuned scoring function actively destroys correct answers.

> **Refinement fails gracefully. Re-ranking fails destructively.**

That asymmetry is why refinement transfers across architectures without retuning and re-ranking did
not, and it is the rule we now apply to every future stage.

**What it cost and what it saved.** The earlier "20% mis-lock / 78% sub-pixel" headline was an
overfitting artefact and has been withdrawn; the honest mis-lock rate is baseline-level. But
removing PADM's FFT decompositions took runtime from 224 ms to **50 ms**, a 4.5× speedup that
directly helps the runtime half of the localization score.

**What would change our mind.** A re-ranker that demonstrates improvement on held-out architectures,
and that is gated to fall back to the argmax when confidence is low — so that its failure mode is
inaction rather than damage. That is now a hard requirement on the planned learned re-ranker, not a
nice-to-have.

**Process note.** This was caught only because held-out splits were generated *before* the result
was trusted. Single-split evaluation would have put 20% mis-lock and 78% sub-pixel into the deck,
and the sponsor's evaluation set would have quietly disagreed.

---

## ADR-0013 · 2026-08-12 · accepted · Treat the sponsor's DRAM presets as one architecture, not six

**Decision.** Report the sponsor's generator as providing **two** distinct architectures (dram,
finfet), not twelve presets. Do not claim robustness across DRAM presets.

**Why.** `dram_dense`, `dram_loose` and `dram_legacy` produce byte-identical images (md5-verified).
`generate_fine_canvas_zoned` passes only `preset["kind"]` to `generate_zone_canvas`, so in the
default zoned path every DRAM preset collapses to the same generator and the pitch, width and
contact-diameter values in `presets.py` are never read.

**Consequence.** Genuine variation in pitch, feature size and CD must come from our own generator.
A slide claiming "validated across six DRAM presets" would be false, and is now impossible to write
by accident.

---

# Hypothesis verification log (rule R3)

The facts in `CLAUDE.md` about the sponsor's generator were derived by **reading its source code**,
not by running it. Each is a hypothesis until confirmed on real generated pairs. **B owns this, Day 1,
before any algorithm work.** If one is refuted, say so immediately — the plan changes.

**Verified 2026-08-11** against **40 real pairs** from the sponsor's generator
(`dram_1x`, seed 20260811) by `scripts/verify_hypotheses.py`. Full evidence in
`results/hypotheses.md`.

| ID | Hypothesis | Status | Key evidence |
|---|---|---|---|
| H1 | Reference footprint in search image is exactly 100×100 px | ✅ CONFIRMED | `gt_box` is 100×100 for every pair; both images 1000×1000 |
| H2 | `gt = (x0/10 + 50, y0/10 + 50)`, GT on a 0.1 px grid | ✅ CONFIRMED | centre == box origin + 50 exactly; origin×10 integral to 1e-16 |
| H3 | Noise is Poisson (shot) then Gaussian (detector) | ✅ CONFIRMED | Var = 1.75·mean + 426 over flat windows — signal-dependent variance is the Poisson signature |
| H4a | `INTER_AREA` downscale is the correct forward operator | ✅ CONFIRMED | ZNCC at truth: mean 0.835, min 0.580; a local peak sits within 0.0 px of truth |
| H4b | Plain ZNCC argmax is defeated by periodic ambiguity | ✅ CONFIRMED | **10/40 (25%) mis-locate >5 px**; worst 271.7 px |
| H5 | Search is noisier / more degraded than the reference | ✅ CONFIRMED | dose 2000 vs 200; noise σ 10× higher |
| H6 | Mats/strips zoning with `boundary_bias=0.35` | ⚠️ NOT INDEPENDENTLY TESTED | asserted from source reading only; not load-bearing for the algorithm |
| H7 | Random-walk line placement → unique per-cell fingerprint | ✅ CONFIRMED | self-correlation margin to the best impostor: median 0.057, **min 0.0086** — positive, so disambiguation is possible |
| H8 | A mis-lock is a hard failure, not a near miss | ✅ CONFIRMED | 100% of rival peaks are >5 px away (median 45.5 px), yet the score margin is only 0.016 |
| H9 | Their generator has no rotation and no scale variation | ✅ CONFIRMED | no such manifest columns; ratio fixed at 10 by pixel sizes |
| H10 | Raster shear produces a systematic, correctable x bias | ✅ CONFIRMED (new) | dx mean −0.837 vs dy +0.073; dx vs gt_y **r = −0.861**, slope −0.00165 vs predicted −0.00150 |

### What this changes

**Nothing in the plan is refuted.** Three findings sharpen it:

1. **H4 was two claims, and separating them mattered.** The first version of the check asked "does
   `INTER_AREA` + argmax land within 5 px" and reported REFUTED — but that conflated *is the forward
   model right* (yes, emphatically) with *does argmax suffice* (no, and that is the entire point of
   the project). A test that bundles the thing you are validating with the thing you are trying to
   beat cannot distinguish them. Split into H4a and H4b.

2. **H10 is new and immediately actionable.** The baseline's ~1 px median error is dominated by a
   *systematic, physically-explained* bias, not by noise: the raster shear displaces each row
   horizontally by `shear·(r/999)`, so dx is biased while dy is not, and dx correlates with the
   template's y position at r = −0.861. This independently justifies **`MOTION_AFFINE` rather than
   `MOTION_EUCLIDEAN`** in step A9 — a Euclidean model cannot represent shear.

3. **The margins are now measured, not guessed.** The true location beats its best impostor by a
   median of 0.057 and a minimum of **0.0086** in self-correlation, and on the real ZNCC surface the
   winner-versus-rival margin is a median 0.016. Disambiguation is possible but the signal is thin —
   which is the quantitative case for scoring the aperiodic residual explicitly (A7) and for
   emitting a confidence rather than a bare coordinate (A8).

### The baseline floor (ablation row 1)

Measured on 40 sponsor pairs, `INTER_AREA` + `matchTemplate` argmax:

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **25%** (10/40) |
| Median error | 1.10 px |
| Max error | 271.71 px |
| Mean ZNCC at truth | 0.835 |

Note the median (1.10 px) is *not* the story — a quarter of the pairs are catastrophically wrong.
Any headline metric that averages over both regimes hides the failure mode the problem is about, so
report the mis-lock rate separately (R9).
