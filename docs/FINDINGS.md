# FINDINGS — experiment log

Everything tried, what the number was, and why it behaved that way. Negative results are kept in
full: the spec allocates **10% to failure analysis and explainability**, and a method we tried and
dropped with its measurement attached is evidence of rigour, whereas a silently omitted experiment
reads as cherry-picking the moment a judge asks the obvious question (rule R9).

Last updated: 11 Aug 2026. Companion documents: `DECISIONS.md` (why choices were made),
`PROGRESS.md` (what is done), `results/` (the generated numbers themselves).

---

## 0. Summary — the state of things

| # | Experiment | Verdict | Effect |
|---|---|---|---|
| 1 | Sponsor-generator hypotheses H1–H10 | ✅ all confirmed | Foundations are sound |
| 2 | Baseline reproduction (INTER_AREA + ZNCC argmax) | ✅ measured | 25% mis-lock, 1.102 px median |
| 3 | Median filter (impulse noise) | ⚪ no effect | Nothing to remove in this data |
| 4 | Row destriping (charging streaks) | ❌ **harmful** | mis-lock 18.8% → 31.2% |
| 5 | Generalized Anscombe transform (A1) | ⚪ no effect on argmax | Monotone map cannot move an integer peak |
| 6 | Phase congruency (A2) | ❌ **broken** | 100% mis-lock, 324 px median |
| 7 | Top-K candidate retention (A6) | ⚪ no effect alone | Correct — needs a re-ranker to matter |
| 8 | PADM residual re-scoring (A7) | ❌ harmful as tuned | mis-lock 18.8% → 25% |
| 9 | Closest-to-centre rule (A8) | ⚪ no effect | `tau` too wide; see §8 |
| 10 | Sub-pixel DFT (A9) | ✅ **works** | median 1.102 → 1.085, pass@1 40% → 45% |
| 11 | ECC affine (A9) | ❌ silently inert | Never converges; see §10 |
| 12 | **Drift-frame correction** | ✅✅ **decisive (oracle)** | median 0.866 → **0.062 px** |

**One-line state:** the baseline is reproduced and understood, the dominant error source is
identified and explained, and the single largest improvement available has been quantified — but it
currently depends on an oracle value and is therefore **not yet a usable result**.

---

## 1. Verifying the foundations before building on them

**Why.** Every architectural choice rested on facts I derived by *reading* the sponsor's published
generator source. Reading is not evidence. If one of those facts were wrong, work built on it would
be wasted, and the failure would surface late and confusingly.

**Method.** `scripts/verify_hypotheses.py` tests each claim against 40 real generated pairs
(`dram_1x`, seed 20260811) and writes verdicts to `results/hypotheses.md`.

**Result.** All confirmed. The load-bearing ones:

- **H1** — the reference occupies exactly a **100×100 px** footprint in the search image. This is a
  *downscale-the-reference* problem, not a small-template problem.
- **H2** — `gt = (x0/10 + 50, y0/10 + 50)` with integer `x0`. Ground truth lands on a 0.1 px grid,
  and the centre convention is `origin + size/2`, **not** `origin + (size−1)/2`. Half a pixel
  matters when the pass threshold is 1 px, so this was worth settling by measurement.
- **H3** — noise is Poisson (shot) then Gaussian (detector). Measured variance is affine in the
  mean: `Var = 1.75·mean + 426`. A purely additive model predicts slope 0.
- **H7** — the aperiodic fingerprint exists. The self-correlation margin between the true alignment
  and its best lattice-equivalent impostor is **strictly positive on every reference tested**
  (median 0.057, min 0.0086). Disambiguation is possible in principle — a genuinely non-obvious
  precondition for the whole approach.
- **H8** — rival peaks are always >5 px away (median 45.5 px) but only 0.016 lower in score.
  Competing hypotheses are separated by far more than the tolerance and far less than the noise.

**Two of my own tests were wrong and had to be fixed before their answers meant anything.**

*H4 conflated two claims.* The first version asked "does INTER_AREA + argmax land within 5 px" and
reported REFUTED. But that bundled *is the forward model correct* (yes, emphatically) with *does
argmax suffice* (no — and that is the entire point of the project). **A test that bundles the thing
you are validating with the thing you are trying to beat cannot distinguish them.** Split into H4a
(forward model: ZNCC at truth averages 0.835, min 0.580) and H4b (argmax: fails 25% of the time).

*H8's lag mask was too small.* It excluded lags below 8 nm and then reported its peak at exactly
8 nm — the boundary of the mask. It was measuring the beam-PSF correlation length, not the lattice.
A plausible-looking number measuring the wrong quantity is more dangerous than an obvious error.

---

## 2. The baseline floor

**Why.** Without a measured baseline there is no ablation row 1 and no improvement can be
substantiated (R6).

**Result** — 40 sponsor pairs, `INTER_AREA` template + `matchTemplate` argmax:

| Metric | Value |
|---|---|
| Mis-lock rate (>5 px) | **25.0%** (10/40) |
| Median error | 1.102 px |
| Mean error | 15.463 px |
| Worst error | 271.71 px |
| pass@5px / @4px / @2px / @1px | 75% / 75% / 75% / 40% |
| Runtime | p50 29.9 ms, p95 33.1 ms |

**The pass-rate shape is itself diagnostic.** Flat at 75% from 5 px down to 2 px means *nothing*
lands between 2 and 5 px — the error distribution is bimodal. A pair is either located (≈1 px off)
or mis-located (tens to hundreds of pixels off). The drop to 40% at 1 px is a separate phenomenon,
explained in §12.

**Consequence for reporting.** The mean error of 15.463 px describes no actual pair. Averaging over
a bimodal distribution produces a number that is technically correct and materially misleading, so
`evaluate.py` reports the **mis-lock rate separately** and gives median error both overall and among
correctly-located pairs only.

---

## 3. Median filter — no effect

**Hypothesis.** Salt-and-pepper noise creates unbounded outliers that a correlation has no defence
against, so a 3×3 median should help.

**Result.** Bit-identical metrics with and without.

**Explanation.** `salt_pepper_prob = 0.0` in the sponsor's defaults — there is no impulse noise in
this data to remove. **Kept in the codebase, off by default.** It is genuinely the right tool if the
evaluator enables impulse noise, and it costs nothing when there is none. This is a case where a
null result does not mean the idea is wrong, only that this dataset does not exercise it.

---

## 4. Row destriping — actively harmful ❌

**Hypothesis.** The generator adds charging streaks as whole rows offset by a constant
(`out[lo:hi, :] += intensity`). Because the corruption is constant along a row, subtracting each
row's median should remove it almost exactly.

**Result.** Mis-lock rate **18.8% → 31.2%**. Median error 1.055 → 1.383 px.

**Explanation — and it is a good lesson.** The reasoning was correct about the artefact and wrong
about the signal. **DRAM word lines are horizontal.** They are row-constant too. Subtracting the row
median removes the streaks *and* a large part of the real structure the matcher depends on. Charging
streaks are also disabled in this data (`charging_streak_prob = 0`), so the operation removed signal
and bought nothing.

**Generalisable point:** a correction targeted at a specific artefact must be checked against the
specific *signal*, not just the artefact. "Row-constant" described both.

**Status.** Retained but off by default, to be enabled only when streaks are actually present — at
which point it should be applied to the residual after lattice removal, not the raw image.

---

## 5. Generalized Anscombe transform (A1) — no effect on argmax

**Hypothesis.** H3 confirms Poisson–Gaussian noise, so per-pixel variance rises with intensity.
ZNCC is the maximum-likelihood estimator only under constant-variance additive noise; under shot
noise it over-trusts bright pixels. The GAT (Mäkitalo & Foi, IEEE TIP 2013) stabilises the variance,
after which correlation is approximately ML.

**Result.** Metrics identical to 3 decimal places.

**Explanation.** The GAT is a *monotone* transform. It rescales the correlation surface but does not
move an integer-valued argmax. The theory is not wrong — the measurement simply cannot see it,
because the metric being measured is insensitive to it by construction.

**Where it should show up instead:** (a) sub-pixel refinement, where the *shape* of the correlation
peak matters, not just its location; (b) genuinely low-dose data, where the variance ratio between
bright and dark pixels is extreme. **Not yet a negative result — an untested one.** It must be
re-measured after refinement works, and the claim held back until then (R6).

---

## 6. Phase congruency (A2) — broken ❌

**Hypothesis.** Gamma, vignetting and a 10× dose difference all change pixel *amplitudes* without
changing where Fourier components come into phase. Phase congruency (Kovesi) measures exactly that
alignment and is therefore invariant to those nuisances by construction rather than by tuning.

**Result.** **100% mis-lock, 324 px median error.** Catastrophic.

**Explanation.** The idea is standard and sound; my log-Gabor approximation is not. Likely causes,
in order of suspicion: summing the even (real) filter responses signed rather than taking the energy
`sqrt(even² + odd²)` consistently; the DC and Nyquist handling in the radius grid; and a filter bank
whose wavelengths do not span the actual lattice pitch (6.4–9.6 px in search space).

**Status.** Disabled. Reported as *broken implementation*, not as *evaluated and rejected* — those
are very different claims and only the first is currently supported by evidence.

---

## 7. Top-K candidate retention (A6) — no effect alone, as expected

**Result.** Identical to baseline.

**Explanation.** Correct behaviour, not a bug. Keeping 20 candidates and then selecting by maximum
score returns exactly what the argmax would have returned. Top-K only pays off in combination with a
re-ranker that can promote a lower-scoring candidate — which is what PADM (§8) and the centre rule
(§9) are for. Its value is that it **preserves the correct answer for a later stage to recover**: in
the worst measured case the true location was the *runner-up*, behind by only 0.0124 ZNCC (1.3%).
The argmax throws that away before disambiguation can happen.

---

## 8. PADM residual re-scoring (A7) — harmful as tuned ❌

**Hypothesis.** The raw correlation score is dominated by the periodic lattice, which by definition
carries no information about *which* repeat you are on. Removing the lattice in Fourier space should
raise the aperiodic residual — where cell identity lives — from a rounding error to the dominant
signal.

**Result.** Mis-lock rate **18.8% → 25%**, and runtime 63 ms → 242 ms.

**Explanation — unresolved, with two credible causes.** H7 confirms the fingerprint exists, so the
premise holds; the implementation does not yet exploit it.

1. **Blend weight untuned.** `padm_weight = 0.5` weights the residual equally with the raw score.
   At dose 200 the residual has low SNR, so half the decision is being made on the noisiest channel
   available.
2. **Bandwidth untuned.** `bandwidth = 0.006` cycles/px sets how much of each spectral peak is
   treated as "lattice". Too narrow leaves lattice energy in the residual (defeating the purpose);
   too wide removes genuine aperiodic content along with it. The random-walk line placement
   *broadens* the true peaks, which pushes toward a wider band than a perfect lattice would need.

**Status.** Off by default. Not claimed as either a success or a refutation — the parameters have
not been swept, so there is no basis for either statement yet.

---

## 9. Closest-to-centre rule (A8) — no effect

**Result.** No change when added on top of PADM.

**Explanation.** `tau`, the score window defining a "tie", is derived as `0.25 × std(scores)` across
all candidates. With 20 candidates spread over the whole search image the spread is large, so `tau`
is large and nearly everything qualifies as tied — after which the rule picks whichever candidate is
nearest the image centre, which for uniformly-placed ground truth is usually wrong. In the observed
runs it either selected the same candidate anyway or made things worse.

**The measured guidance for fixing it:** H8 puts the real winner-versus-rival margin at a median of
**0.016**. `tau` should be on that order — derived from the *local* score noise, not the global
spread of a set that deliberately includes distant, unrelated peaks.

**Note.** The rule itself is mandated by the problem statement, so it stays in the code and stays
visible. What needs fixing is the tie *criterion*, not the tie *break*.

---

## 10. ECC affine (A9) — silently inert ❌

**Result.** No change whatsoever, in any configuration.

**Explanation.** `cv2.findTransformECC` is raising and being caught by the `except cv2.error`
fallback on every pair, so the unrefined estimate is returned every time. The fallback is correct
design — a diverged refinement must not be trusted — but a stage that *always* falls back is not a
stage, and it was reporting success by producing no error.

This is a case worth flagging: **a silent fallback made a completely non-functional component look
merely ineffective.** It should log at debug level when it fires, so the difference between "tried
and didn't help" and "never ran" is visible.

Standalone testing (`tests/test_deps_api.py`) confirms ECC itself is fine, reaching **0.037 px** with
`MOTION_AFFINE` on band-limited data. So the failure is in how it is being invoked here — most
likely the seeded warp matrix convention, or feeding it patches that are too small or too flat.

---

## 11. Sub-pixel DFT (A9) — works ✅, after fixing an inverted sign

**Result.** Median 1.102 → 1.085 px, pass@1px 40% → 45%. Among correctly-located pairs, 0.900 →
0.866 px.

**The sign convention was backwards, and I determined it by measurement rather than from the
documentation.** With `phase_cross_correlation(window, template)`, the returned `(row, col)` shift
must be **added** to the current estimate. Measured across 8 real pairs:

| pair | as found | subtracting | adding |
|---|---|---|---|
| 0 | 0.894 | 1.417 | **0.411** |
| 1 | 1.900 | 2.310 | **1.490** |
| 5 | 1.105 | 1.533 | **0.680** |

Adding improved 7 of 8; subtracting made every one worse. **Get this backwards and the refinement
silently doubles the error instead of halving it** — a plausible-looking result that would survive
code review, which is exactly the class of bug rule R4 exists for.

**A related trap, recorded in ADR-0009:** `phase_cross_correlation` must be called with
`normalization=None`. The scikit-image default `'phase'` whitens the spectrum by dividing by
magnitude; on blurred images the high-frequency magnitudes are ≈0, so that division amplifies
numerical noise and **silently returns approximately zero shift** — 2.8 px error on a true 2.86 px
displacement at blur σ=3. Our images are blurred by the beam PSF.

**Why the gain is only modest.** Because the dominant residual is not a matching error at all — §12.

---

## 12. The dominant error source: a drift-frame offset ✅✅

**This is the most important finding so far.**

**Observation that started it.** Across every correctly-located pair, the x error was systematically
negative (mean −0.837 px) while the y error was not (mean +0.073 px). A random error is not one-sided.

**Hypothesis.** `apply_raster_drift` remaps row *r* by `shear·(r/999)` in x only, modelling stage
drift accumulating over scan time. If that is the cause, the x error should correlate with the
template's y position.

**Test.** Regress dx on gt_y across 30 correctly-located pairs.

**Result.** Pearson **r = −0.861**, slope −0.00165 px/px against a predicted −`shear`/1000 =
−0.00150 px/px. Sign and magnitude agree.

**The explanation, which changes the approach.** The raster drift **physically displaces the search
image's content**, while the ground truth is defined in the **undrifted** frame. The matcher is
finding exactly where the content *is*; the ground truth records where it *would have been* without
drift. That gap is unreachable by any improvement to the similarity measure — it is not a matching
error, and no amount of better correlation, better features or better sub-pixel fitting will close
it.

**Quantifying the ceiling.** Inverting the shear analytically,
`x_corrected = x_found + shear·(y_found/999)`, over 40 pairs:

| | median (located) | mean | pass@1px | pass@0.5px |
|---|---|---|---|---|
| as found | 0.866 px | 0.827 | 45% | 18% |
| **shear-corrected** | **0.062 px** | **0.069** | **75%** | **75%** |

A **14× reduction**, landing near the noise floor. It also fully explains the baseline's pass-rate
shape: flat 75% from 5 px to 2 px then collapsing to 40% at 1 px, because nearly every located pair
sits in a narrow band set by this one systematic offset.

> ### ⚠️ This used the true shear from the manifest — an ORACLE
>
> At inference we do not get the shear value. **This is not a usable result and must never be quoted
> as an achievement** (R6). It is an *upper bound* that establishes what blind estimation is worth —
> which is a great deal, and is why it is now the highest-priority work.

**Why it matters beyond the number.** It is the strongest confirmation of the project's thesis so
far. The largest available win came from **inverting a known acquisition distortion**, not from a
better matcher. That is "we don't match images, we invert the microscope" being vindicated by
measurement rather than asserted in a slide.

---

## 13. What this means for the plan

**Confirmed as valuable:** verifying foundations before building (§1 caught two of my own broken
tests); reporting the mis-lock rate separately from the median (§2); keeping top-K so a later stage
can recover the true answer (§7).

**Needs rework:** PADM parameters (§8), the tie criterion for the centre rule (§9), the ECC
invocation (§10), and the phase-congruency implementation (§6).

**New and highest priority:** blind estimation of the raster shear (§12).

### Blind shear estimation — the approach and its risk

The reference image is shear-free (`image_reference` passes `shear_amplitude_px = 0.0`) while the
search image is sheared. The distortion should therefore appear as a difference in **lattice basis
vectors** between the two images: a shear tilts the vertical bit-line direction by
`atan(shear/1000)`. This is exactly plan step A5, "lattice as a ruler" — using the periodicity that
defeats ordinary matching as a measuring instrument.

**Honest risk assessment.** For shear = 1.5 px over 1000 rows the tilt is only **0.086°**, against an
FFT angular resolution of roughly **0.057°** at this image size. That is measurable but not
comfortably so. This needs a real measurement and a fallback for when the estimate is unreliable —
it must not be assumed to work because the payoff is attractive.

**Also outstanding:** our own generator (30% of the score, and the only way to exercise the 9:1–11:1
scale and 1–2° rotation envelope the spec says will be tested — the sponsor's generator produces
neither, confirmed as H9).
