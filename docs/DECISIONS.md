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

## ADR-0014 · 2026-08-12 · MacBook Air M2 · accepted · The template builder is a continuous affine, not a resize

**Decision.** `build_template` box-integrates the reference over the detector footprint
(`area_kernel`, an exact box of arbitrary **real** width) and then samples it with a single affine
carrying both scale and rotation. `cv2.resize(INTER_AREA)` is gone from the matching path.

**Why.** `INTER_AREA` can only emit an integer output size, so the representable magnifications were
`1000/n` — 9.0090, 9.0909, 9.1743, … — steps of about **1%**. Our own measurement says a 1.3% scale
error drops the ZNCC peak from 0.856 to 0.262. The quantisation step was therefore as coarse as the
whole tolerance, which means **no pose search could ever have worked**: the grid it was searching did
not exist in the template builder. `INTER_AREA` also cannot express rotation, so rotation had to be a
second interpolation of an already-resampled image.

It is also the more honest statement of the thesis. The search image was formed by
*integrate-then-affine-sample*; the template is now built by exactly that operator, so "we invert the
microscope" is literal rather than decorative.

**Evidence it did not disturb the calibrated convention.** On the sponsor `verify` split the baseline
reproduces exactly (25.0% mis-lock, 1.102 px median, 40% pass@1px) and the shipped default gives
0.243 px against win-2's committed 0.238 px.

**What would change our mind.** Nothing short of a measured regression on the sponsor split; the old
path cannot represent the tested envelope, so it is not a fallback.

---

## ADR-0015 · 2026-08-12 · MacBook Air M2 · accepted · Pose is searched on a pyramid, not read off the lattice

**Decision.** The default pose method is `pyramid` — an exhaustive coarse search on a 4×-downsampled
level, then a full-resolution bracket, then a local polish. The two spectral estimators stay in the
tree, off by default, as measured negative results (R9).

**Why, and this one hurt.** "The lattice is a ruler" is the idea the project is named for, and it
lost on measurement:

| Method | scale median err | rotation median err |
|---|---|---|
| Reciprocal-lattice peak voting | 1.21% | 0.24° |
| Log-polar Fourier–Mellin | 3.49% (+2.07% bias) | 0.13° |
| **Coarse pyramid search** | **0.72%** (+0.09% bias) | 0.43° |

The cause is an information limit, not an implementation flaw. `dram_legacy` has a 240 nm bit-line
pitch, so a 1000 nm reference contains **4.2 periods**, and a frequency estimated from four periods
cannot be pinned to the 0.5% correlation demands. **The lattice is a fine ruler but a short one.**

The pyramid wins for a reason worth stating: a scale error costs misalignment *proportional to
template size*, so downsampling 4× (100 px → 25 px template) widens the basin from ~1% to ~4%. The
whole 9:1–11:1 envelope is then ~11 hypotheses at 1/16 the cost each.

**What would change our mind.** A reference that spans many more lattice periods — a finer pitch or a
larger reference — would move the spectral estimators back into contention, and they are cheaper.
Re-measure before switching; do not assume.

---

## ADR-0016 · 2026-08-12 · MacBook Air M2 · accepted · Our ground truth was half a pixel off; fixed at the source

**Finding.** With the true pose supplied from the manifest, the residual on 40 dev pairs was
`dy = +0.503 px, std 0.035` — far too consistent to be anything but a convention.

**Cause.** `warpAffine` samples at **pixel centres**, so the analytic inverse in
`canvas_to_search_coords` lands in pixel-*index* space. The problem's convention, verified as H2
against the sponsor's manifests, is `origin + size/2` — half a pixel further. Our GT therefore sat
half a pixel from the sponsor's for the same physical situation.

**Why it mattered more than it looks.** The sub-pixel threshold *is* 0.5 px. This alone would have
made every sub-pixel claim on our own benchmark fail while the sponsor's data passed — and the
natural reaction would have been to blame the matcher and "fix" it into being genuinely wrong.

**What would change our mind.** If the organizers publish an evaluation utility using pixel-centre
coordinates, this flips — and so does H2. The `+0.5` is in one place for exactly that reason.

---

## ADR-0017 · 2026-08-12 · MacBook Air M2 · accepted · The drift estimator must be told the rotation

**Finding.** `dx = −9.5 × rotation_deg`, a clean straight line through the failures, up to 19 px on a
2° pair.

**Cause.** A rotation and a drifting raster produce the **same** row-to-row displacement: a tilt of ρ
moves content sideways by `gap·tan(ρ)` over the same row separation drift does. They are
indistinguishable to that measurement. The estimator reported the tilt as drift and then "corrected"
a distortion that was never there.

**Fix.** `estimate_shear` takes `rotation_deg` and subtracts the geometric term, leaving genuine
drift. `localize` passes the pose of the chosen candidate.

**Why it went unnoticed until now.** The sponsor's generator produces no rotation (H9), so their data
*structurally cannot* exhibit this. It is the clearest argument in the project for owning a
generator: cross-validating on someone else's data proves you did not overfit to yours, but it
cannot test an axis their data does not contain.

---

## ADR-0018 · 2026-08-12 · MacBook Air M2 · accepted · Mats share a pitch; only their roughness differs

**Decision.** `build_canvas(vary_preset_per_mat=...)` defaults to **off**.

**Why.** It randomised each mat's nominal **pitch** by ±6%. A cell array's pitch is a design rule
fixed by lithography and is identical across every mat on a die — mats differ in line-edge roughness
and local CD, which we already model per instance. A process engineer would spot it immediately, and
realism is explicitly graded in the 30% bucket.

It was also measurably harmful: with every mat on its own pitch there is no single pitch for the
search image to present, which pushed the lattice-based scale estimate from 0.69% error to **4.1%**.
The motive ("diversity") was reasonable and the mechanism was wrong — diversity belongs at the
per-*sample* level, where preset choice already provides it.

**What would change our mind.** Modelling a deliberate multi-die or multi-product field of view,
where genuinely different arrays are in frame. That is a different scenario and should be a separate
flag, not the default.

---

## ADR-0026 · 2026-08-12 · MacBook Air M2 · accepted · Manifest paths are normalised across platforms

*(Renumbered 14 Aug. This was written as a second ADR-0019, colliding with the per-candidate refit
decision below. Kept in chronological position; this entry was renumbered rather than the refit one
because every inbound reference — in `localize.py`, `match.py`, `PROGRESS.md` and ADR-0025 — means
the refit. Duplicate identifiers in a decision log are a credibility problem even when nothing
depends on them.)*

**Decision.** `resolve_manifest_path` retries with `\` → `/` as a **fallback** when the recorded path
does not resolve as written.

**Why.** A manifest written on Windows records `data\verify\ref\0.png`. POSIX treats a backslash as
an ordinary filename character, so on macOS or Linux that path does not exist and the entire batch
fails — which is exactly what happened to us, with two of the team on Windows and one on macOS. The
evaluator's manifest may equally be Windows-authored.

**Why a fallback and not a rewrite.** On POSIX a backslash can legitimately be part of a filename, so
a real file must always win over a guessed separator.

---

## ADR-0019 · 2026-08-12 · accepted · Re-score each candidate at its own pose (per-candidate refit)

**Decision.** Ship per-candidate pose refit: `top_k=10`, `candidate_refit=True`, `refit_steps=2`.

**Why, from the measurement rather than from intuition.** On an information argument ZNCC should
already separate the true location from its lattice impostors easily — margin ~0.016 against
sampling noise ~0.002 on a 100×100 correlation, a signal-to-noise ratio near 8. That predicts almost
no mis-locks; we measured 28%. **The noise that decides the ranking is therefore not photon noise
but model mismatch**, which is what the maximum-likelihood re-ranker had already concluded from the
other side (ADR-0018). The global pose is a compromise fitted across the whole field while drift
accumulates over the scan, so the locally-best pose differs per candidate and a shared pose
handicaps them unequally.

**Result** — improves every split, most on the held-out architecture:

| split | before | after |
|---|---|---|
| dev (tuning) | 20.0% | **12.5%** |
| bench | 33.3% | **26.7%** |
| holdout FinFET | 33.3% | **20.0%** |
| all 100 pairs | 28.0% | **19.0%** |

**Why this one generalised when three re-rankers did not.** It is re-*scoring*, not re-*ranking*: no
new criterion, no blend weight, still ZNCC — just measured at each candidate's own optimum instead of
a compromise. It removes an unequal handicap rather than introducing a preference, which puts it on
the safe side of ADR-0012's rule. Consistent with that, the biggest gain landed on the architecture
it was never tuned on.

**Cost.** 238 ms → 316 ms per pair. Above our own 300 ms aspiration by 5%; we chose the 9 points of
mis-lock. `refit_steps=2` is deliberate — identical accuracy to 3 at 316 ms against 433 ms.

**What would change our mind.** If a future stage removes the mismatch globally (a proper
per-candidate affine model, or drift correction applied before scoring rather than after), the refit
would become redundant and should be re-measured rather than kept out of habit.

---

## ADR-0020 · 2026-08-12 · accepted · Rotation sign convention is `+rotation_deg`, and it is tested

**Decision.** `build_template(reference, scale, rotation)` takes the rotation **with the same sign**
as the manifest's `rotation_deg`. Pinned by a test.

**Why this needed an ADR.** It was `−rotation_deg` before the forward operator was rewritten, and it
flipped with the rewrite. Building an oracle-pose diagnostic from the remembered convention produced
the impossible result that a *perfect* pose was worse than a searched one (60% vs 33.3% mis-lock) —
and that nonsense was the only reason the error was caught rather than silently believed.

Settled by measuring peak ZNCC at `+R` against `−R` on eight pairs: `+R` won on seven, and on the
eighth the true rotation was −0.02° so the two are indistinguishable.

**The general lesson**, which is rule R7 stated concretely: a convention that was verified once is
not verified forever. It is a property of the code as it stands, and it must be re-measured whenever
the code it describes is rewritten.

---

## ADR-0021 · 2026-08-12 · accepted · Centre rule: fix its threshold, implement it, default it off

**Decision.** Keep the problem statement's closest-to-centre rule implemented, tested and reachable
via `centre_rule=True`, with a statistically derived tie threshold. Do **not** enable it by default.

**The threshold was wrong and is now correct.** `tau` was `0.25 × std(candidate scores)`. The
candidate set spans the whole search image, so that spread gives tau ≈ 0.037 — more than twice the
0.016 median winner-versus-rival margin. Clearly-worse candidates were being called "tied" and then
decided on centre proximity, which nearly doubled mis-lock (23.3% → 43.3%). `tau` is now the
sampling standard error of a correlation coefficient, `(1−ρ²)/√N`, at two sigma. Nothing is tuned:
N is the template footprint and ρ the winning score.

**Why it is still off by default.** Even corrected it costs accuracy — sponsor 25.0% → 35.0%, and
24% → 28% across all three splits. That is not a defect in the rule. **It encodes a deployment
prior**: a tool that has drifted lands near the site it meant to revisit, so among equally-scoring
candidates the central one is the likely one. Both benchmarks sample target positions uniformly —
measured median distance from the search centre is 373 / 335 / 347 px against the 358 px a uniform
draw predicts. The assumption the rule rests on is absent from the test data, so when it fires it is
a coin flip that can only lose.

**Compliance position.** The checklist asks that the rule be implemented; it is, correctly, and the
reason it is not the default is measured and documented rather than silent. If the evaluation data
reflects the deployment scenario — targets near the centre because the tool only drifted slightly —
enabling it is a one-line change and should pay.

**Process note.** An earlier round tested this on bench/FinFET/dev only and concluded it was
neutral. Adding the sponsor split reversed the conclusion. **A stage must be checked on every split,
not on a convenient subset** — the same lesson as ADR-0012, learned again.

---

## ADR-0022 · 2026-08-12 · accepted · The drift gap is derived from the measured rotation

**Decision.** `DEFAULT_GAP` drops from 100 to 40, and the operating value is computed per pair from
the measured rotation via `gap_for_rotation()`.

**The bug this fixes.** With `gap=100` and `max_lag=3`, a 2° rotation displaces content by
`100·tan(2°) = 3.49 px` per row-pair — outside the ±3 lag search entirely. The correlation peak
clipped at the edge of its own window and the estimate saturated. Measured standard deviation of the
shear estimate was **17.75 px on bench** (truth 1.5), and error above 1° of rotation was six times
that below 0.5°. The two-axis rotation cancellation was not "exact" as documented, because its
inputs were clipped before it ran.

**The constraint, which is derived and not tuned.**

```
gap·tan(ρ) + |drift|  <  max_lag  <  lattice_pitch / 2
```

Below the lower bound the measurement saturates; above the upper bound the correlation locks onto
the next lattice line. With a ~6.4 px word-line pitch the upper bound is ~3.2, so at gap=100 the
lower bound (5) exceeds it — **the old configuration was infeasible, not merely suboptimal.** A
sweep confirms both failure modes: gap=100/lag=3 gives sd 13.3 on bench, and widening to lag=5
gives sd 16.5–19.2 by aliasing.

**Why adaptive rather than a fixed 40.** A long baseline divides the estimate by a larger number and
so amplifies per-pair noise less; it is better whenever the field is not tilted. Solving the
constraint for the measured rotation serves both regimes, and returns **43 at 2°** — where the
empirical sweep independently put the optimum (40).

**Result.** Total mis-lock 24/100 → 22/100; sub-pixel pass rate across all splits 50 → 65; bench
mis-lock 30.0% → 23.3%; FinFET pass@0.5px 33% → 63%.

**Fitted vs derived, chosen deliberately.** A fixed gap=40 scores one pair better on mis-lock
(21/100) and five pairs worse on sub-pixel. We take the derived rule: it wins where it matters more,
and it has a reason to hold at rotation ranges we have not tested, which a fitted constant does not.

---

## ADR-0023 · 2026-08-12 · rejected · Photometrically-invariant matching features

**Decision.** Do not use lattice-phase fingerprints or gradient-orientation correlation for ranking.

**The hypothesis.** The limiting noise on ranking is model mismatch, which is photometric (PSF,
apodisation, gain), while every scorer we use compares amplitudes. So compare something invariant to
photometry: the analytic phase of the lattice carrier (which measures line displacement directly),
or the unit gradient vector field (direction without magnitude).

**Measured — all worse than the argmax they replaced:**

| method | dev | bench | FinFET |
|---|---|---|---|
| argmax | 20.0% | 26.7% | 33.3% |
| lattice-phase fingerprint | 32.5% | 26.7% | 43.3% |
| gradient orientation | 27.5% | 36.7% | 40.0% |
| orientation, magnitude-weighted | 22.5% | 46.7% | 50.0% |

**Why the premise was wrong, which is the valuable part.** The stage that did fix ranking was a
**pose refit** — a geometric correction. So the mismatch limiting us is **geometric**, while the
evidence distinguishing candidates is **photometric**. Photometric invariance therefore discards the
evidence and leaves the mismatch in place — exactly backwards.

Stated as a rule: **the mismatch is geometric, the evidence is photometric.** That explains the
refit's success rather than merely recording it, and it correctly predicted where the next gain
would come from — removing more geometric mismatch (ADR-0022), not inventing features.

---

## ADR-0024 · 2026-08-12 · accepted · Stop adding re-ranking criteria; the evidence is conclusive

**Decision.** No further candidate re-ranking criteria will be attempted. The default pipeline keeps
per-candidate pose refit and nothing else in the selection stage.

**The evidence.** Six independent attempts to re-rank candidates by a *new* criterion, across three
splits and two architectures:

| Attempt | Result |
|---|---|
| PADM residual scoring | overfit — gained on tuned split, lost both held-out |
| Coarse-level consensus | harmful (62.5% on sponsor) |
| Maximum-likelihood, Poisson–Gaussian | no gain — mismatch dominates photon noise |
| Refit-*gain* ranking | catastrophic (80–92%) |
| Lattice-phase / gradient-orientation features | harmful (up to 50%) |
| Residual tie-break, statistically gated | harmful (20.0% → 25.0% held-out) |
| **Per-candidate pose refit** *(same criterion, better geometry)* | **28.0% → 19.0%, improves every split** |

> **Every attempt to re-rank by a NEW criterion failed. The only stage that worked re-scores by the
> SAME criterion at a better geometry.**

**Why this is a decision and not a pause.** Six failures and one success is no longer a run of bad
luck; it is the shape of the problem. At dose 200 and 10 nm/px the aperiodic fingerprint carries too
little information to support any hand-designed discriminator we have found, while reducing geometric
mismatch pays every time. Continuing to guess at criteria in the face of that evidence would be poor
judgement rather than persistence, and each attempt costs a full three-split validation.

**What would change our mind.** Evidence that the fingerprint is recoverable at all — for example a
component that reduces geometric mismatch further (a richer constrained local deformation, or a
learned model trained to *reduce mismatch* rather than to *score similarity*) and thereby raises the
margin the discriminator has to work with. The direction is more geometry, not more scoring.

**A gate calibrated before a stage runs is not calibrated after it.** The residual tie-break used the
tie threshold derived in ADR-0021, and it fired on 38 of 40 sponsor pairs — because the refit
compresses the score distribution, which is exactly its purpose. Any future gate placed downstream of
the refit must be re-derived against post-refit scores. This also applies to the centre rule, which
shares that threshold.

---

## ADR-0025 · 2026-08-13 · accepted · The default refit is wide, densely sampled, and screened

**Decision.** The shipped configuration changes from a narrow refit over all candidates to a **wide,
densely-sampled refit over the top 10 candidates after a cheap narrow screen**:

```python
refit_steps=5, refit_scale_span=0.03, refit_rotation_span=1.5,
refit_screen_steps=2, refit_screen_top_n=10
```

**Measured**, all four splits, `dev` used only for tuning (R5):

| config | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|
| narrow only (ADR-0019, previously shipped) | 12.5% | 25.0% | 23.3% | 16.7% | 22.0% | 296 ms |
| wide dense, unscreened (ADR-0024 era) | 10.0% | 22.5% | 20.0% | 16.7% | 20.0% | 601 ms |
| **wide dense + screen** | 12.5% | **22.5%** | **16.7%** | **13.3%** | **18.0%** | **427 ms** |

**Why this is not a new criterion, and therefore not a violation of ADR-0024.** The screen ranks by
ZNCC and the dense pass re-scores by ZNCC. It is the same criterion evaluated at two resolutions —
the *same* shape as the one selection stage that has ever worked here (ADR-0019). Nothing is ranked
by anything that was not already ranking it.

**Why it is more accurate than the dense grid it replaces.** ⚠️ *This paragraph originally claimed
the gain came from the narrow pass re-centring each candidate's pose before the wide grid is laid
around it. That explanation was plausible, was proposed independently by an external reviewer, and
is **wrong** — it was measured on 14 Aug and refuted. The corrected account:*

Factorising the screen into its two effects (FINDINGS §23f):

| variant | prunes | re-scores first | held-out |
|---|---|---|---|
| A — no screen | – | – | 20.0% |
| B — **shipped** | ✓ | ✓ | **18.0%** |
| C — screen runs, nothing pruned | – | ✓ | 20.0% |
| D — truncate to 10 on unrefit scores | ✓ | – | 24.0% |

**Neither half works alone.** Re-scoring without pruning (C) is worth exactly nothing; pruning
without re-scoring first (D) is worse than no screen at all. The mechanism is therefore not "better
initialisation" but a **bound on how much geometric freedom the candidate field collectively
receives**, made safe by ranking the field first:

> A wide pose search helps the true candidate and helps impostors *more* — the §15d asymmetry, which
> sank refit-*gain* ranking at 80–92%. Handing ±3% and ±1.5° to 60 candidates gives 59 impostors 25
> chances each to find a flattering pose. The narrow refit is what makes a top-10 cut trustworthy
> enough to take before that exposure is granted.

This is consistent with, not contrary to, §22: dense sampling is still irreplaceable — it is just
dangerous to hand out widely. And it re-derives ADR-0024's rule from a third direction.

**Why `top_n=10` and not 6**, when both measured identically on all 140 pairs and 6 is 41 ms faster
and meets a pre-registered "<400 ms" bar: after the screen, the true candidate lies within the top 10
on **90.0%** of sponsor pairs but only **80.0%** of the top 6. The tie was broken on retained recall
rather than on today's tie, because recall is what protects against evaluation data that differs from
ours, and the sponsor split is the one the problem statement scores. The bar was missed deliberately
and the reason recorded, rather than the bar being moved.

**What made it affordable.** Profiling, not cleverness. The dense grid's cost was assumed to be
template construction; it is 6%. It is correlation count: candidates arrive `top_k`-per-*pose*, so 60
of them over a 5×5 grid is 1500 correlations per pair. Hoisting box-integration out of the rotation
loop (bit-identical, verified by diffing all 100 held-out predictions) gave a real 1.35× and was not
enough on its own. See FINDINGS §23.

**Consequence for ADR-0024's frontier.** §21d's "2 points of accuracy costs 3× runtime" was an
artefact of this implementation, exactly as §22's correction hedged. It is now 18.0% at 1.4×.

---

## ADR-0027 · 2026-08-14 · accepted · The median filter ships, having been rejected in the wrong regime

**Decision.** `median_filter=True` in the shipped configuration.

**Why it was off.** FINDINGS §3 measured it as "no effect" and it stayed off for three days. That
measurement was taken on our nominal splits, where `salt_pepper_prob = 0`. **A stage that removes
impulse noise was evaluated only on data containing none**, so the best it could have scored was
"no effect" — which is exactly what it scored, and the number was treated as settled.

**Measured, with the regime present** (validation seeds, disjoint from every reporting split):

| config | nominal (control) | salt-and-pepper | charging streaks |
|---|---|---|---|
| off (previous default) | 20.0% | 16.7% | 36.7% |
| **on** | **20.0%** | **6.7%** | 33.3% |

And paired on the 100 held-out pairs: **breaks 0, fixes 2**, held-out mis-lock 18.0% → 16.0%,
runtime delta **−3 ms** measured interleaved, i.e. free.

**Why this is not tuning on the benchmark (R5).** The decision rests on the impulse-noise column,
measured on validation-only seeds, plus a check that it regresses nothing. The 2-pair held-out gain
is inside the sampling noise established in ADR-0029 and is reported, not relied on. Had it broken
even one held-out pair the trade would have been arguable; breaking zero of 100 makes it not.

**Why it is worth taking for two pairs.** It is free, it is provably harmless here, and the spec
names salt-and-pepper explicitly among possible degradations while stating that the released test
set uses parameters we have not seen. A stage worth 10 points in a regime the evaluator may include
and 0 points otherwise is a good trade at zero cost.

**Row destriping stays off**, re-tested in the same way: catastrophic on clean data (20.0% → 36.7%,
confirming ADR-0011) and worth one pair on the streaks it was written for. It removes horizontal
word lines along with the streaks.

**What would change our mind.** Evidence that the evaluation data contains no impulse noise at all,
which would make this a free no-op rather than a free hedge — in which case it may as well stay,
since it costs nothing either way.

---

## ADR-0028 · 2026-08-14 · accepted · Ground truth must pass through every geometric stage, not most of them

**Decision.** `pipeline.py` maps ground truth through barrel distortion via
`imaging.barrel_map_point` before recording it. Covered by a hand-derived asymmetric test.

**The bug.** `barrel_distortion` is written the way `cv2.remap` requires: for each **output** pixel
it names the **source** pixel to sample. That is the inverse of the path a feature travels. Ground
truth was computed through scale and rotation and stopped there, because barrel is applied later
inside `detector_chain`. So the label described the pre-distortion frame while the saved image showed
the distorted one.

**How it surfaced.** Not by inspection — by the robustness sweep returning 53.3% mis-lock at
`k = 0.05` with a **median error of 9.09 px**. That median is the tell: a real mis-lock is tens to
hundreds of pixels off, so 9 px is a systematic offset, not a wrong lattice repeat. One measurement
confirmed it: the residual pointed radially **inward on 97% of pairs** and fitted `a·r²` with
**R² = 0.811**. Inward, radial and quadratic is barrel's own signature.

**Why it matters beyond the fix.** Reported unexamined, that row would have appeared in our own
submission as a measured weakness of the localizer. It was a mislabelled dataset. Anyone using our
generator for distortion robustness would have inherited it silently, since nothing else in the
pipeline cross-checks the label against the image.

**Blast radius: none.** `barrel_distortion_k` defaults to 0, so `bench`, `dev` and `holdout_finfet`
are unaffected and no reported number moves.

**The rule this generalises to.** Ground truth is not a by-product of the geometry; it is a *parallel
render* of it, and every stage that moves pixels must move the label. The reference/search
acquisitions already share this property for scale, rotation and drift — barrel was the one stage
applied after the coordinate was frozen, which is precisely why nobody noticed.

---

## ADR-0029 · 2026-08-14 · accepted · Report paired tests and Wilson intervals, not bare proportions

**Decision.** `scripts/significance.py` generates confidence intervals and a paired McNemar test into
`results/significance.csv`. Differences of 2–4 points between splits are reported as directional, not
as resolved.

**What forced it.** The stress sweep accidentally ran the nominal configuration twice — `s02` and
`s06` share an identical generator parameter set, verified by diffing every manifest column, and
differ only in seed. They measured **20.0%** and **26.7%** (and 20.0% vs 33.3% before ADR-0027).
Two samples of the same distribution, n = 30, six to thirteen points apart. Every "X is 3 points
better than Y" in this project needed re-reading against that.

**The two questions are different, and conflating them cut against us.** Marginal intervals are wide
(aggregate 18.0%, 95% CI [11.7%, 26.7%]). But our own configuration comparisons run on the *same
pairs*, where 78 of 100 are correct under both — so the paired test is far more powerful:

| screened-wide vs narrow, same 100 pairs | |
|---|---|
| narrow correct, screened wrong (b) | **0** |
| screened correct, narrow wrong (c) | **4** |
| exact McNemar two-sided | **p = 0.125** |

**Strictly dominant, and not significant at 0.05.** Both halves get reported. Four discordant pairs
all falling one way is the best available outcome at this sample size and still only reaches 0.125;
believing the mechanism does not change that arithmetic.

**What this does not undermine.** 76.7% → 16.7% on bench and 90.0% → 10.0% on held-out FinFET are
not four-point differences and are not in doubt.

---

## ADR-0030 · 2026-08-15 · accepted · Every analysis claim needs a committed script, not a print-out

**Decision.** An analysis result may not enter `FINDINGS.md`, `STATE.md`, `HANDOFF.md`, `README.md`
or the deck unless a committed script under `scripts/` regenerates it into `results/`. Retroactively
applied: FINDINGS §35b, §35c and §36 were promoted to `scripts/pose_ceiling.py`, and the retraction
this forced is FINDINGS §37.

**What forced it.** §35 was the submission's headline argument — *at the generator's exact pose the
true site correlates 0.065 worse than the impostor, and the refit recovers 89% of that*. It was
measured once in a scratchpad file, printed to a terminal, and copied by hand into four documents.
The commit message says it was "promoted to `scripts/oracle_ceiling.py`", but only §35a actually
was; the scratchpad file was later overwritten. Writing the rest down properly re-measured it:

| | published | reimplementation |
|---|---|---|
| ZNCC at the **true** location | 0.7661 | **0.7661** ✅ |
| deficit **after** the refit | +0.0072 | **+0.0072** ✅ |
| micro-warp differential (§36b) | −0.0004, 4/8 | **−0.0004, 4/8** ✅ |
| ZNCC at the **winning** location | 0.8615 | **0.7696** ❌ |
| truth out-correlates the winner | 2/15, p = 0.007 | **7/15, p = 1.000** ❌ |
| deficit at the **fixed** pose | +0.0654 | **+0.0114** ❌ |

Every truth-side quantity reproduced to the digit; no winner-side quantity did. The cause is a
single methodological error: **the "winner" score was the maximum of the correlation surface, not
the score at the location the pipeline chose.** A maximum over ~810,000 positions is selected
*because* it is the largest, so comparing it against a value at one nominated point is
upward-biased by construction — it cannot come out any other way, and what it actually reports is
that the argmax is not at the truth, which is §35a.

**Why neither existing rule caught it.** R2 fails the build on any deck number not present in
`results/` — but these numbers were never on a slide. R8's red-team pass re-derived the accuracy
numbers, all of which `evaluate.py` generates — but not the interpretive measurement the argument
rested on, precisely because that one had no script. The gap was exactly the class of claim that is
most load-bearing and least mechanised.

**Consequence for what may be claimed.** The corrected result is a statement about *margin*, not
about direction: at the exact pose the truth (0.7661) and its impostor (0.7696) are statistically
indistinguishable, and the paired deficit is +0.0114, of which the refit closes about a third. This
fits the rest of the evidence better than the retracted version did — six re-ranking criteria failed
because they were resolving a margin of about 0.01, which is a measurement rather than an
impossibility claim. Withdrawn with it: "these were never selection errors", "no re-ranker could
ever reach them", "geometry recovers 89%", and §36's "every degree of freedom helps the wrong
candidate, monotonically" (§36c's sign reverses under reimplementation; §36a and §36b stand).

**Nothing shipped changed.** Accuracy, runtime, configuration, ablation and packaging are untouched:
20.0 / 16.7 / 10.0, aggregate 16.0%.

**The general rule, which is the point.** *A result with no script is not a result.* The cost of
mechanising an analysis is minutes; the cost of defending a retracted headline in front of a panel
is the credibility of everything next to it.

---

## ADR-0031 · 2026-08-15 · accepted · The forward model is closed: fair corrections cannot select

**Decision.** No further work on the acquisition forward model. `src/driftlock/scanfield.py` is kept,
tested and **unreferenced by the pipeline** — the measurement is the deliverable, not the stage.

**What forced it.** An external review proposed the one architecture never tried, and proposed it for
a good reason: every deformation experiment so far estimated a correction from each *candidate's own
patch*, and a candidate allowed to choose its own geometry is being handed freedom that flows to
whoever has more mismatch to absorb. The alternative is to measure the scanner **once, from the whole
search image, before any candidate exists**.

The physics supported it. The generator applies `shear·y/(H−1) + jitter_y`; across a 100 px footprint
the 1.5 px shear contributes 0.15 px and its linear part is already removed, while the 0.5 px jitter
is **white in y** and unreachable by any smooth model. The reference's own jitter is 0.05 px after
the ↓10. So the search image's per-row jitter was the largest uncorrected geometric error in the
pipeline, and correcting it raised ZNCC at the true site by **+0.0297** — nearly 3× the +0.0114
margin (ADR-0030). It should have been decisive.

| ZNCC lift from the global correction, 27 dev pairs | |
|---|---|
| at the **true** location | **+0.0297** |
| at the **impostor** location | **+0.0301** |
| **differential** | **−0.0003**, truth ahead in 8/27 |

> **The impostor is a real lattice site imaged through the same scanner, so removing the scanner's
> jitter sharpens it by exactly as much. A global correction is fair by construction — and being
> fair is precisely why it cannot break a tie.**

**Why this closes the whole direction rather than one stage.** There is no third option: a
correction either privileges a candidate or it does not. Unfair freedom flows to the wrong candidate
(§15d at 80–92% mis-lock, §23f, §36b); fair improvement flows to both (§38b). Four independent
additions to the forward model now sit at the fourth decimal — PSF blur +0.0000, micro-warp −0.0004,
candidate-local jitter (two implementations, opposite signs), global scan field −0.0003 — against a
margin of 0.0114.

**It also retires §36c.** The +0.0378 and −0.0310 that disagreed about sign were never measuring
physics; each was measuring how much unfairness its own estimator handed each candidate. The
physical version of that correction has a differential of −0.0003.

**Judged in the regime it targets**, per ADR-0027, across a 6× range:

| jitter σ | base | with calibration | applied |
|---|---|---|---|
| 0.5 px (all reporting splits) | 12.5% | **15.0%** | 27/40 |
| 1.5 px | 25.0% | 25.0% | **0/24** |
| 3.0 px | 63.3% | 63.3% | **0/30** |

Above nominal the gates decline every pair, and structurally so: a per-row lag search must stay
below half the lattice period (~4.8 px at the 96 nm bit-line pitch, 10:1), so **the correctable
jitter range is bounded by the very periodicity that makes localization hard**. The stage fires only
where the jitter is too small to matter. That is not ADR-0027's mistake repeated — it is three
regimes with the same answer.

**Two things worth keeping from the attempt.** Correcting the image *destroys* the drift estimator,
which works precisely because jitter is zero-median noise it can average away — shear estimates went
to −3.9 and +17.0 against a true 1.50 (§38c). And scan jitter turns out to be the harshest
robustness axis measured, 63.3% at σ = 3.0, now recorded in the envelope.

---

## ADR-0032 · 2026-08-15 · accepted · Read the pose grid as evidence, not as a maximum

**Decision.** `pose_evidence_beta = 5.0` ships. After the refit, candidates are ordered by
`(1/β)·log mean exp(β·s)` over their own pose grid instead of by the grid's maximum. The maximum is
the `β → ∞` limit of the same expression, so the previous behaviour is a special case rather than a
different rule.

**Why this does not contradict ADR-0024.** That ADR bans ranking by a *new criterion* — six of them
failed. This adds no criterion: it is the same ZNCC, on the same grid, already computed by the
refit, summarised differently. Nothing new is measured and nothing is weighted against anything
else.

**What forced it.** §23f measured that widening the pose bracket for the whole candidate field is
*worse* than widening it for ten survivors — a wide search helps impostors more. That is a
multiple-comparisons effect: each candidate gets ~25 attempts at a flattering pose, and a candidate
whose pose surface is rough has more chance of getting lucky than one whose surface is flat and
genuinely high. The maximum of 25 draws is therefore an upward-biased estimate of quality, with the
bias growing in the roughness of the surface.

| | pose grid | max |
|---|---|---|
| truth | 0.762 0.768 0.766 0.764 0.765 | 0.768 — consistently good |
| impostor | 0.751 0.752 **0.769** 0.753 0.750 | 0.769 — one lucky sample |

**Measured, paired, on every split we have** (β chosen on `dev` alone and then frozen):

| split | n | shipped | + pose evidence | fixed | broke |
|---|---|---|---|---|---|
| dev *(tuning)* | 40 | 12.5% | 7.5% | +2 | 0 |
| dev2 | 160 | 11.2% | **6.9%** | +7 | 0 |
| sponsor | 40 | 20.0% | **5.0%** | +6 | 0 |
| bench | 30 | 16.7% | 23.3% | +1 | **3** |
| held-out FinFET | 30 | 10.0% | **6.7%** | +1 | 0 |
| **total** | **300** | | | **+17** | **3** |

**Exact McNemar over 300 paired pairs: p = 0.0026.** Reporting aggregate 16.0% → **11.0%**.

**And it is free.** The grid is already computed by the refit, so this re-reads numbers rather than
adding correlations — there is no runtime cost to weigh against the accuracy.

**The honest negative.** `bench` regresses, 16.7% → 23.3%, +1/−3. It is reported in the ablation and
in the deck rather than smoothed over. Two things bound how much weight it should carry: it is 3
discordant pairs out of 30, and ADR-0029 measured two *identically-parameterised* splits at 20.0%
and 26.7% — a 6.7-point swing from seed alone. bench is also not distinguished from FinFET by
generator or envelope, and FinFET improved.

**What is not claimed.** The mechanism is not established. The obvious hypothesis — that the sponsor
split gains because its pose is fixed at 10:1/0° (H9), so averaging the grid is free there — was
tested within `bench`+`FinFET` by pose offset and **refuted**: near-nominal 3→4, far-from-nominal
4→4. The effect, its size and its sign are measured on 300 paired pairs; the reason is not.

**A defect this exposed, worth its own line.** The first implementation made things dramatically
worse (14.4 px → 57.6 px) because `refit_candidates` merges screened-out candidates back in, and
*their* grids come from the 2×2 narrow screen rather than the 5×5 wide pass. A narrow grid is flat
and high by construction, so its log-sum-exp sits near its maximum while a wide grid averages in
poses that are genuinely wrong — ranking them together promotes exactly the candidates the screen
rejected. **A statistic is only comparable over the same support.** The maximum happens to be immune
to this, which is why the defect stayed invisible until the summary changed.

---

## ADR-0035 · 2026-08-15 · accepted · The lattice residual proposes candidates, and only proposes

**Decision.** `proposal_channels = "residual"`, `proposal_top_k = 3`. A second representation — the
search image minus its own lattice-periodic prediction — proposes candidate *locations*. Their
scores never enter any comparison; the existing ZNCC and the existing refit re-score every candidate
on the original intensity image.

**What forced it.** After ADR-0034 the decomposition was 3 `absent` / 0 `screened` / 5 `outscored`.
`absent` is the only bucket no selection change can reach, and it had not moved through a single
change made in this project, because nothing built so far touched candidate generation.

**Diagnose before building.** `scripts/proposal_forensics.py` asked the cheap question first: scored
at the generator's *exact* pose, does any representation have a peak near the truth? All three do,
and no single one sees more than two. That is what justified a union rather than a replacement.

**Then the per-channel ablation overturned the design.** Measured end to end, separately:

| channel, alone | sponsor | bench | FinFET | total |
|---|---|---|---|---|
| off | 0.0% | 20.0% | 6.7% | **8.0%** |
| variance | 0.0% | 20.0% | 6.7% | **8.0%** |
| **residual** | 0.0% | **16.7%** | **3.3%** | **6.0%** |
| edge | 0.0% | 20.0% | 6.7% | **8.0%** |
| variance + residual | 0.0% | 16.7% | 3.3% | 6.0% |

**The residual carries all of it; variance and edge are pure cost.** Without this ablation the
shipped configuration would have carried two channels that buy nothing — the union sweep alone could
never have shown that.

**And oracle visibility did not predict which channel to ship.** The forensics said `bench 4` was
found by *variance* and that the residual could not see it. End to end the opposite holds. The
forensic measures the *exact* pose; the pipeline searches an *estimated* one, and which
representation survives that gap is not predictable from the oracle. **The oracle forensic is a
screening tool — "is the information present anywhere?" — not a design tool.**

**Evidence, paired, k chosen on the tuning family:**

| split | n | shipped | + residual | |
|---|---|---|---|---|
| dev | 40 | 5.0% | 5.0% | +0/−0 |
| dev2 | 160 | 6.9% | **5.6%** | +2/−0 |
| sponsor | 40 | 0.0% | 0.0% | +0/−0 |
| bench | 30 | 20.0% | **16.7%** | +1/−0 |
| FinFET | 30 | 6.7% | **3.3%** | +1/−0 |
| **total** | **300** | | | **+4 / −0** |

`k` = 3, 5 and 8 measure identically, so the fewest extra candidates wins on parsimony rather than on
reporting-split performance.

**Provenance confirms the mechanism rather than assuming it.** Three outcomes look identical in an
aggregate mis-lock number: rescuing the truth, duplicating a site intensity already found, or
proposing a new impostor that then wins. Only the first justifies shipping. Measured over 100 pairs:
the residual proposes the truth on **2** pairs intensity misses, and exactly **one**
auxiliary-proposed candidate ever wins — a rescue. No impostor is ever manufactured.

**Why this is not PADM (§8) returning.** PADM removed periodic frequencies with a Fourier mask and
used the result as a *ranking* score with two tuned constants; it gained on its tuning split and lost
on both held-out splits. Nothing here ranks. A representation can be useless at ranking and useful
at proposing, and only the first was ever tested.

**On duplicating the lattice estimator.** `proposals.py` estimates a period per axis, while the
project's existing `padm.estimate_lattice` exposes a single radial `dominant_pitch_px`. Checked
rather than argued: on ten pairs the existing estimator's value matches one of the two per-axis
periods every time (16.13/23.26 against 23.25; 4.52/6.80 against 4.52; 5.32/8.00 against 8.00). It
is not a divergent second estimator — it computes a strictly richer quantity the existing API does
not expose, and agrees on the axis they share.

**The cost is real and is the argument against.** ×1.46 runtime, on a figure already above this
project's own 300 ms target and, at the time of writing, **not certified at all** (ADR-0034). This
is accuracy bought, not found. It ships on the same precedent as the screened wide refit — this
project has consistently chosen accuracy where no runtime limit is published — and the trade is
stated in the README rather than buried.

### Amendment, 16 Aug — the stress cost this ADR shipped without measuring

This decision was validated on the 300 clean pairs (+4 fixed / −0 broken) and the robustness sweep
was **never re-run for it**. Measured now, over the same 25 operating points with identical
generator seeds and the ADR-0036 guard off on both sides:

| | 750 stress pairs |
|---|---|
| fixed | 2 (±2°, ±5° rotation) |
| broken | **3** (read noise σ=20, fixed 10:1, 0° rotation) |
| net | **−1** |

So the residual channel buys 4 pairs on clean data and gives back a net 1 across the stress sweep —
essentially flat there, not the free win the original entry implies. **It stays**: the clean-data
gain is paired, reproducible and targets the `absent` bucket nothing else reaches, and −1 of 750 is
well inside this sweep's sampling floor. But the entry above claimed a benefit it had not measured
in the regimes it had not run, and that is recorded here rather than left to be discovered.

The mechanism is plausible and already documented in ADR-0034's own text: a wider candidate pool has
more competition in it, so on pairs where the intensity channel was only just winning, three extra
proposals can displace it. That is the same effect that pushed `finfet 25` from rank 29 to 32.

---

## ADR-0034 · 2026-08-15 · accepted · The screen widens to 30, because the selector that receives it changed

**Decision.** `refit_screen_top_n` 10 → 30.

**What forced it.** 4 of the 11 remaining failures were lost at the screen, and §23d had already
measured this exact knob at 6/10/15/20 and found it **flat** — so the cut point was closed. Both
facts cannot hold unless the truth ranks far below every cut tested, which is checkable. Instrumenting
the screen on all 100 pairs:

| where the truth is | failures | rank the screen gives it |
|---|---|---|
| absent — never a candidate | 3 | — |
| survives the screen and still loses | 4 | 0, 0, 0, 2 |
| **cut by the screen** | 4 | **12, 14, 25, 29** |

On *correct* pairs the truth's screen rank is median 0, p90 0. So a wider cut always did reach these
four. §23d found it flat because **recovering a candidate is not winning**: they entered the wide
refit and lost the final comparison to the plain maximum — the statistic ADR-0032 replaced.

**Measured, same pairs, only the cut varying:**

| `top_n` | dev | sponsor | bench | FinFET | reporting | runtime |
|---|---|---|---|---|---|---|
| 10 | 7.5% | 5.0% | 23.3% | 6.7% | 11.0% | ×1.00 |
| 15 | 7.5% | 0.0% | 23.3% | 6.7% | 9.0% | ×0.96 |
| 20 | 7.5% | 0.0% | 23.3% | 6.7% | 9.0% | ×1.01 |
| **30** | **5.0%** | **0.0%** | **20.0%** | 6.7% | **8.0%** | see below |

**+4 fixed, 0 broken over 140 pairs, exact McNemar p = 0.125.** No split regresses; sponsor reaches
0.0%. `dev` alone selects 30, so the choice is made on the tuning split (R5) and the reporting splits
confirm it.

**The runtime cost is not yet cleanly measured, and the first two attempts were both unusable.** The
interleaved sweep above reads ×1.05, but it ran four configurations per pair on a loaded machine,
which compresses relative differences. A clean re-measure then reported a **baseline control at
76 ms against a quiet-machine 22 ms** — the machine was throttled and the benchmark's own gate said
so and refused to certify. The ratio-to-baseline column drifts too, because the heavier workload
throttles harder than the control does (20.8× before, 25.9× while throttled).

So the honest statement is: **the cost is somewhere between ×1.05 and roughly ×1.9, and it must be
re-measured on a settled machine before any figure is quoted.** What is structurally true is that
tripling the candidate count does *not* triple the work — the wide refit groups candidates by pose
and builds each template once (§23's hoist), so the extra candidates cost correlations inside
existing pose groups rather than template construction, which dominates. That bounds the cost well
below ×3 but does not pin it.

**The ablation isolates both stages and shows they are not additive:**

| configuration | sponsor | bench | FinFET |
|---|---|---|---|
| **DEFAULT** — top_n = 30 **+** pose evidence | **0.0%** | 20.0% | 6.7% |
| top_n = 10 + pose evidence | 5.0% | 23.3% | 6.7% |
| top_n = 30, **no** pose evidence | 20.0% | 16.7% | 10.0% |
| top_n = 10, no pose evidence | 20.0% | 16.7% | 10.0% |

The last two rows are **identical to the decimal**: widening the screen buys nothing without the
evidence selector, which is §23d's flat measurement reproduced on demand.

**The general lesson, which is worth more than the three points.** §23f's warning that a wider field
hands impostors more chances is still true; the plain maximum is simply the statistic that cashes
those chances in. Once selection stopped rewarding the luckiest sample, a wider field became a net
gain. **A parameter measured as "flat" is flat against the pipeline it was measured in.** ADR-0027
says stages must be judged in the regime they target; this says the same of configuration. What
re-opened it was a contradiction between two of our own recorded results, not a new idea.

---

## ADR-0033 · 2026-08-15 · accepted · The RGB optical bonus images a coarser layer, and measures its own colour axis

**Decision.** `--modality optical` generates 3-channel brightfield pairs through
`src/synth/optical.py`. The localizer is unchanged; `src/driftlock/color.py` supplies an optional
colour-to-single-channel projection and is a no-op on grayscale input, which a test asserts.

**Why the optical path is not the SEM path in colour.** An optical microscope is diffraction-limited
at `0.61 λ/NA` = **372.8 nm**, six times the 64 nm DRAM word-line pitch. The cell lattice is not
blurred in this modality; it is **absent**. Rendering a colourised SEM image would have been
physically false in a way a process engineer would spot immediately. So the optical modality images
a **coarser layer** — mats and peripheral routing, which is what optical inspection is actually used
for — preserving the ambiguity the task is about while changing the physics honestly.

Contrast comes from thin-film interference (`4πnd/λ`), not from dye, which is why two materials can
share a luminance and separate cleanly in one channel. Chromatic aberration and a wavelength-scaled
PSF are modelled because they follow from the same optics and make the three channels genuinely
non-redundant.

**The result that matters.** The SEM pipeline — built around an electron probe, area-average
decimation and Poisson-Gaussian noise — localizes diffraction-limited RGB brightfield to a **median
of 0.10 px with no code changes**, because `load_grayscale` folds colour to luminance and the
forward-model framing does not depend on the modality.

**Why measure the colour axis rather than use luminance.** Rec. 601's weights describe the human
eye; which channel separates two materials depends on the film thickness on the wafer. Measuring the
direction of greatest colour variance in the **reference** (the high-dose acquisition) and applying
it to both images gives, on 30 pairs:

| arm | mis-lock | median px | p95 px | pass@1px |
|---|---|---|---|---|
| luma | 6.7% | 0.1003 | 11.94 | 93.3% |
| **measured projection** | **3.3%** | 0.0929 | **0.51** | **96.7%** |
| green channel *(control)* | 6.7% | 0.0871 | 11.89 | 93.3% |

The measured direction sits **25.6°** from luminance and averages **R +0.787, G +0.610, B +0.082** —
a real red-green mix, not a channel pick, which is what the `green` control existed to rule out. The
mis-lock difference is +1/−0 on 30 pairs and is not significant on its own; the p95 collapse from
11.94 px to 0.51 px is the sturdier figure.

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

---

## ADR-0036 · 2026-08-16 · accepted · The drift correction is bounded, because it is the last thing that runs

**Decision.** `drift_max_shear_px = 6.0` ships. `estimate_and_correct` abandons a shear estimate
whose magnitude exceeds the bound and returns the coordinate unchanged — the same posture it
already took when estimation failed outright and returned `None`.

**What forced it.** The failure decomposition sorts every mis-lock into ABSENT / SCREENED /
OUTSCORED — three ways of choosing the wrong candidate. It had no bucket for *choosing the right
candidate and then moving off it*, because nothing had ever measured post-selection movement.

`scripts/refine_forensics.py` measures it, recording the answer after each of the three stages that
run once a candidate is committed to. Over 354 pairs:

| stage | median move | p95 | max |
|---|---|---|---|
| `_refine_pose_local` | 0.000 px | 0.000 | 1.000 |
| sub-pixel DFT | 0.250 px | 0.424 | 0.707 |
| **drift correction** (clean 300) | **0.652 px** | **2.077** | **24.254** |
| **drift correction** (all 354, incl. jitter stress) | **0.713 px** | **3.772** | **33.937** |

The first two stages are bounded by construction and stay bounded under stress. The drift stage is
neither. Two pairs in the 300 clean ones selected a candidate within 5 px of ground truth and were
still reported as mis-locks. Both are this stage, and nothing else in 300 pairs is:

| pair | selected at | reported at | \|shear\| |
|---|---|---|---|
| `dev2 100` | 0.789 px | 23.478 px | **50.386** |
| `bench 21` | 0.923 px | 6.539 px | **14.751** |

**Why a bound is the right instrument.** The correction is `x + shear·(y/(H-1))`, so `|shear|`
bounds how far the answer can move, and an estimator blow-up shows up directly as an implausible
shear. The generator's true shear is 1.50 px on every split, so 14.75 and 50.39 are not large
corrections — they are wrong ones.

**Why 6.0 is not a tuned number.** On the 283 clean pairs that are correct today, `|shear|` tops out
at **4.564**; the two pathological pairs read 14.75 and 50.39. Every threshold in [6, 12] therefore
clips exactly those two clean pairs and no others, and thresholds from 3 to 12 all give the same
result on the reporting splits. 6 rather than 8 only because it is also best-or-tied under the two
jitter stress splits, where a noisy estimate is likeliest. Below ~4 it begins clipping legitimate
corrections (7 of 300 at 4 px, 12 at 3 px) and starts costing precision instead of buying accuracy.

**Measured, paired, on every split.** Threshold derived from the tuning family and the shear
distribution, then confirmed by a real pipeline run — not shipped on the simulation:

| split | n | before | after |
|---|---|---|---|
| dev *(tuning)* | 40 | 2 | 2 |
| dev2 *(tuning)* | 160 | 9 | 8 |
| sponsor | 40 | 0.0% | **0.0%** |
| bench | 30 | 16.7% | **13.3%** |
| finfet | 30 | 3.3% | **3.3%** |
| **aggregate** | 100 | 6.0% | **5.0%** |

**Zero regressions, and no precision traded for it.** Median error is unchanged on all three
reporting splits (0.179 / 0.300 / 0.214) and pass@0.5px is unchanged (92.5% / 66.7% / 76.7%),
because the guard clips only the two pairs that were already wrong. pass@1px on bench rises
80.0% → 83.3%.

**And it is strictly dominant on the stress sweep too**, which is where a guard that rejects a
*legitimately* large correction would show up as a cost. Run twice over the same 25 operating points
with identical generator seeds, `--no-drift-guard` against the shipped default:

| | 750 stress pairs |
|---|---|
| fixed | **12** |
| broken | **0** |

It improves 10 of the 25 points and worsens none. The largest single gain is ±5° rotation
(30.0% → 23.3%) and the nominal read-noise point (20.0% → 13.3%); both are regimes where drift
estimation is hardest, which is the direction the mechanism predicts.

**Honest scope.** This buys one pair on the reporting splits. Its real significance is the bucket
rather than the count: it is the first failure in this project that was never a selection error, and
it was invisible for as long as the decomposition had only selection buckets in it.

> **A correction to an earlier reading of this experiment.** The first comparison run put three
> stress points *worse* and I very nearly attributed that to the guard. It was not the guard:
> `results/robustness.csv` had last been regenerated at 68d1ef0 and had never been re-run for
> ADR-0035, so the comparison spanned **two** config changes. Isolating them with `--no-drift-guard`
> assigns all three regressions to ADR-0035 and none to ADR-0036. *A stale baseline makes a clean
> experiment produce a confident wrong answer* — see the note appended to ADR-0035.

**What would change our mind.** Evidence that a legitimate shear can exceed 6 px on data we care
about. The estimator saturates rather than growing without bound, so if the evaluator's data has
genuinely stronger raster drift than ours, the guard should be raised — or replaced by a bound
derived per-pair from the measured lag search range rather than a constant.

---

## ADR-0037 · 2026-08-16 · accepted · The screen cut widens again, 30 → 40 — and it changes no reported number

**Decision.** `refit_screen_top_n = 40`. Chosen on the tuning family, confirmed harmless on the
reporting splits, and shipped **in full knowledge that it does not move the headline**.

**What forced the re-examination.** ADR-0034 widened this cut 10 → 30 and explained why FINDINGS
§23d had measured the same knob as flat: the candidates a wider cut recovered were being handed to
the plain maximum, which is the thing that loses ties. Three further stages have landed since
(ADR-0035 proposals, ADR-0036 guard), each changing what the screen hands downstream. The knob was
therefore due a third measurement, and this time by standing tooling rather than another throwaway
script — `scripts/param_sweep.py`.

**Measured, paired, real pipeline.** Tuning family first, and the value frozen before the reporting
splits were scored (R5):

| cut | dev | dev2 | tuning total | fixed | broke |
|---|---|---|---|---|---|
| 30 | 2 | 8 | 10 | — | — |
| **40** | 2 | 5 | **7** | **3** | **0** |
| 60 | 2 | 5 | 7 | 3 | 0 |

40 and 60 measure **identically**, so this is a plateau rather than a spike — which is the main
reason to believe it is not a selection artefact of picking the best of three values. 40 is the
cheap end of the plateau.

| cut | sponsor | bench | finfet | reporting total | fixed | broke |
|---|---|---|---|---|---|---|
| 30 | 0 | 4 | 1 | 5 | — | — |
| **40** | 0 | 4 | 1 | **5** | **0** | **0** |

**Every reported number is unchanged to the decimal** — 0.0% / 13.3% / 3.3%, medians 0.179 / 0.300 /
0.214, aggregate 5.0%. This ADR buys nothing a judge can see.

**Runtime ×1.091**, measured by interleaving both arms within one session, three rounds over eight
pairs. The absolute milliseconds are not quotable (the machine is down-clocked, ADR-0036) but the
ratio is: both arms saw the same clock, cache and thermal history. Much cheaper than the naive
33%-more-candidates estimate, because the wide refit groups candidates by pose and builds each
template once — extra candidates inside an existing group cost correlations, not templates.

**Why ship a change worth nothing on the reported data.** The reporting set is 100 pairs and the
effect is 1.5%; the expected number of visible fixes there is about 1.5, so observing 0 is entirely
consistent with a real effect this size and is a statement about power, not about the change. The
evidence base is 300 pairs with **zero regressions on any of five splits**, which is the same bar
ADR-0034 and ADR-0036 cleared. And the tuning family exists precisely so that decisions can be made
on data that is not reported — declining to act on +3/−0 there would make it ornamental.

**Why it might still be wrong.** The gain rests entirely on splits used for tuning, and this
parameter was selected on those splits. The plateau and the zero regressions are the argument
against that reading, not a proof. **If a runtime limit is ever published, this is the first thing
to revert** — it is 9% for an effect no reported metric can see.

**`finfet 25` was not recovered**, though it sits at screen rank 31 and a cut of 40 reaches it. That
is ADR-0034's lesson pointing the other way: reaching the wide refit is not the same as winning it.

**On the stress sweep it is net positive but NOT strictly dominant**, which is the main thing this
entry has to report that the tuning table does not. Same 25 operating points, same seeds, guard on
both sides:

| | 750 stress pairs |
|---|---|
| fixed | 5 — nominal dose, 8–12:1 scale, 0°, ±1°, ±5° rotation |
| **broken** | **2 — charging streaks 26.7% → 30.0%, heavy blur 6.7% → 10.0%** |
| net | **+3** |

ADR-0036 was 12/0 on the same sweep; this one costs two pairs to buy five. The mechanism of the
loss is the same as the mechanism of the gain, seen from the other side: a wider cut admits more
candidates, and more candidates means more competition, not only more chances. That is ADR-0035's
amendment repeating itself.

**Split by the spec envelope, which is the split that decides it** — the sweep already records
`in_spec_envelope` per operating point, and neither the original write-up nor an external review of
it thought to use the column:

| | fixed | broken |
|---|---|---|
| **inside the spec envelope** | **3** | **0** |
| beyond the spec envelope | 2 | 2 |

Every in-spec regime measured improves and none regresses: nominal dose 16.7% → 13.3%, 0° rotation
13.3% → 10.0%, ±1° rotation 3.3% → 0.0%. Both regressions — charging streaks and 12 nm beam spot —
are beyond-spec points, and beyond-spec is exactly break-even overall. An external review
recommended reverting this change on the strength of the charging-streak regression alone; that
reading does not survive the envelope split, because the point it rests on is outside the range the
problem statement says will be tested and is paid for by beyond-spec gains elsewhere.

This does not make the change strictly dominant, and it is still worth nothing on the reported 100
pairs. It does mean the honest summary is *"strictly dominant inside the tested envelope, neutral
outside it"* rather than *"net positive with two regressions"*.

**Totals across everything measured:** +3/−0 on 200 tuning pairs, +0/−0 on 100 reporting pairs,
+5/−2 on 750 stress pairs. Net +6 broken 2 over 1050 pairs.

⚠️ `results/robustness_noguard.csv`, the ADR-0036 attribution run, was measured with `top_n = 30` on
both arms. It remains a valid paired experiment **at that configuration** and its 12/0 result stands,
but it must not be diffed against the current `robustness.csv`, which is a 40-cut run. Regenerate
both arms if that comparison is ever needed again.

**What would change our mind.** A fourth measurement showing it flat again after some later stage —
which, given this knob's history, should be actively expected rather than treated as surprising.
Or a published runtime limit, which would make 9% for an invisible gain the wrong trade outright.
