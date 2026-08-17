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

## 12b. Blind shear estimation — attempted, failed, abandoned ❌

Following §12, the obvious next step was to estimate the shear without an oracle. Two approaches
were tried on data generated at shear ∈ {0.0, 1.5, 3.0, 5.0} (the sponsor's generator exposes
`--shear-amplitude-px`, so the estimator could be validated against known truth rather than against
a single constant).

**Attempt 1 — horizontal band correlation.** Split the search image into horizontal bands, collapse
each to a 1D column profile, and cross-correlate each band against the first. The x-displacement
should grow linearly with band centre row, with slope `shear/(H−1)`.

*Result:* per-band shifts of 291, 431, −289 px — nonsense. **The lattice's own periodicity aliased
the estimator onto a different repeat.** The same ambiguity that defeats the matcher defeated the
tool built to help it.

**Attempt 2 — the same, with the lag search constrained to ±4 px** (unambiguous, since the expected
shift is <5 px while the lattice pitch is ~9.6 px).

*Result:* estimates of −0.90, −1.12, +0.26, −2.26 px for true shears of 0.0, 1.5, 3.0, 5.0. **No
correlation with truth**, and per-pair scatter (±3–6 px) larger than the quantity being measured.

**Why it cannot work this way.** The canvas is zoned in **both** directions: horizontal strips
separate mats vertically, and each mat's line positions are drawn independently. So two horizontal
bands do not contain the same pattern displaced by the shear — they contain *genuinely different
patterns*. There is no common signal to correlate. The method is unsound for this data, not merely
imprecise.

**Not pursued further, and that is a deliberate scope call.** The remaining candidate — comparing
reciprocal-lattice angles between the shear-free reference and the sheared search — needs to resolve
a **0.086°** tilt against roughly **0.057°** of FFT angular resolution. That is a marginal
measurement at best, and the payoff is bounded: correcting the drift offset is worth ~0.8 px on
pairs that are *already correct*, whereas **25% of pairs are currently wrong by tens to hundreds of
pixels**. Mis-lock is worth roughly an order of magnitude more, and it is the failure mode the
problem statement is actually about.

**A tempting shortcut, explicitly rejected.** The sponsor's default shear is a fixed 1.5 px, so a
hard-coded correction would improve our score on their default data. It is rejected: it is
calibration to one generator setting rather than a method, it would make results *worse* than no
correction if the evaluator sets shear near zero, and it is precisely the overfitting that rules R5
and R6 exist to prevent.

**Recorded as an honest limitation.** The drift-frame offset is a real, understood, quantified error
source that we can bound (0.87 px → 0.062 px if known) but cannot currently remove blind. That is a
stronger statement than most teams will be able to make about their residual error, and it belongs
in the limitations section rather than being hidden.

---

## 12c. Candidate recall — the single most useful measurement so far ✅

**The question that should have been asked first.** When the pipeline mis-locks, is the true
location *in the candidate set at all*? That determines whether the problem is candidate
**generation** or candidate **ranking** — and those need completely different fixes.

**Method.** For each pair, extract the top-K correlation peaks and check whether any lands within
5 px of ground truth.

| K | Truth present in candidate set | Median rank of truth |
|---|---|---|
| 1 | 75.0% | 1 |
| 5 | 87.5% | 1 |
| 20 | **92.5%** | 1 |
| 50 | 92.5% | 1 |
| 100 | **97.5%** | 1 |

**What this establishes.** Candidate generation is *not* the bottleneck. At K=20 the correct answer
is available 92.5% of the time and we select it only 75% of the time, so **a perfect re-ranker would
cut the mis-lock rate from 25% to 7.5%** — and to 2.5% at K=100. The problem is ranking, and there
is a 3–10× improvement sitting there.

This retroactively justifies the "keep top-K, never commit to the argmax" decision with a number
rather than an argument, and it says precisely where further effort belongs.

---

## 12d. PADM parameter sweep — real but modest ✅

A 5×5 sweep of blend weight × spectral bandwidth over 40 pairs (baseline argmax = 25.0% mis-lock):

| weight ↓ / bandwidth → | 0.002 | 0.004 | 0.006 | 0.010 | 0.020 |
|---|---|---|---|---|---|
| 0.2 | 27.5% | 27.5% | 25.0% | 22.5% | 25.0% |
| **0.4** | 32.5% | 32.5% | 25.0% | **20.0%** | 22.5% |
| 0.6 | 37.5% | 32.5% | 27.5% | 20.0% | 22.5% |
| 0.8 | 40.0% | 37.5% | 30.0% | 30.0% | 22.5% |
| 1.0 | 42.5% | 42.5% | 30.0% | 32.5% | 20.0% |

**Best: 20.0% at weight 0.4, bandwidth 0.010** — the value now used by default.

**The bandwidth trend is the informative part.** Narrow bands (0.002–0.004) are consistently *worse
than doing nothing*. The reason is the random-walk line placement: it **broadens** the true spectral
peaks, so a narrow mask leaves lattice energy behind in the "residual", which then carries exactly
the periodic signal PADM exists to remove. The very property that makes disambiguation possible
(H7) is what forces a wider band.

**Raising K does not help PADM.** At K=50 and K=100 it plateaus at 22.5–30%: more candidates simply
add distractors it cannot discriminate. Against the 7.5% ceiling from §12c, hand-designed residual
scoring is capturing roughly a fifth of what is available.

**Conclusion, and it is a clear signal for the plan.** The gap between the 7.5% ceiling and the 20%
achieved is the strongest justification yet for the **learned re-ranker** (Tier C1). The negatives
are exactly definable (lattice-equivalent positions), the correct answer is in the candidate set,
and hand-designed scoring has demonstrably plateaued well short of the ceiling.

---

## 12e. Current best configuration

Enabled: top-K=20, PADM (w=0.4, bw=0.010), closest-to-centre rule, sub-pixel DFT.

| Metric | Baseline | Tier A | Change |
|---|---|---|---|
| Mis-lock rate | 25.0% | **20.0%** | −5 pts |
| Median error | 1.102 px | **0.975 px** | −12% |
| pass@5px | 75% | **80%** | +5 pts |
| pass@1px | 40% | **52%** | +12 pts |
| Worst error | 271.71 px | **628.58 px** | ⚠️ worse |
| Runtime p50 | 29.9 ms | **218.1 ms** | ⚠️ 7× slower |

**Two regressions, reported rather than buried.** The worst-case error more than doubled: when PADM
re-ranks incorrectly it can promote a *more distant* candidate than the argmax would have chosen, so
the failures get worse even as they get less frequent. And runtime rose 7× from the FFT
decompositions — still inside the 300 ms budget, but the margin is much thinner and it will matter
once further stages are added.

---

## 12f. Blind drift estimation — SOLVED ✅✅ (supersedes §12b)

§12b abandoned this as infeasible. That was **wrong**, and the distinction matters: the two failed
approaches failed for *fixable* reasons, not fundamental ones. "This approach failed" is not the
same claim as "this is impossible", and conflating them nearly cost the largest win in the project.

**The insight.** Rows **close together** contain the same content. Vertical bit-lines run
continuously down the image, so two rows a modest distance apart show the same structure displaced
only by the drift accumulated between them. Correlating them recovers that displacement directly.
The earlier attempts used *distant* bands — which sit in different, independently randomised mats,
so there was no common signal to correlate.

**But adjacent rows alone are not enough.** Correlating neighbours and integrating the differentials
also fails: summing noisy per-row estimates random-walks, accumulating √1000 × 0.05 ≈ **1.6 px** of
integration noise against a **1.5 px** signal. Measured directly, it tracked truth but with ±0.7–1.7
scatter — the right trend, unusable precision.

**The working method avoids both traps.** Correlate rows separated by a fixed **gap** (still inside
one mat, which spans ~260 search px) and fit the displacement **directly**. Nothing is integrated,
so no random walk accumulates. The lag window is kept well below the lattice pitch, or the
periodicity aliases the correlation onto the wrong repeat — exactly how the first attempt failed.

**Validation against known shear** (gap=100, 10 pairs each):

| true shear | estimated | std dev |
|---|---|---|
| 0.0 | 0.009 | 0.202 |
| 1.5 | 1.445 | 0.344 |
| 3.0 | 2.804 | 0.321 |
| 5.0 | 5.184 | 0.245 |

Essentially unbiased, with scatter well below the ~0.84 px bias being removed. Larger gaps are
better (25 → ±0.70, 50 → ±0.40, 100 → ±0.34) because the drift signal grows relative to per-row
noise, bounded by the requirement to stay within one mat.

**End-to-end effect, 40 sponsor pairs, fully blind:**

| | mis-lock | median | median (located) | pass@1px | pass@0.5px |
|---|---|---|---|---|---|
| sponsor baseline | 25.0% | 1.102 | 0.900 | 40% | 18% |
| Tier A | 20.0% | 0.975 | 0.715 | 52% | 20% |
| **+ blind drift correction** | 20.0% | **0.220** | **0.143** | **80%** | **78%** |

Median error **5× better**, median among located pairs **6.3× better**, sub-pixel pass rate
**4.3× better**. Against the oracle ceiling of 0.062 px, the blind estimate reaches 0.143 px — most
of the theoretically available correction, with the remainder being the price of estimating rather
than knowing.

**Safety property.** The estimator returns `None` when too few row pairs survive the correlation
gate (a featureless or heavily zoned image). The caller then skips the correction rather than
applying a guess, so an unreliable estimate can never make results worse than not correcting.

**Why this is the strongest evidence for the thesis.** The largest single improvement in the project
came from **inverting a known acquisition distortion**, not from a better matcher, better features,
or a bigger model. "We don't match images, we invert the microscope" is now a measured claim.

---

## 12g. Generalisation test — PADM was overfit ❌❌ (supersedes §12d, §12e)

**The most consequential experiment so far, and it invalidated a headline result.**

**Why it was run.** Every parameter in the pipeline — PADM blend weight, PADM spectral bandwidth,
drift gap — was tuned on a single split: `dram_1x`, seed 20260811, 40 pairs. Rule R5 requires
checking that tuning transfers before the numbers are believed. It had not been checked.

**Method.** Generate held-out splits with a *different seed* (999333) and a *different architecture*
(FinFET), then re-run every configuration on all three.

**Result.**

| Configuration | verify (tuned) | held-out dram | held-out FinFET |
|---|---|---|---|
| baseline mis-lock | 25.0% | 20.0% | 30.0% |
| + top-K + PADM + centre rule | **20.0%** ✅ | **26.7%** ❌ | **43.3%** ❌ |
| + sub-pixel + drift correction | 25.0% | 20.0% | 30.0% |

PADM improved the split it was tuned on by 5 points and made **both** held-out splits worse — by 6.7
points on dram and **13.3 points on FinFET**. Its blend weight and spectral bandwidth were fitted to
one lattice geometry and did not survive a change of pitch or architecture.

**Consequences.**

1. **The "20% mis-lock, 78% sub-pixel" headline is withdrawn.** It was an overfitting artefact. The
   honest mis-lock rate is baseline-level: 25% / 20% / 30% across the three splits.
2. **PADM is disabled by default.** It stays in the codebase and the ablation table as a measured
   negative result rather than being deleted (R9).
3. **Runtime improved as a side effect:** removing PADM's FFT decompositions took the pipeline from
   224 ms to **50 ms**, a 4.5× speedup that directly helps the runtime component of the 50% bucket.
4. **The mis-lock problem is completely unsolved**, and is now the only thing capping the score.

**Why the surviving stages transfer, and PADM did not.** This is the structural point worth
carrying forward. Sub-pixel refinement and drift correction **never touch candidate selection** —
they adjust a coordinate after a location has been chosen. They are therefore *strictly additive*:
they cannot convert a correct pick into a wrong one, and the mis-lock rate is identical to baseline
on all three splits. PADM, by contrast, **re-ranks**, so a mistuned scoring function actively
destroys correct answers. Refinement fails gracefully; re-ranking fails destructively.

**What this means for the planned learned re-ranker.** It cuts both ways. Hand-designed re-ranking
demonstrably failed, which strengthens the case for learning it. But PADM's failure is a warning
about exactly this class of component: **any re-ranker must be validated on held-out architectures
before it is believed**, and it should be gated so that low confidence falls back to the argmax
rather than overriding it.

**The process lesson.** This was caught only because held-out splits were generated *before* the
result was trusted. Single-split evaluation would have reported 20% mis-lock and 78% sub-pixel into
the deck, and the sponsor's evaluation set would have quietly disagreed.

---

## 12h. The sponsor's DRAM presets are not actually distinct

Found incidentally while building the held-out splits: `dram_dense`, `dram_loose` and `dram_legacy`
produce **byte-identical images** (verified by md5 of the reference PNGs).

**Cause.** `generate_fine_canvas_zoned` passes only `preset["kind"]` into `generate_zone_canvas`.
In that zoned path — which is the default — every DRAM preset collapses to the same generator, and
the carefully specified pitch, width and contact-diameter values in `presets.py` are never used.
Only `dram` versus `finfet` changes anything.

**Consequences.**

1. The sponsor's generator offers far less diversity than its twelve preset names suggest. Our
   "held-out dram" split differs from the tuned split only by seed, not by geometry.
2. Genuine variation in pitch, feature size and CD has to come from **our own generator**, which
   raises its value further.
3. Any robustness claim based on "tested across six DRAM presets" would be false. Worth knowing
   before writing it in a slide.

---

## 14. Rotation and scale — the untested axis, opened up (12 Aug, MacBook Air M2)

Full narrative in `docs/WORKLOG.md`; decisions in ADR-0014…0019. Summary of experiments, with the
negatives kept in full per R9:

| # | Experiment | Verdict | Effect |
|---|---|---|---|
| 13 | Shipped pipeline on our own rotated/scaled data | ❌ **total failure** | 95% mis-lock, 326 px median |
| 14 | Exact continuous forward operator (replacing `INTER_AREA`) | ✅ **enabling** | scale was quantised to ~1% steps; no pose search could work without this |
| 15 | Pose by reciprocal-lattice peak voting | ⚪ too imprecise | 1.21% median scale error vs a ~1% basin |
| 16 | Pose by log-polar Fourier–Mellin | ❌ biased | 3.49% median, **+2.07% bias** |
| 17 | Pose by coarse pyramid search | ✅ **shipped** | 0.72% median, +0.09% bias, 39 ms |
| 18 | Generator GT half-pixel convention | ✅ **bug fixed** | `dy = +0.503 ± 0.035` — a pure convention offset |
| 19 | Rotation-aware drift estimation | ✅ partial | removed `dx = −9.5·rotation°`, but needed rotation to 0.05° |
| 20 | **Two-axis drift cancellation** | ✅✅ **decisive** | sponsor median 1.155 → 0.297; dev 0.768 → 0.497 |
| 21 | Coarse-level consensus re-ranking | ❌ **harmful** | mis-lock 20% → 55% |
| 22 | Pose bracket at half resolution (speed) | ❌ **harmful** | 2× faster, mis-lock 27.5% → 45% |
| 23 | Per-mat pitch randomisation in our generator | ❌ **removed** | unphysical; pushed scale estimation from 0.69% to 4.1% error |

### 14a. The result worth putting on a slide: drift and rotation are separable by symmetry

The blind drift correction was the previous session's biggest win, and on rotated data it turned
*destructive* — because **a tilted field of view and a drifting raster produce the same row-to-row
displacement**. The estimator measured their sum and could not split it. Subtracting a rotation
*estimate* does not rescue it: an error of δ degrees becomes `tan(δ)·(H−1)` pixels of shear, so our
0.43° pose accuracy turned a 1.5 px correction into a 7 px error. Measured, every variant of that
idea was worse than not correcting at all (dev median: uncompensated 9.60 px, Fourier–Mellin
rotation 1.705, clamped 0.896, **no correction 0.768**).

The fix came from asking what makes the two physically different rather than how to estimate one of
them better:

> **Drift is anisotropic. Rotation is isotropic.**
> The raster scans line by line, so drift displaces x as a function of y and leaves horizontal
> features horizontal. A rotation tilts *both* axes.

So run the identical row-shift measurement on the **transposed** image. Along columns the drift
contributes nothing and only the tilt survives, and for a square frame the two measurements simply
add, cancelling the rotation **exactly** rather than approximately:

```
rows   :  S_row = -(drift_rate + tan ρ)·(H−1)
columns:  S_col = +tan ρ·(W−1)
S_drift = S_row + S_col·(H−1)/(W−1)
```

No rotation estimate, no new parameter, and it restored the drift win on *both* regimes at once —
sponsor median 1.155 → **0.297** px (sub-pixel rate 15% → 67.5%) and dev 0.768 → **0.497** px.

### 14c. Maximum-likelihood re-ranking — right premise, wrong conclusion ❌

The thesis says this is an ML inverse problem, and until now every candidate had still been ranked
by ZNCC — which is the ML estimator only for *additive constant-variance* noise. Ours is
Poisson-then-Gaussian (H3). So we built the estimator the measured noise model actually calls for:
gain and offset profiled out in closed form per candidate, variance `α·prediction + β` with `(α, β)`
fitted from the search image itself. No tuned constants, deliberately (PADM died of two).

| Ranking | truth at rank 1 | mean rank of truth |
|---|---|---|
| ZNCC | **82.1%** | **2.62** |
| log-likelihood | 79.5% | 3.77 |

Improved the rank on 2 pairs, worsened it on 4; end to end mis-lock 20.0% → **22.5%**. Off by
default.

**Why it failed is more useful than the fact that it did.** The premise checks out — fitting the
noise model gives `α = 0.80`, so the noise is genuinely signal-dependent and ZNCC genuinely
mis-weights it. But photon noise is not what limits this comparison. The template is an *imperfect
prediction*: the PSF differs between acquisitions, drift is only partly removed, alignment is
sub-pixel at best. Those **model-mismatch** residuals are bigger than the shot noise and they are
structured, so weighting by photon variance sharpens the wrong term. ZNCC survives because it is
agnostic about magnitudes and asks only whether the shapes agree — the robust question when the
forward model is approximate.

> **The ML estimator for your noise model is not the ML estimator for your problem, unless the model
> mismatch is smaller than the noise.**

### 14d. Three re-rankers have now failed — and that is the case for the learned one

| Attempt | Idea | Result |
|---|---|---|
| PADM residual re-scoring | remove the lattice in Fourier, score the residual | overfit: −5 pts tuned, +6.7 and +13.3 held out |
| Coarse-level consensus | let the downsampled level vote | 20% → 55% mis-lock |
| Maximum-likelihood | rank by the measured noise model | 20% → 22.5% mis-lock |

Meanwhile the prize is now **measured on our own data**: at K=20 the true location is in the
candidate set on **39 of 40** dev pairs (97.5%), and ZNCC puts it first on 82.1%. **A perfect
re-ranker would take mis-lock from 20% to ~2.5%.** The correct answer is nearly always available
and hand-designed scoring has failed three times in three different ways — which is exactly the
quantitative argument for learning the re-ranker rather than designing it, with the hard
precondition from ADR-0012 that it must be validated on a held-out *architecture* and gated to fall
back to the argmax when unsure.

### 14b. The rule that came out of the failures

Experiments 21 and 22 failed for the same reason, and it is now a design rule:

> **Downsampling is free for measuring pose and ruinous for deciding identity.**

Pose is a global, low-frequency property — a 25×25 template measures it fine. Identity lives
entirely in the full-resolution aperiodic fingerprint, which downsampling destroys. Experiment 21's
specific error is worth remembering: downsampling does not widen the *field of view*, so the
reference's 1000 nm footprint never contains a 2600 nm mat boundary at any resolution. There was no
landmark to reveal.

---

## 15. Solving the mis-lock: five experiments, one that worked ✅

Mis-lock had been the binding constraint since Stage 4. Precision was solved; selection was not.
Three re-rankers had already failed (PADM, coarse consensus, maximum-likelihood). This section is
the round that broke it.

### 15a. First: is it even an ambiguity problem? (the diagnostic that redirected everything)

The bench results stratified by pose looked alarming:

| rotation band | mis-lock | | scale band | mis-lock |
|---|---|---|---|---|
| −0.04 .. 0.60° | 14% | | 9.01 .. 9.61 | 25% |
| 0.60 .. 1.88° | **62%** | | 10.5 .. 11.0 | **50%** |

That is not the signature of periodic ambiguity — it looks like **pose estimation failing**, which
would need a completely different fix. So: hand the matcher the true scale and rotation from the
manifest and see what happens.

**First attempt said oracle pose was WORSE (60% vs 33.3%), which is impossible.** A correct pose
cannot hurt. The oracle was wrong: I passed `−rotation`. Measuring the peak ZNCC at `+R` against
`−R` settled it — the template wants **`+R`**. The convention had been `−R` before the forward
operator was rewritten, and it flipped with the rewrite. **Remembering a convention instead of
measuring it cost an hour and nearly produced a completely wrong conclusion** (rule R7).

With the correct sign:

| split | shipped pose | oracle pose | pose failures |
|---|---|---|---|
| bench | 33.3% | 33.3% | 2 of 10 |
| holdout FinFET | 33.3% | **43.3%** | 2 of 10 |

**Pose is not the bottleneck.** A perfect pose leaves mis-lock unchanged on bench and makes FinFET
*worse* — because the searched pose sometimes fits better than the true one, absorbing drift and
distortion the true pose does not. The apparent rotation correlation was confounding, not causal.
It is genuine ambiguity.

### 15b. Candidate-consensus periodic cancellation — mixed ⚪

**Idea.** The top-K candidates are, by construction, different repeats of *the same lattice*. Their
average therefore estimates what they have in common — the periodic part — **from the search image
itself, with no bandwidth, no lattice fit and no tuned constant**. Subtract it (leave-one-out, so a
candidate never cancels itself) and what remains is the aperiodic fingerprint.

This is what PADM was trying to do, without PADM's two tuned parameters — and those parameters were
exactly what made PADM overfit.

**Result.** dev 20.0% → 12.5%, bench 26.7% → **30.0%**, FinFET 33.3% → 30.0%. Net 26 → 23 mis-locks
across 100 pairs. Real but not decisive, and it *hurts one split* — the same shape as PADM. Not
shipped.

### 15c. Per-candidate pose refit — the one that worked ✅✅

**The reasoning that produced it.** On a pure information argument, ZNCC should already separate the
true location from its impostors easily: the measured margin is ~0.016, and sampling noise on a
100×100 correlation at ρ≈0.9 is ~0.002. That is a signal-to-noise ratio near **8**, which should mean
almost no mis-locks. We measured 28%.

So the noise that actually decides the ranking **is not photon noise** — it is model mismatch. The
maximum-likelihood re-ranker had already said this from the other direction (§14): weighting by
photon variance sharpened a term that was not the limiting one.

If mismatch is what dominates, the fix is not a cleverer score — it is **less mismatch**. The global
pose is a compromise fitted across the whole search image, but drift accumulates over the scan and
distortion varies with field position, so the locally-best pose differs from candidate to candidate.
Scoring them all at one shared pose handicaps them *unequally*.

**So: re-score every candidate at its own best pose.**

| split | shipped | + refit | change |
|---|---|---|---|
| dev (tuning) | 20.0% | **12.5%** | −7.5 pts |
| bench | 33.3% | **26.7%** | −6.6 pts |
| holdout FinFET | 33.3% | **20.0%** | **−13.3 pts** |
| **all 100 pairs** | **28.0%** | **19.0%** | **−32% relative** |

Precision improved too (bench median 0.556 → 0.504 px, FinFET 0.706 → 0.639).

**Why this generalises when three re-rankers did not.** It is re-**scoring**, not re-**ranking**. No
new criterion, no blend weight — the comparison is still ZNCC, just measured at each candidate's own
optimum rather than at a compromise. It *removes an unequal handicap* rather than introducing a
preference, which keeps it on the safe side of ADR-0012. The largest gain landing on the held-out
architecture is the signature of a real effect rather than a fitted one.

### 15d. Two variants that failed badly ❌

**Ranking by the score *gain* when the pose is freed** — the intuition being that only the true
location has a fingerprint to bring into register, so only it should improve much.
**80–92% mis-lock.** Exactly backwards: *impostors* gain more, because they start with more
mismatch and therefore have more to absorb. The gain measures how wrong a candidate was, not how
right it can become.

**Consensus cancellation applied to the refitted patches** — the principled-looking combination:
remove the mismatch first, then compare fingerprints. **40–53% mis-lock.** Refitting re-registers
each patch to its own frame, so the consensus average is then taken over patches that are no longer
in a common frame, and the "periodic component" it estimates is blurred nonsense.

### 15e. A 6× speedup with no accuracy cost

The first working implementation cost **2250 ms per pair** — unshippable against a 300 ms target.
The cause was structural, not algorithmic: the template depends only on `(scale, rotation)`, **not**
on which candidate is being scored, but the natural loop nesting (candidate outer, pose inner)
rebuilds the same few templates once per candidate. Template construction — box-integrating a
1000×1000 reference and warping it — dominates everything else here.

Grouping candidates by pose and building each template once per group: **2250 ms → 430 ms**,
identical results.

One trap on the way: centring a single shared pose grid on the top candidate ran fast and **silently
erased the entire effect** (back to 20.0/33.3/33.3). Candidates arrive from *different* poses in the
bracket, so each genuinely needs a grid centred on its own. A performance optimisation that quietly
deletes the result it was optimising is precisely why every change is re-measured rather than
assumed correct.

Final tuning: `refit_steps=2` matches `steps=3` exactly (19.0% both) at **316 ms against 433 ms**.

---

## 16. The closest-to-centre rule: why a MANDATED rule cannot help here ✅

The problem statement requires it — *"if several valid matches exist, select the one whose centre is
closest to the search-image centre"* — and the submission checklist lists it explicitly. It had been
disabled because it nearly doubled the mis-lock rate. That is an uncomfortable place to leave a
mandated requirement, so it was worth understanding rather than working around.

### 16a. The threshold was genuinely wrong

`tau`, the score window defining a "tie", was `0.25 × std(candidate scores)`. But the candidate set
spans the **entire search image**, so its scores run from ~0.9 down to ~0.3 and that spread gives
**tau ≈ 0.037** — more than **twice** the 0.016 median margin between the winner and its best rival
(H8). The rule was declaring clearly-worse candidates "tied" and then deciding between them on
proximity to the centre.

**Fixed by deriving the threshold from measurement noise instead of from the spread of an arbitrary
set.** The sampling standard error of a correlation coefficient ρ over N pixels is ≈ `(1−ρ²)/√N`;
candidates closer than about two of those are genuinely indistinguishable, and anything further
apart is not a tie at any confidence. Nothing is tuned — N is the template footprint, ρ the winning
score.

Effect of the fix alone: **23.3% → 43.3% became 19.0% → 18.0%** on the three splits first tested.

### 16b. But it still costs accuracy — and the reason is not a bug

| split | rule off | rule on (corrected tau) |
|---|---|---|
| sponsor | **25.0%** | 35.0% |
| bench | 30.0% | **26.7%** |
| holdout FinFET | **16.7%** | 20.0% |
| **all three** | **24.0%** | 28.0% |

*(An earlier round tested only bench/FinFET/dev and looked neutral. Adding the sponsor split — the
one that most resembles the evaluation data — reversed the conclusion. A stage must be checked on
every split, not on a convenient subset.)*

**The rule encodes a deployment prior that the benchmark does not contain.** In the real scenario it
was written for, a tool has drifted only slightly from a site it meant to revisit, so the target
genuinely *is* near the centre of the search image, and among equally-scoring candidates the central
one is the likely one. Both benchmarks instead place targets **uniformly**:

| split | median GT distance from centre | uniform draw predicts |
|---|---|---|
| sponsor | 373 px | 358 px |
| bench | 335 px | 358 px |
| holdout FinFET | 347 px | 358 px |

The observed distances match the uniform expectation. **The prior the rule depends on is simply
absent from the test data**, so every time the rule fires it is a coin flip that can only lose.

**Conclusion, and it is a position rather than an omission.** The rule is implemented, tested,
reachable via `centre_rule=True`, and now has a statistically defensible tie threshold — the
checklist asks that it be implemented and it is. It is **off by default** because the benchmark's
uniform target sampling removes the assumption it rests on. On data that reflects the deployment
scenario it was designed for, it should pay; on this data it cannot, and we can show why with a
measurement rather than an assertion.

### 16c. Raising K does not help either

Candidate recall, measured correctly this time (merging candidates across all poses, as the pipeline
actually does — an earlier measurement kept only the winning pose's list and understated it):

| split | K=10 | K=20 | K=40 |
|---|---|---|---|
| bench | 90% | 93% | 97% |
| holdout FinFET | **100%** | 100% | 100% |

**FinFET has perfect candidate recall at K=10 and still mis-locks 16.7% of the time** — so on that
split, *every* remaining failure is a ranking failure and a perfect re-ranker would reach zero.
Raising K to 20 changes the mis-lock rate not at all (23.3% either way on bench + FinFET) while
costing runtime, because the refit ranking cannot use the extra candidates. Recall is not the
constraint; discrimination is.

---

## 17. Attacking mis-lock from first principles ✅✅

Rather than trying another scorer, this round started from two questions: **what actually
distinguishes the true cell from an impostor**, and **what noise is actually limiting us**.

Only four things distinguish cell (i,j) from cell (i+m, j+n): the accumulated random-walk deviation
of line positions, per-line width jitter, per-contact radius jitter, and mat boundaries. The
dominant one is **geometric** — where the lines sit relative to a perfect grid.

### 17a. A wrong hypothesis, and what it taught ❌

The reasoning was: the limiting noise is model mismatch, which is *photometric* (PSF, apodisation,
gain), and every scorer we compare with uses *amplitudes*. So compare something photometrically
invariant instead.

Two implementations, both worse than the argmax they replaced:

| method | dev | bench | holdout FinFET |
|---|---|---|---|
| argmax | 20.0% | 26.7% | 33.3% |
| lattice-phase fingerprint | 32.5% | 26.7% | 43.3% |
| gradient-orientation correlation | 27.5% | 36.7% | 40.0% |
| orientation, magnitude-weighted | 22.5% | 46.7% | 50.0% |

**The premise was wrong, and being wrong was the useful part.** The stage that actually fixed
ranking was a **pose** refit — a *geometric* correction. So:

> **The mismatch is geometric. The evidence is photometric.**

Photometric invariance discards the evidence while leaving the actual mismatch untouched, which is
exactly backwards. This explains *why* the refit worked rather than merely recording that it did,
and it says the direction with headroom is **removing more geometric mismatch**, not inventing
features.

### 17b. Following that: a real bug in the drift estimator ✅✅

The drift is a **shear** — the most obvious remaining geometric distortion. Testing whether
un-shearing the image (rather than correcting the coordinate afterwards) helps selection produced a
strange split: FinFET 33.3% → 16.7%, but bench 26.7% → **36.7%**. The diagnostic printed alongside
it gave the answer: mean estimated shear on bench was **6.98 px** where the truth is 1.5.

Measuring the estimator against known truth:

| split | true | est mean | est **sd** | median abs error |
|---|---|---|---|---|
| dev | 1.50 | 1.20 | 1.12 | 0.66 |
| bench | 1.50 | −1.01 | **17.75** | 0.49 |
| holdout FinFET | 1.50 | 1.01 | 0.93 | 0.81 |

Median error was fine; the **standard deviation was catastrophic**. And on bench,
`corr(|rotation|, |shear error|) = +0.433`, with median error 0.25 px below 0.5° against **1.50 px
above 1°** — six times worse.

**The bug.** `DEFAULT_GAP = 100` and `DEFAULT_MAX_LAG = 3`. A 2° rotation displaces content by
`100·tan(2°) = 3.49 px` per row-pair — **outside the ±3 lag search entirely**. The correlation peak
clipped at the edge of its own search window and the measurement saturated. The "exact" two-axis
rotation cancellation was not exact because **its inputs were clipped before it ever ran**.

**The constraint, derived rather than tuned.** The row separation is pinned between two bounds:

```
gap·tan(ρ_max) + |drift|   <   max_lag   <   lattice_pitch / 2
\______________________/                     \_______________/
 must be able to SEE the        beyond this the correlation locks onto
 displacement without clipping   the NEXT lattice line
```

The DRAM word-line pitch is ~6.4 search px, so the upper bound is ~3.2. At gap=100 the lower bound
is 5 — **there is no valid `max_lag` at that gap.** The configuration was infeasible.

Sweeping confirms both failure modes exactly as predicted:

| config | dev sd | bench sd | FinFET sd |
|---|---|---|---|
| gap=100, lag=3 (was) | 0.6 | **13.3** | 0.6 |
| gap=100, lag=5 | **16.5** | **19.2** | 0.5 |
| **gap=40, lag=3** | **0.6** | **0.6** | **0.8** |

Widening the lag to 5 makes it *worse* — 5 > pitch/2, so it aliases onto the neighbouring lattice
line. Both bounds are real.

### 17c. Deriving the gap from the measured rotation ✅

A fixed gap forces a choice between regimes: short is required when the field is tilted, long is
better when it is not (the estimate is divided by `(H−1)/gap`, so a longer baseline amplifies noise
less). We already measure rotation, so the constraint can simply be solved:

```
gap  <  (max_lag − drift) / tan(ρ)      → 43 at 2°, uncapped as ρ → 0 (capped at 100)
```

**The formula returns 43 at 2°, where the empirical sweep put the optimum at 40** — derivation and
measurement agree independently, which is the reason to trust either.

### 17d. Result

| split | before | after | median | pass@0.5px |
|---|---|---|---|---|
| sponsor | 25.0% | 25.0% | 0.297 | 67.5% → **68%** |
| bench | 30.0% | **23.3%** | 0.509 → **0.343** | 50% → **63%** |
| holdout FinFET | 16.7% | **16.7%** | 0.587 → **0.313** | 33% → **63%** |
| **total mis-lock** | **24/100** | **22/100** | | |

The headline is precision rather than mis-lock: **sub-pixel pass rate across all 100 pairs rises
from 50 to 65**, and FinFET's nearly doubles. bench mis-lock falls 6.7 points.

A fixed gap=40 scores marginally better on mis-lock (21/100) but clearly worse on precision (60/100
sub-pixel). We ship the **derived** rule over the **fitted** constant: it performs better where it
matters most, and a rule that follows from the constraint should survive a rotation range we have
not tested, whereas a fitted constant has no reason to.

---

## 18. Three flaws found by an external review, and one it got wrong

An external review of the full experiment trail flagged several things. Two were real and are fixed
here; a third was factually wrong and acting on it would have been actively harmful. All three are
recorded, because a review is evidence to be checked rather than instructions to be followed.

### 18a. The documentation carried three generations of numbers at once ❌ → ✅

The most important catch. At one point:

| source | sponsor | bench | FinFET |
|---|---|---|---|
| `results/` (actual) | 25.0% | 23.3% | 16.7% |
| `RESULTS.md` headline | 27.5% | 33.3% | 33.3% |
| `PROGRESS.md` (one place) | 27.5% | 33.3% | 33.3% |
| `PROGRESS.md` (another) | 25.0% | 30.0% | 16.7% |

A judge browsing the repository would have found the project contradicting itself, which is worse
than any single number being unflattering.

**The root cause was a gap in our own tooling, not carelessness.** Rule R2 was enforced for the deck
— which is generated from `results/` and checked by `verify_submission.py` — but *not* for the
markdown, which was hand-maintained. A hand-maintained results document drifts by construction,
because it is updated by discipline rather than by the build.

**Fix:** `scripts/make_results_doc.py` generates the headline block of `RESULTS.md` from `results/`
between explicit markers, stamped with the date and commit. The analysis and reasoning around it stay
hand-written; only the numbers are generated.

### 18b. Runtime was being measured in a way that made splits incomparable ❌ → ✅

Regenerating the headline immediately exposed something the review did not catch: runtimes of
**1228 / 1190 / 354 ms** across the three splits *from a single batch of identical code*. The
accuracy run walks the splits sequentially over many minutes, so the machine's thermal drift — which
we had already documented as up to 3× — was being charged to whichever split happened to run last.

**Fix:** `scripts/benchmark_runtime.py` measures runtime separately from accuracy, with warm-up
calls discarded and the splits **interleaved round-robin**, so drift is spread evenly across them
rather than landing on one. Re-measured properly, the three splits agree: **1211 / 1232 / 1273 ms**.
The earlier 354 ms was an artefact of measurement order, not a genuinely faster split.

### 18c. The review's H100 claim was wrong, and following it would have been harmful ⚠️

The review stated that "the official page says KLA's benchmarking team will run the inference script
on an H100", and concluded that the CPU-only constraint could be relaxed in favour of GPU batching
and CUDA components.

**That belongs to the KLA PS01 restoration problem, not Applied Materials Drift-Sense.** Our extracted
spec (`docs/SPEC.md`) contains no GPU or H100 requirement; it says the runtime environment "will take
precedence when released", i.e. it is *not yet specified*. Building a CUDA dependency on that basis
would have risked the single failure mode that eliminates teams outright — a script that does not run
on the evaluator's machine.

The CPU-only path stays. This is exactly why R1 and R3 exist: a confident claim about a source is not
a fact until someone opens the source.

**Re-raised on 14 Aug by a second external review, and settled definitively.** The claim came back
with a citation this time, so both sources were opened rather than argued about:

| Source | Says |
|---|---|
| `reference/AMAT_DriftSense_ProblemStatement.pdf`, all 7 pages | **zero** occurrences of "H100", "GPU" or "CUDA". The only "hardware" mentions require *us* to state ours: *"Runtime per image pair, with hardware, Python version and timing method."* |
| The cited hackathon page, fetched | *"…used AS-IS by KLA's benchmarking team to measure your model's quality scores and inference time on the H100 GPU"* — inside the section for the **KLA track, Problem Statement 1 (AI-Based Restoration of Degraded Images)**. For the Applied Materials Drift-Sense track, no GPU is named. |

So the H100 is real, and it belongs to a **different problem statement in the same hackathon**. The
sentence is quotable and looks decisive, which is exactly what makes it dangerous second-hand.

The consequences of having followed it would have been severe and one-directional: our own
constraints require the submission to run with **no network access, no model downloads, and weights
committed in-repo**, and `torch` must remain optional (`pip uninstall torch` leaves every graded
command working). A CUDA dependency, or a multi-hundred-megabyte learned matcher fetched at build
time, trades a working submission for a faster one on hardware nobody has told us we get.

**Decision: CPU-only stands, `torch` stays optional, no GPU work.** Recorded at this length because
the claim has now cost time twice, and the next person to raise it should be able to close it in one
minute rather than one afternoon.

*Sharper form of the general rule:* **a citation that is accurate about the wrong scope is more
dangerous than one that is simply wrong**, because checking it superficially confirms it. The
question to ask is never "does the source say this?" but "does the source say this *about us*?"

---

## 19. A 4x speedup with bit-identical results ✅

Having made runtime measurable, the profile was surprising:

| stage | cumulative | marginal |
|---|---|---|
| baseline (argmax only) | 39 ms | — |
| + sub-pixel + drift | 376 ms | **337 ms** |
| + pose search | 695 ms | 319 ms |
| + candidate refit | 736 ms | **41 ms** |

**The per-candidate refit — the stage assumed to be expensive — costs 41 ms.** The drift estimator
cost 337 ms, and not for arithmetic reasons: it ran a Python loop over ~192 row-pairs × 2 axes × 7
lags, roughly 2700 tiny dot products through the interpreter. The work is trivial; the overhead was
the cost.

Vectorising it — all row-pairs at once for each lag, via `einsum` — gives **1232 ms → 309 ms on
bench**, with mis-lock (23.3%), median (0.343 px) and pass@1px (73%) **all unchanged to the digit**,
because it computes the same dot products in the same order.

That brings the pipeline to our own 300 ms target, from 4× over it, without trading a single point of
accuracy. The lesson generalises: **profile before optimising, and before assuming which stage is
expensive** — the intuition here was wrong by an order of magnitude.

### 19a. The benchmark heats the machine it is measuring (14 Aug) ⚠️

Two further methodological faults surfaced when runtime was re-measured on a laptop that had been
running generation for hours.

**The baseline is a control, and it was being discarded.** It performs a fixed, simple computation,
so its runtime is a direct proxy for how fast this machine currently is. Measured across three
states in one day:

| machine state | baseline p50 | DriftLock p50 | **ratio** |
|---|---|---|---|
| quiet | 20 ms | 400 ms | **20.0×** |
| loaded | 34 ms | 630 ms | **18.5×** |
| throttled | 67 ms | 1262 ms | **18.8×** |

The absolute figures move by 3×; the ratio does not. `benchmark_runtime.py` now records the ratio and
**refuses to certify absolute milliseconds** when the control sits more than 50% above its
quiet-machine value, writing `absolute_ms_representative` into `results/runtime.csv`. The generated
README and RESULTS blocks read that flag and print a visible warning rather than quoting a number
that is a property of one afternoon's thermal state.

**The ratio's denominator was itself noisy.** Dividing each split's median by *that split's own*
baseline median seemed natural and was wrong: the baseline does the same work on every split, so its
per-split medians differ only by sampling noise, and a noisy denominator injects exactly the noise
the ratio exists to remove. On a recovering machine that produced ratios of **13.5 / 25.4 / 22.7**
for three splits whose true cost is identical to within a few percent — which would have been
published as sponsor running twice as fast as bench. Pooling the denominator across all 36 baseline
samples restores 19.1 / 17.6 / 17.4.

**And the measurement is self-heating.** Running the benchmark on a rested machine drives the
baseline from 36 ms back to 67 ms within the run. On this hardware the absolute number is close to
unobtainable during an active session, which is not a reason to quote it anyway — it is the reason
the ratio is the reported quantity and the gate exists.

### 19b. Certified — and the control had a blind spot it could not see past ✅

Measured on a genuinely cold machine, and the result was not what the gate expected.

| run | baseline (control) | DriftLock p50 | p95/p50 | gate |
|---|---|---|---|---|
| first, from idle | 20–24 ms | **577–629 ms** | 1.28 | **passed** |
| second, steady state | 19–20 ms | **388–406 ms** | 1.10 | passed |

**The control read clean both times while the measurement moved by 1.6×.** The reason is structural:
the baseline runs for ~19 ms and a DriftLock call for ~400. A short task can complete entirely
inside the CPU's boost window while a long one drops into the sustained-clock regime — so a 19 ms
control is *incapable* of observing the regime the 400 ms measurement lives in. Counter-intuitively
the **first heavy run after idle is the unreliable one**, which is the opposite of the assumption
the gate was built on.

Ruling out the alternative first: a paired same-session comparison of the current configuration
against the pre-median-filter one gave 390.6 ms and 392.1 ms with the baseline at 19.4 ms — ratio
20.1×, exactly the historical figure. The code had not become slower, and the median filter is free
(a separate microbenchmark confirms `medianBlur` costs ~1 ms and gives bit-identical output on
uint8 and float32 input). The 1.6× was entirely measurement.

What *did* separate the two runs was the dispersion of the measurement itself — p95/p50 of 1.28
against 1.10. A steady machine produces a tight distribution regardless of its absolute speed, so
`benchmark_runtime.py` now gates on that too. It catches precisely the instability the baseline
control structurally cannot.

**Certified figures, both gates passing:** sponsor 406 ms, bench 397 ms, holdout FinFET 391 ms,
against a 19–20 ms baseline — a ratio of ~20×, which is the same ratio measured across every machine
state this project has seen. The absolute numbers and the ratio finally agree, which is the point of
having run both.

---

## 20. Six re-ranking attempts, one rule ✅ (the strongest conclusion in the project)

Two further experiments were run specifically to attack mis-lock. Both failed, and with them the
picture is now unambiguous enough to be stated as a result rather than a running tally.

### 20a. Penalising pose excursion in the refit — no effect ⚪

**Reasoning.** Ranking by score *gain* when the pose is freed failed at 80–92% because impostors
start with more mismatch and have more to absorb (§15d). The same asymmetry should leak into the
plain maximum: a wrong candidate could buy a high score with a large pose excursion the true one
never needs. So charge each candidate for how far it had to move.

**Result**, swept on `dev` only (R5), penalty in units of the search span:

| penalty | 0.0 | 0.002 | 0.005 | 0.01 | 0.02 | 0.05 |
|---|---|---|---|---|---|---|
| dev mis-lock | **12.5%** | 12.5% | 12.5% | 12.5% | 20.0% | 20.0% |

No gain at any setting, and harmful above 0.01. **The loophole does not exist**: the winning poses
already sit near the centre of the bracket, so there is nothing to penalise. Kept in the code at 0
with the reasoning recorded; the hypothesis was reasonable and the measurement says no.

### 20b. Tie-break by aperiodic residual — harmful ❌

**Reasoning.** The candidate-consensus residual helped dev and FinFET but hurt bench when used as a
*global* re-ranker (§15b). Perhaps the problem was not the signal but *when it is allowed to act*:
let it decide only among candidates that are statistically indistinguishable on the primary score,
reusing the tie threshold derived for the centre rule (§16a). No blend weight, and gated so it
cannot override a clear winner — exactly the shape ADR-0012 says a safe stage should have.

**Result:**

| split | refit only | + residual tie-break | tie fired on |
|---|---|---|---|
| dev | 12.5% | 12.5% | 20/40 |
| sponsor | 22.5% | **30.0%** | **38/40** |
| bench | 20.0% | **23.3%** | 18/30 |
| holdout FinFET | 16.7% | **20.0%** | 17/30 |
| **held-out total** | **20.0%** | **25.0%** | |

**Why, and it is worth knowing:** the tie test fires on **38 of 40 sponsor pairs**. The refit
*compresses the score distribution* — that is what it is for — so after it runs, a threshold derived
from correlation sampling noise declares almost everything tied. A weak residual signal then decides
nearly every pair, and it decides badly. **A gate calibrated before a stage runs is not calibrated
after it.** The same caution applies to the centre rule, which shares that threshold.

### 20c. The rule these six experiments establish

| # | Attempt | Kind | Result |
|---|---|---|---|
| 1 | PADM residual scoring | new criterion | overfit — helped tuned split, hurt both held-out |
| 2 | Coarse-level consensus | new criterion | harmful (62.5% on sponsor) |
| 3 | Maximum-likelihood (Poisson–Gaussian) | new criterion | no gain; mismatch > photon noise |
| 4 | Refit-*gain* ranking | new criterion | catastrophic (80–92%) |
| 5 | Lattice-phase / gradient-orientation | new criterion | harmful (up to 50%) |
| 6 | Residual tie-break, gated | new criterion | harmful (20.0% → 25.0%) |
| ✅ | **Per-candidate pose refit** | **same criterion, better geometry** | **28.0% → 19.0%, every split** |

> **Every attempt to re-rank candidates by a NEW criterion has failed. The only stage that worked
> re-scores by the SAME criterion at a better geometry.**

Six independent failures and one success, across three splits and two architectures, is no longer a
run of bad luck — it is the shape of the problem. At dose 200 and 10 nm/px sampling the aperiodic
fingerprint carries too little information to support *any* hand-designed discriminator we have
found, while reducing geometric mismatch pays every time it is tried.

**So we stop here rather than trying a seventh.** Continuing to guess at criteria, given this
evidence, would be poor judgement rather than persistence. If mis-lock is to fall further, the
evidence points at *more geometric mismatch removal* — a richer local deformation model, or a learned
component trained to reduce mismatch rather than to score similarity — not at another scoring
function.

**What this is worth in the submission.** The failure-analysis bucket is 10% of the score and asks
specifically about repeated-pattern ambiguity. A single measured principle supported by six
independent negative experiments is a considerably stronger answer than a seventh attempt would have
been, whether or not it worked.

---

## 21. Geometric headroom exists — and it costs 3× runtime to reach ⚖️

After ADR-0024 closed the door on new scoring criteria, the open question was whether *geometry* had
anything left. It does, and the shape of the answer is a clean accuracy/runtime frontier rather than
a free win.

### 21a. Pose-regime routing — refuted ❌

An external review proposed that on nominal 10:1 data the extra pose hypotheses are distractors, so
routing to fewer poses should help. My own ablation was suggestive: pose search takes sponsor from
25.0% to 27.5%, and only the refit claws it back.

Measured directly — candidates from all poses merged, versus candidates from the single best-scoring
pose:

| split | merge all poses | best pose only |
|---|---|---|
| sponsor | **22.5%** | 27.5% |
| bench | **20.0%** | 36.7% |
| holdout FinFET | **16.7%** | 26.7% |
| **total** | **20.0%** | **30.0%** |

**Restricting poses is far worse.** The extra hypotheses are not distractors — they are *recall*.
Routing on that basis is a dead end.

*(The review also reported a bug in this experiment, claiming the comparison used `g.score` on a
list. The code reads `g[0].score`, and `extract_peaks` returns candidates sorted descending, so that
is exactly `max(c.score for c in g)`. The comparison was fair.)*

### 21b. A wider refit genuinely helps ✅

| refit span / steps | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|
| **.006 / .3, 2 steps** (shipped) | 12.5% | 25.0% | 23.3% | 16.7% | **22.0%** | **297 ms** |
| .03 / 1.5, **3** steps | 20.0% | 25.0% | 23.3% | 30.0% | 26.0% | 441 ms |
| **.03 / 1.5, 5 steps** | **10.0%** | **22.5%** | **20.0%** | 16.7% | **20.0%** | 886 ms |
| .05 / 2.0, 5 steps | 17.5% | 25.0% | 20.0% | 23.3% | 23.0% | 895 ms |

Two points matter here. The wide span improves **both** the tuning split and held-out, which is the
signature of a real effect. But **span and step count interact**: the same wide span sampled with 3
steps instead of 5 is *worse than not widening at all* (26.0% vs 22.0%). The optimum lies **between**
coarse samples, so a wide span is only useful when sampled densely — and that density is the cost.

### 21c. Interpolating the pose between samples — failed ❌

The obvious escape: the grid scores already describe the local shape, so fit a parabola per axis,
evaluate once at its vertex, and get dense-grid accuracy from a coarse grid. This is exactly the
sub-pixel peak-fitting argument applied to pose instead of position, and it costs one extra
correlation instead of sixteen.

| config | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|
| dense .03/1.5 s5 | 10.0% | 22.5% | 20.0% | 16.7% | **20.0%** | 886 ms |
| wide s3 + interpolation | 20.0% | 30.0% | 30.0% | 20.0% | **27.0%** | 559 ms |
| wide s4 + interpolation | 20.0% | 27.5% | 23.3% | 23.3% | **25.0%** | 785 ms |

Worse than both the dense grid and the shipped narrow one. **A parabola through three widely
separated samples interpolates across basins rather than within one** — the same reason the coarse
wide grid failed. Interpolation cannot rescue a grid that is too coarse to resolve the structure it
is sampling; it needs three points on *one* peak, and a wide coarse grid does not provide them.

### 21d. The decision, and why

The frontier is real:

| | held-out mis-lock | p50 runtime |
|---|---|---|
| **shipped (narrow refit)** | 22.0% | **297 ms** |
| dense wide refit | **20.0%** | 886 ms |

**We ship the narrow configuration.** The spec weights *"coordinate accuracy on sponsor test data
**and computation time**"* in one 50% bucket, and on sponsor specifically the dense configuration
buys **one pair out of forty** (25.0% → 22.5%) for a **3× runtime cost**. That is a poor trade
against the metric that is actually scored.

*(Wording corrected: this is a frontier for the current optimization strategy, not a property of the
problem. See §22 — we measured that this implementation needs 3× runtime, not that the task does.)*

The dense configuration is kept in the ablation as a measured operating point, not deleted. A
quantified accuracy/runtime frontier is a more useful thing to hand a reader than a single arbitrary
point on it, and if the released evaluation environment turns out to be generous about runtime, the
better-accuracy configuration is one flag away.

---

## 22. Multi-basin refinement — and the reason all three shortcuts fail ❌

An external review argued, correctly, that both earlier attempts to exploit a wide refit span share
one flaw: they assume the pose surface has a **single basin**. A coarse grid takes its highest
*sample*, which can sit in the wrong peak; and a parabola fitted across widely separated samples
interpolates *between* peaks rather than within one. Its proposal — retain several distinct local
maxima and refine inside each — is precisely targeted at that mechanism.

Implemented as non-maximum suppression in `(scale, rotation)` space (a sample qualifies only if it
beats its four neighbours, so it finds *basins* rather than the top-N samples, which usually all
belong to one peak).

| config | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|
| narrow, 2 steps (shipped) | 12.5% | 25.0% | 23.3% | 16.7% | **22.0%** | **308 ms** |
| dense wide, 5 steps | 10.0% | 22.5% | 20.0% | 16.7% | **20.0%** | 850 ms |
| multi-basin, 3 steps, 2 basins | 20.0% | 25.0% | 23.3% | 30.0% | 26.0% | 441 ms |
| multi-basin, 3 steps, 3 basins | 20.0% | 25.0% | 23.3% | 30.0% | 26.0% | 441 ms |

Worse than both, and **identical for 2 and 3 basins** — the third basin never fires, because a 3×3
grid rarely contains three distinct local maxima. It also lands on exactly the same 26.0% as the
plain coarse-wide grid, i.e. basin retention changed nothing at all.

### The general result

Three independent attempts to get dense-grid accuracy out of a coarse grid:

| method on a coarse wide grid | held-out |
|---|---|
| take the best sample | 26.0% |
| parabola interpolation | 27.0% |
| multi-basin retention | 26.0% |
| **dense sampling** | **20.0%** |

> **You cannot reconstruct an optimum from samples that do not resolve it.**

The basins are narrower than the sample spacing, so nine samples spanning ±3% simply do not contain
the structure any of these methods is trying to recover. This is a sampling-theorem argument, not an
implementation shortfall: the dense grid wins on **sampling density**, and no post-hoc cleverness on
sparse samples substitutes for it. Three failures with three different mechanisms, all reducing to
the same cause, is what makes this a result rather than a run of bad luck.

### A correction to our own wording

An earlier version of this document called the remaining 2-point gap *"irreducible"*. The review
objected, and it is right: **we proved this implementation needs 3× runtime, not that the problem
does.** The honest statement is a measured accuracy/runtime frontier *for the current optimization
strategy*. A fundamentally cheaper optimizer — a learned geometry initializer that lands inside the
right basin without sampling for it, for instance — is not excluded by anything measured here. It is
simply not something we have built or tested, and the frontier stands until someone does.

*(Superseded by §23. The frontier was real for the strategy measured here; screening the refit
removed it, and the wide configuration now costs 1.4× rather than 3× — while being more accurate
than the unscreened version of itself.)*

---

## 23. The frontier dissolves: screening the refit ✅✅ (13 Aug, win-2)

§21d framed a two-point accuracy gain as costing 3× runtime, and shipped the cheaper point. That
frontier turned out to be an artefact of **where the dense configuration's time was actually going**,
which nobody had measured. Profiling it was the whole of the work.

### 23a. First, the hypothesis that was wrong ⚪

The recorded next action was: `build_template` does two things — box-integrate the 1000×1000
reference (depends on **scale** only) and affine-warp it (scale **and** rotation) — and the refit
re-integrated for every rotation. Hoisting the integration to once per scale turns a 5×5 grid's 25
integrations into 5.

Implemented, and it works exactly as predicted: **850 → 616 ms, bit-identical** on all 100 held-out
pairs (verified by diffing predictions against the committed CSVs, not by eyeballing the summary
metrics). But 616 ms is not 400 ms, and the reason is that the hypothesis was aimed at the wrong
term. After the hoist:

| | dense config, per pair |
|---|---|
| `matchTemplate` (correlation) | **1.08 s / 2.0 s of total profile** |
| `sepFilter2D` (integration) | 0.13 s |
| `warpAffine` | 0.04 s |

Template construction was **6%** of the refit. It was never the cost.

### 23b. The measurement that redirected everything ✅

Instrumenting `_refit_once` to print what it is actually given:

```
candidates=60  groups=6  steps=5  ->  templates=150  corrs=1500
```

**Sixty candidates, not ten.** `top_k=10` is *per pose*, and the pose bracket contributes six poses,
so the refit receives 60 candidates and sweeps each over 25 poses: **1500 correlations per pair**,
which is 334 of the dense configuration's 540 ms almost exactly. The cost is candidate count × grid
size, and only the grid size had ever been considered.

Nothing about this was visible in the config; it took an instrumented run to see it.

### 23c. Screen cheaply, then spend the dense budget on the survivors ✅✅

A candidate lying 30th on score cannot become the answer — the refit *compresses* scores, it does
not reorder by thirty places. So rank with the cheap narrow grid first, and give only the top 10 the
expensive one. **This is the same criterion at two resolutions, not a new criterion**, so it stays on
the safe side of ADR-0024.

| config | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|
| narrow only (previously shipped) | 12.5% | 25.0% | 23.3% | 16.7% | 22.0% | 296 ms |
| wide dense, unscreened | 10.0% | 22.5% | 20.0% | 16.7% | 20.0% | 601 ms |
| **wide dense + screen, top 10** | 12.5% | **22.5%** | **16.7%** | **13.3%** | **18.0%** | **427 ms** |

Runtimes interleaved round-robin across configs *and* splits, warm-up discarded — the method §19
established, extended so that the configs are comparable to each other and not only the splits.

**The screen is not merely a cost saving: it is faster *and* more accurate than the dense grid it
replaces.** *(The mechanism originally stated here — that the wide sweep is now centred on a pose the
narrow pass has already corrected — was measured on 14 Aug and refuted. See §23f for the corrected
account. Dense sampling is still what §22 said was irreplaceable; what changes is how widely it is
handed out.)*

Held-out improving 20.0% → 18.0% while the tuning split *worsens* 10.0% → 12.5% is the opposite of
the overfitting signature, and is why this was believed.

### 23d. Choosing the threshold on recall, not on the tie ⚪→✅

Accuracy was **identical** for `top_n` ∈ {6, 10, 15, 20} across all 140 pairs; only runtime differed
(392 / 427 / 478 / 510 ms). A tie on the evidence available is exactly where it is easiest to pick
the wrong thing for the wrong reason — the pre-registered criterion was "under 400 ms", which
`top_n=6` meets and `top_n=10` misses.

So the tie was broken by measuring what the screen *discards*, which is the quantity that matters on
data we have not seen. Rank of the true candidate after the screen:

| split | rank 1 | within top 6 | within top 10 | within top 20 | present at all |
|---|---|---|---|---|---|
| sponsor | 75.0% | 80.0% | **90.0%** | 95.0% | 97.5% |
| bench | 80.0% | 86.7% | 86.7% | 86.7% | 90.0% |
| holdout FinFET | 83.3% | 90.0% | 90.0% | 90.0% | 96.7% |

On **sponsor** — the split the problem statement actually scores — `top_n=6` throws away **10 points
of recall** that `top_n=10` keeps. Both convert it to the same answer *today*; recall is the headroom
that protects against evaluation data that differs from ours, and 41 ms is a poor price for it.
`top_n=10` ships, over the pre-registered runtime bar, with the reason recorded rather than the bar
quietly moved.

Note also that the screen at top-10 is **strictly more permissive than the previously shipped
configuration's own selection**, which took rank 1 after that identical narrow pass. It cannot
discard anything the old default was keeping.

### 23e. What this changes about §21d

| | held-out mis-lock | p50 |
|---|---|---|
| §21d's stated frontier: cheap point | 22.0% | 297 ms |
| §21d's stated frontier: accurate point | 20.0% | 886 ms |
| **now** | **18.0%** | **427 ms** |

The accurate point is now better than §21d's accurate point *and* cheaper than its own earlier self.
§22's correction — "we proved this implementation needs 3× runtime, not that the problem does" —
was the right hedge, and it earned its keep within a day: **the 3× was an implementation artefact,
and profiling removed it.** The general lesson is §19's, learned twice now: *profile before
optimising, and before assuming which stage is expensive.* Both times the intuition was wrong, and
both times it was wrong about the same thing — assuming the expensive-looking operation (a filter
over a 1000×1000 image) dominated a large number of cheap-looking ones (a correlation on a 114×114
window).

### 23f. Why the screen works — the explanation we published first was wrong ❌ → ✅

§23c attributed the gain to *better initialisation*: the wide sweep is centred on a pose the narrow
pass has already corrected. An external reviewer arrived at the same explanation independently and
called it the strongest formulation of the method. It is wrong, and one experiment shows it.

The screen does two separable things — it **prunes** the field, and it **re-scores** the field
before pruning. Run each without the other:

| variant | prunes | re-scores first | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|---|---|
| A — no screen | – | – | 10.0% | 22.5% | 20.0% | 16.7% | **20.0%** | 598 ms |
| B — **shipped** | ✓ | ✓ | 12.5% | 22.5% | 16.7% | 13.3% | **18.0%** | 397 ms |
| C — screen runs, nothing pruned | – | ✓ | 12.5% | 22.5% | 20.0% | 16.7% | **20.0%** | 730 ms |
| D — truncate on unrefit scores | ✓ | – | 17.5% | 27.5% | 20.0% | 23.3% | **24.0%** | 304 ms |

*(C is `refit_screen_top_n=9999`; D is `refit_screen_steps=1`, a single evaluation at the existing
pose, which truncates without moving anything. Making these expressible required separating "run the
screen" from "truncate" in `refit_candidates` — they had been one condition.)*

**C is identical to A on every split.** Re-centring the poses buys nothing, because the wide grid's
±3% span dwarfs the ±0.6% the narrow pass moves anything by; it simply re-finds the same optimum.
And **D is the worst configuration measured**, worse than doing nothing.

So the mechanism is neither half:

> **A wide pose search helps the true candidate and helps impostors more.** Handing ±3% and ±1.5° to
> 60 candidates gives 59 impostors 25 chances each to find a flattering pose. The screen is a
> **bound on how much geometric freedom the candidate field collectively receives** — and the narrow
> refit is what makes a top-10 cut trustworthy enough to take *before* granting that freedom.

That asymmetry is not new: it is exactly why ranking by refit *gain* failed at 80–92% (§15d).
Impostors start with more mismatch and therefore have more to absorb. What is new is that the same
asymmetry sets a limit on how *widely* geometric freedom may be distributed — which is why the
harm appears between top_n=20 (18.0%) and no pruning at all (20.0%), and why the accuracy plateau
over top_n ∈ {6, 10, 15, 20} is a plateau rather than a monotone trend.

> ⚠️ **The paragraph above is a hypothesis, and its central prediction has since been tested and
> failed.** See §25c. The A/B/C/D ablation stands — bounding the field is what helps — but *"because
> impostors travel further in pose"* does not survive direct measurement, and is the **second**
> mechanism this section has proposed and had to withdraw. The ablation is the finding; the
> explanation is not. Both are left standing here, marked, rather than quietly rewritten.

**Why this correction is worth more than the explanation it replaces.** "Coarse geometric
preconditioning" is a nicer story and would have gone in the deck unchallenged. It predicts C ≈ B.
C = A. Publishing the measured mechanism instead costs a good slide and buys a claim that survives
a judge asking "how do you know?".

### 23g. Two parameters swept to a plateau, both negative ⚪

Recorded because both were named as the highest-value remaining knobs — one by us in the handoff,
one by an external review — and both turned out flat. `top_k` is the per-pose candidate count, so it
sets the pool the screen sees (6 poses × top_k).

| `top_k` | pool | dev | sponsor | bench | FinFET | held-out | p50 |
|---|---|---|---|---|---|---|---|
| 5 | 30 | 17.5% | 25.0% | 16.7% | 13.3% | 19.0% | 357 ms |
| **10** | **60** | 12.5% | 22.5% | 16.7% | 13.3% | **18.0%** | **397 ms** |
| 15 | 90 | 12.5% | 22.5% | 16.7% | 13.3% | 18.0% | 401 ms |
| 20 | 120 | 12.5% | 22.5% | 16.7% | 13.3% | 18.0% | 427 ms |
| 30 | 180 | 12.5% | 22.5% | 20.0% | 10.0% | 18.0% | 478 ms |

The reasoning for expecting a win was sound — before the screen, raising `top_k` multiplied the
*dense* grid; after it, extra candidates only pay for the cheap screen, so recall should have been
nearly free. It is free. There is simply none left to buy: `top_k=10` is already at the plateau, and
below it (5) accuracy falls. Checking whether the flat accuracy hid a recall gain, `top_k=20`
doubles the pool and moves screen recall@10 by +3.3 points on bench, 0 on sponsor and **−3.3 on
FinFET** — the extra candidates crowd the top 10 as often as they populate it.

`top_n` (the screen's cut) is likewise flat over {6, 10, 15, 20} at 18.0%, and was set to 10 on
retained recall rather than on the tie (§23d).

**Both are reported as measured negatives (R9).** Two independently-motivated "highest-value knobs"
landing on a plateau is itself the finding: this configuration is at a local optimum in its
parameters, and further accuracy will not come from tuning them.

### 23i. Two packaging defects found while re-verifying ❌ → ✅

`verify_submission.py --strict` failed on three untraceable deck numbers. The cause was
`solution_presentation.rebuilt.pptx` — a fallback `make_deck.py` writes when the real deck is locked
by an open PowerPoint/LibreOffice window — which had been committed on 12 Aug and was two
generations stale. Deleted and added to `.gitignore`.

It also exposed a live bug: `package_submission.py` selected the deck with
`next(REPO_ROOT.glob("*.pptx"))`, and glob order is not guaranteed. **The submission zip could have
shipped the stale fallback deck**, silently, with a plausible filename and a complete-looking
archive. Now selected by exact name.

---

## 24. The robustness sweep — a required deliverable we were not producing ✅ (14 Aug)

Searching the problem statement for what it actually asks for turned up a graded deliverable with
no corresponding artefact:

> *"Results across multiple noise levels, target positions, scales and rotations."*

Every number in `results/` came from three splits at **one operating point**. That answers "how good
is it" and not "where does it break" — and the spec separately states that the released test data
uses parameters we have not seen, at higher noise. A single-point result cannot distinguish a method
that degrades gracefully from one that falls off a cliff just outside the tested envelope.

`scripts/robustness_sweep.py` now measures 22 operating points. Seeds come from a band disjoint from
`bench`, `dev` and `holdout_finfet` by construction: this is **validation, never tuning** (R5). The
ladders deliberately run *past* the promised envelope, because the shape of the failure outside it is
worth more than another point inside it.

| axis | point | in spec | baseline | **DriftLock** | median px |
|---|---|---|---|---|---|
| dose | 800 (4× nominal) | ✔ | 60.0% | **13.3%** | 0.251 |
| dose | 200 **nominal** | ✔ | 73.3% | **20.0%** | 0.363 |
| dose | 50 (4× noisier) | ✘ | 73.3% | **16.7%** | 0.207 |
| dose | 25 (8× noisier) | ✘ | 90.0% | **16.7%** | 0.334 |
| read σ | 5 **nominal** | ✔ | 86.7% | **26.7%** | 0.337 |
| read σ | 20 (4×) | ✘ | 80.0% | **6.7%** | 0.232 |
| scale | 10:1 fixed | ✔ | 43.3% | **16.7%** | 0.304 |
| scale | 9–11:1 **spec** | ✔ | 86.7% | **16.7%** | 0.294 |
| scale | 8–12:1 | ✘ | 83.3% | **40.0%** | 0.705 |
| rotation | 0° / ±1° / ±2° **spec** | ✔ | 63–80% | **10.0% at all three** | 0.19–0.36 |
| rotation | ±3° | ✘ | 86.7% | **16.7%** | 0.299 |
| rotation | ±5° | ✘ | 96.7% | **26.7%** | 0.596 |
| other | gamma 0.7 + vignette 0.4 | ✘ | 70.0% | **13.3%** | 0.378 |
| other | charging streaks | ✘ | 90.0% | **33.3%** | 0.939 |
| other | salt-and-pepper + speckle | ✘ | 73.3% | **6.7%** | 0.338 |
| other | beam spot 12 nm | ✘ | 73.3% | **10.0%** | 0.330 |

**What it says.**

* **Noise is not the problem.** Across a 32× dose range the rate moves between 13.3% and 23.3% —
  inside the sampling noise established in §27. The baseline moves 60% → 90% over the same range.
  Read noise likewise. Whatever limits this method, it is not photon or detector statistics, which
  is consistent with §15's finding that the ranking is limited by model mismatch rather than noise.
* **Rotation is flat inside the envelope and degrades smoothly outside it.** 10.0% at 0°, ±1° and
  ±2° — the same number three times — then 16.7% at ±3° and 26.7% at ±5°. Graceful, not a cliff.
* **Scale is the binding axis.** 16.7% inside the promised 9–11:1, **40.0%** at 8–12:1. The pose
  bracket is built for the spec's range and does not extend itself; this is the honest edge of the
  envelope and is now stated rather than left to be discovered.
* **Charging streaks are the worst named degradation** at 33.3%. The sponsor's list of possible
  degradations includes them explicitly, so this is a live risk on the released test set rather than
  a hypothetical one. Row destriping was re-tested against them and does not fix it (§26).

### 24a. Target position — the fourth axis, and it needed no new data ⚪

The spec names four axes and the sweep above covers three. The fourth, **target position**, turned
out to require no generation at all: the 100 already-evaluated pairs place targets from **32 px to
547 px** from the field centre. `scripts/position_strata.py` stratifies what exists rather than
manufacturing more, which matters here — generating one stress split costs more machine time than
every analysis in this document combined.

Two stratifications, because they probe different mechanisms. Radius from the field centre is where
barrel, vignetting and the drift model's linear approximation would bite; distance to the nearest
frame edge is about context available to the correlation window, which radius does not capture.

| stratum | n | mis-lock | 95% CI | median px |
|---|---|---|---|---|
| radius, inner | 16 | 6.2% | [1%, 28%] | 0.194 |
| radius, mid | 36 | 22.2% | [12%, 38%] | 0.349 |
| radius, outer | 48 | 14.6% | [7%, 27%] | 0.206 |
| edge, near | 25 | 16.0% | [6%, 35%] | 0.340 |
| edge, mid | 41 | 12.2% | [5%, 26%] | 0.205 |
| edge, central | 34 | 20.6% | [10%, 37%] | 0.300 |

**Every interval overlaps every other, and both patterns are non-monotone** — the worst radius band
is the middle one, not the outer. There is no positional dependence resolvable at this sample size,
which is the useful answer: it means no positional correction is warranted, and nothing in the field
geometry is quietly costing accuracy.

It also corroborates ADR-0021 from a second direction. The closest-to-centre tie-break was rejected
because the benchmark samples targets uniformly, so the deployment prior it needs is absent. This
adds that accuracy does not vary with position *either* — so even a correctly-calibrated centre rule
would have nothing to exploit here.

---

## 25. Stress testing found a bug in our own generator, not in the localizer ❌ → ✅

The barrel-distortion point came back at **53.3% mis-lock, median error 9.09 px**, by far the worst
in the sweep. A median of 9 px is the tell: a genuine mis-lock lands tens to hundreds of pixels away.
9 px is not a wrong lattice repeat, it is a **systematic offset**.

### 25a. The diagnosis, which took one measurement

If the error is a distortion the model does not invert, it must be radial and grow with radius.
Measured on the 30 barrel pairs:

| quantity | value |
|---|---|
| cos(error vector, radial direction) | **−0.829** |
| error points *inward* | **97% of pairs** |
| fit of error to `a·r²` (non-mislocked pairs) | **R² = 0.811** |
| implied error at r = 100 px / 400 px | 0.40 px / 14.10 px |

Inward, radial, quadratic in radius. That is barrel distortion's own signature, arriving in the
residual of a localizer that has no barrel term.

### 25b. Root cause: `cv2.remap` runs backwards, and the label did not

`barrel_distortion` is written the way `remap` requires — for each **output** pixel it names the
**source** pixel to sample, `source = c + (p − c)(1 + k·r_p²)`. That is the *inverse* of the path a
feature actually travels. Meanwhile `pipeline.py` computed ground truth through scale and rotation
and stopped, because barrel is applied later inside `detector_chain`.

So the ground truth described the pre-distortion frame while the saved image showed the distorted
one. **The dataset was mislabelled, and the sweep read it as a 53.3% failure of the localizer.**
Reported as-is, it would have been a stated weakness of our method that was actually a defect in our
data.

Fixed by `imaging.barrel_map_point`, which solves the map rather than reusing the expression — a
fixed-point iteration, since the closed form runs the wrong way. `tests/test_geometry.py` covers it
with a **hand-derived asymmetric case**: pick the output point, compute by hand the source it
implies, require the function to recover the output. It also asserts the *inward* sign, which was
the whole bug, and that `k = 0` is exactly the identity.

**Only datasets generated with `barrel_distortion_k ≠ 0` were affected.** `bench`, `dev` and
`holdout_finfet` all use the default of 0, so no reported number moves.

**Result after the fix**, same seeds, same localizer:

| | mis-lock | median error |
|---|---|---|
| before (mislabelled GT) | 53.3% | **9.085 px** |
| after | 43.3% | **1.192 px** |

The median falls by 7.6×, which is the diagnosis confirming itself — a systematic radial offset
disappears when the label is placed in the frame the image was actually rendered in. The mis-lock
rate falls much less, and that residual is **real**: at `k = 0.05` barrel warps the 100×100 footprint
by more than a global affine template can express, so the lattice selection genuinely suffers. That
is now an honest limitation of the localizer instead of a bug wearing a limitation's clothes. It is
also the worst point in the entire sweep, and barrel distortion is *not* among the degradations the
problem statement names — unlike charging streaks, which are, and which sit at 33.3%.

### 25c. The same instrumentation refuted our own mechanism claim ❌

`scripts/failure_decomposition.py` was written to answer two questions, and the second was aimed at
§23f's explanation of why the screen works: *a wide pose search rewards periodic impostors more than
the true candidate*. That predicts something checkable — in a failure where the truth reached the
final comparison and lost, the winning impostor should have **travelled further in pose**.

Measured on the 9 such failures, travel normalised by the refit's own search span:

| | winner | truth |
|---|---|---|
| mean pose travel | **0.224** | 0.281 |
| winner travelled further | **0 of 9 failures** | |
| median score margin the truth lost by | 0.0053 | |

The winner travels **less**, in every single case. Under a fair coin that is p ≈ 0.004.

*A correction to the correction:* the first version of this measurement recorded
`abs(rotation_deg)` — the final absolute pose, not displacement from the starting pose — and called
it "travel". It did not measure the quantity it was named after, so its result meant nothing. The
entry pose is now stamped on each candidate before the screen runs and travel is a real difference.
**A test that does not measure what its variable is named after is worse than no test**, because it
produces a number that looks like evidence.

So §23f's explanation joins §23c's on the refuted pile. What survives is the ablation itself:
bounding the field helps (18.0% against 20.0%), re-scoring alone does nothing, pruning alone is
worse than nothing. The mechanism consistent with *all* of it — impostors do not need more freedom,
there merely need to be more of them — is a multiple-comparisons effect: the maximum over many
candidates' independently-optimised scores is upward-biased, and that bias grows with the *number*
of competitors rather than with any one competitor's excursion. **That is a hypothesis and is
labelled as one.** Two mechanisms have already been asserted here and withdrawn; a third assertion
would be worth less than the honest statement that the ablation is solid and the explanation is not.

---

## 26. Two components were rejected in the one regime where they could not work ⚪ → ✅

§3 recorded the median filter as "no effect" and §4 recorded row destriping as "actively harmful".
Both conclusions were drawn on the nominal splits — where `salt_pepper_prob = 0` and
`charging_streak_prob = 0`. **A component that removes a degradation was evaluated only on data
containing none of it**, so it could do nothing but destroy signal. The sweep supplied the missing
regime.

| config | nominal (control) | salt-and-pepper | charging streaks |
|---|---|---|---|
| neither (shipped) | 20.0% | 16.7% | 36.7% |
| **+ 3×3 median** | **20.0%** | **6.7%** | 33.3% |
| + row destripe | **36.7%** | 23.3% | 33.3% |

**Row destriping stays off.** It is catastrophic on clean data (20.0% → 36.7%, confirming §4) and its
gain on the streaks it was written for is one pair — inside noise. It removes horizontal word lines
along with the streaks, and on this layout that is most of the signal.

**The median filter ships.** On the 100 held-out pairs it is *strictly* non-harmful, paired:

| | value |
|---|---|
| pairs it breaks | **0 of 100** |
| pairs it fixes | 2 |
| held-out mis-lock | 18.0% → **16.0%** |
| sponsor / bench / FinFET | 22.5→**20.0%** / 16.7→16.7% / 13.3→**10.0%** |
| runtime cost, interleaved | **−3 ms** (i.e. none) |

The 2-pair held-out gain is *not* the justification and is well inside noise (§27). The justification
is the impulse-noise column: **16.7% → 6.7%**, on validation-only seeds, for a degradation the spec
names explicitly and a released test set stated to use parameters we have not seen. A stage that is
free, provably harmless on 100 held-out pairs, and worth 10 points in a regime the evaluator may
include is worth taking on those grounds alone.

The mechanism is not subtle, which is why it deserved a fair test: impulse pixels are *unbounded*
outliers and correlation has no defence against them, while a 3×3 median removes them essentially
exactly and leaves edges intact.

> **The general lesson, and it is not about medians:** an ablation run at a single operating point
> silently answers a narrower question than the one it appears to answer. "Stage X does not help"
> means "stage X does not help *here*". Two of our own negative results were artefacts of that, and
> both had been recorded with numbers and treated as settled for three days.

### 26a. Composition: do the robustness gains survive being stacked? ✅

Every ladder in §24 moves one axis, which is right for diagnosis and wrong for prediction — the
released test set will not vary one nuisance at a time. Three combined points:

| point | baseline | **DriftLock** |
|---|---|---|
| spec envelope (9–11:1, ±2°) + 4× noise | 73.3% | **23.3%** |
| the same + charging streaks | 63.3% | **20.0%** |
| everything, beyond spec (8.5–11.5:1, ±3°, 4× noise, 2× read noise, streaks, impulse, gamma, vignette) | 83.3% | **46.7%** |

**Degradations compose roughly additively; no new failure mode appears.** The 46.7% point is fully
accounted for by axes already characterised alone — 8.5–11.5:1 straddles the searched scale bracket
(40.0% at 8–12:1) and ±3° is outside the pose envelope (16.7%). Nothing emerges from the combination
that was not visible in the parts.

Note the second row is *lower* than charging streaks alone (33.3%). That is not a real effect and is
not claimed as one: it is a different seed at n=30, and §27 puts the sampling floor at ~13 points.

### 26b. A charging-streak correction, built on the evidence and rejected by it ❌

Under charging streaks the failure mode **inverts** relative to the reported splits:

| split | ABSENT | SCREENED | OUTSCORED |
|---|---|---|---|
| the three reported splits | 3 | 4 | **9** |
| charging streaks | **23.3%** | 6.7% | 3.3% |
| mixed, beyond spec | **30.0%** | 6.7% | 10.0% |

70% of the streak failures are **ABSENT** — the true location never becomes a candidate. So the
streak destroys the correlation peak *upstream of top-K*, no re-ranking stage could ever reach those
pairs, and preprocessing is the only intervention that could work. That is a real, evidence-led
reason to build one, and it also explains why row destriping was the wrong shape: it does not restore
the peak, it removes different signal.

`preprocess.destreak` corrects **conditionally**: attenuate the lattice's vertical oscillation first,
estimate a wide baseline, flag only rows deviating by >4 robust sigmas, and subtract from those rows
alone. On clean data nothing is flagged.

**A hand-built test caught a design flaw before any of that reached data.** The first version skipped
the lattice-attenuation step. With word lines every 8 rows the bright rows are a low-duty-cycle spike
train in the row-mean profile, so a robust baseline sits near the dark level and *every word line*
reads as a 4-sigma anomaly — the correction erased the lines and left a residual seven times larger
than the streak. Amplitude cannot separate them; vertical frequency can, since the lattice oscillates
over a few pixels and a charging band spans tens of rows.

Measured properly, it does exactly what it was built to do and still fails the bar:

| | without | with |
|---|---|---|
| charging streaks (n=30) | 33.3% | **26.7%** |
| nominal control (n=30) | 20.0% | **20.0%** |
| the 100 reported pairs | 16.0% | **17.0%** — breaks 1, fixes 0 |
| runtime | — | **+56 ms** |

**Rejected.** The median filter cleared this identical bar with 0 broken, 2 fixed and −3 ms
(ADR-0027); this breaks one, fixes none, and costs 56 ms. A 2-pair gain well inside the sampling
floor does not buy a regression on the reported set. Kept unwired with its numbers per R9 — if the
released data proves streak-heavy it is one line from being enabled, but on the evidence available
it is a net negative.

*The discipline is the point.* This stage was suggested by review, motivated by our own failure
decomposition, and behaves exactly as designed in its target regime. None of that is evidence. The
paired held-out test is, and it said no.

### 26c. Charging streaks, closed: the peak is destroyed, not demoted ❌

Two further experiments, both cheap, both aimed at the ABSENT bucket that dominates this regime.

**Raising `top_k` does nothing.** `top_k` is the one knob that directly adds candidates, and it had
only ever been swept on nominal data where the ABSENT bucket is nearly empty:

| split | top_k=10 | top_k=20 | top_k=30 |
|---|---|---|---|
| charging streaks | 33.3% | 33.3% | 33.3% |
| mixed, beyond spec | 46.7% | 46.7% | 46.7% |
| nominal control | 20.0% | 20.0% | 20.0% |

Flat to the pair, on every split, at three times the candidate budget. **That is a stronger
statement than the ABSENT bucket alone.** If the true location were merely *demoted* below the cut,
tripling the pool would recover it. It does not, so the streak is not reordering the correlation
surface — it is **erasing the peak**. No proposal mechanism that reads the raw image can find a
maximum that is no longer there.

**And the correction barely restores it.** Instrumenting the candidate pool with `destreak` active:

| | mis-lock | true peak ABSENT from the pool |
|---|---|---|
| raw | 33.3% | 23.3% |
| destreaked | 26.7% | **20.0%** |

One pair of thirty recovered. That also settles a proposal-union design — running the corrected
image as a *second* candidate source while leaving the raw pipeline untouched, which would have
sidestepped the regression that killed `destreak` outright. It would import at most one pair of
recall for a second full candidate-generation pass. Not worth the runtime or the complexity.

**So charging streaks are a stated limitation, not an unsolved to-do.** The chain is complete and
each link is measured: the failure is upstream of ranking (23.3% ABSENT vs 3.3% OUTSCORED), so no
selection stage can help; it is not a ranking-threshold problem (top_k flat); and the natural
correction restores almost none of the lost peaks while regressing the benchmark. Recovering this
regime needs a representation in which the streak and the signal are separable — which is a research
direction, not a three-day fix.

---

## 27. How much of our own reported difference is real? ⚠️

The sweep accidentally ran the nominal configuration **twice**: `s02` and `s06` draw from an
identical generator parameter set — verified by diffing every manifest column — and differ only in
seed. They measured **20.0%** and **26.7%** mis-lock. Earlier, before the median filter, the same
pair measured 20.0% and 33.3%.

That is the sampling floor, and it is not small. `scripts/significance.py` now generates it:

| scope | rate | Wilson 95% CI |
|---|---|---|
| sponsor | 20.0% (8/40) | [10.5%, 34.8%] |
| bench | 16.7% (5/30) | [7.3%, 33.6%] |
| holdout FinFET | 10.0% (3/30) | [3.5%, 25.6%] |
| **aggregate** | **16.0% (16/100)** | **[10.1%, 24.4%]** |

Wilson rather than the textbook normal approximation, which at n = 30 and p ≈ 0.13 extends below
zero and is therefore not a probability.

**But the marginal intervals answer the wrong question for our own comparisons, and they answer it
pessimistically.** Comparing two configurations by their overall rates discards the fact that both
ran on the *same pairs*. The paired comparison of the screened-wide configuration against the narrow
one it replaced:

| | value |
|---|---|
| narrow correct, screened wrong (b) | **0** |
| screened correct, narrow wrong (c) | **6** |
| both correct / both wrong | 78 / 16 |
| exact McNemar two-sided | **p = 0.031** |

**Strictly dominant — zero regressions on 100 pairs — and significant at 0.05.** It is worth
recording that this was *not* true earlier in the same day: at 4 discordant pairs the identical
comparison gave p = 0.125, and the honest report then was "dominant but unresolved". Two more
discordant pairs, both falling the same way, moved it across. That is how thin the evidence is at
this sample size, and it is the reason the paired test is quoted rather than the marginal rates —
which still overlap heavily and would have shown nothing either way.

What this retroactively licenses, and what it does not:

* **Across-split differences of 2–4 points are not resolved.** Every such claim in this document
  should be read as directional. The two identically-parameterised splits differing by 6.7 points
  are the calibration.
* **Within-split paired comparisons are much stronger than the marginal intervals suggest**, because
  the pair-level correlation is enormous — 78 of 100 pairs are correct under both configurations.
  The A/B/C/D mechanism ablation (§23f) is of this kind and is correspondingly more trustworthy than
  its marginal rates look.
* **"Beats the baseline" is not in doubt.** 76.7% → 16.7% on bench and 90.0% → 10.0% on FinFET are
  not 4-point differences.

---

## 28. The nine outscored failures, and why a seventh re-ranker would also fail ⚪

These are the only failures a better selection rule could ever address: the true location was a
candidate, survived the screen, reached the final comparison, and lost. Nine of them, across 100
pairs.

| split | error px | margin the truth lost by |
|---|---|---|
| sponsor | 14.38 | 0.0035 |
| sponsor | 14.34 | 0.0108 |
| sponsor | 21.53 | 0.0094 |
| sponsor | 64.25 | 0.0105 |
| sponsor | 43.23 | 0.0114 |
| sponsor | 19.40 | 0.0053 |
| bench | 17.70 | 0.0028 |
| bench | 6.54 | 0.0000 |
| holdout FinFET | 707.28 | 0.0039 |

**Median error 19.4 px — two to three lattice periods.** Eight of nine land within 65 px, so these
are *nearby repeats*, not wild misses. The one 707 px outlier is the failure case already visualised
in `results/failure_case/`.

**Median margin 0.0053, and six of nine lose by under 0.01.** That is the number that matters. The
sampling noise on a correlation of ρ≈0.9 over a 100×100 template is about 0.002 (§15), so the truth
is losing by roughly **2.6× the measurement noise of the statistic being used to decide**.

That is the quantitative form of a conclusion the project reached the expensive way. The
discriminating information *is* present — the margin is not zero, and it is not negative — but it
sits close enough to the noise floor of ZNCC-on-100×100 that any rule reading that surface must
resolve a half-percent difference reliably. Six independent criteria were built to try (ADR-0024);
all six failed; and this says why in one number rather than as a tally of attempts.

**It also bounds what is left.** Nine pairs of 100 is the entire addressable-by-ranking budget, and
they are the *hardest* nine by construction. A seventh criterion would have to beat six predecessors
on a margin of 0.005 without regressing the 78 pairs that are currently correct — and the paired
tests in §27 show that a change of two pairs is not even resolvable at this sample size. We stop
here, and the stopping is evidence-based rather than a schedule decision.

## 30. The spec's centre tie-break, done properly — and the reason nothing can win a tie ❌✅

The problem statement licenses one selection rule explicitly: *"If several valid matches exist,
select the one whose centre is closest to the search-image centre."* ADR-0021 rejected it as a
**default**. This tests the narrow, spec-faithful version — fire it *only* when candidates are
statistically indistinguishable — which is the strongest form of the idea and the one an external
review ranked as the highest-value remaining experiment.

**The audit that made it look promising.** Comparing the true location against the winning impostor
on distance-to-centre, across the nine outscored failures: the truth is closer in **6 of 9**. An
apparent free +3.

**It does not survive implementation.** Sweeping the tie gate over every threshold, applying the rule
to the full tied set (all candidates within τ of the top score), on the 100 held-out pairs:

| gate τ | fires | flips | **fixes** | breaks | net |
|---|---|---|---|---|---|
| 0.000 | 32 | 0 | **0** | 0 | 0 |
| 0.002 | 65 | 4 | **0** | 2 | −2 |
| 0.005 | 83 | 17 | **0** | 6 | −6 |
| 0.010 | 95 | 25 | **0** | 9 | −9 |
| 0.020 | 97 | 44 | **0** | 26 | −26 |
| 1.000 (ungated) | 100 | 74 | **0** | 57 | −57 |

**Zero fixes at every threshold.** Not "a poor trade" — the rule never once recovers a failure, at
any setting, while breaking up to 57 correct pairs.

### The mechanism, which is the actually valuable part

Final rank of the *true* candidate across the 15 held-out failures:

| | count |
|---|---|
| rank ≤ 2 | **0** |
| rank ≤ 3 | 1 |
| rank ≤ 5 | 4 |
| rank ≤ 10 | 8 |
| absent from the top 20 entirely | **7** |

> **The truth is never the runner-up.** In every failure it sits at rank 3 or worse, or is not in the
> candidate set at all.

That single fact explains far more than this experiment:

* **Why the centre rule cannot help.** A tie-break selects among *near-equal scorers*. The tied set
  is populated by other impostors; the true candidate is not in it. The 6-of-9 audit was measuring
  the wrong thing — truth-versus-winner *position* says nothing about whether the truth is reachable
  through the *ranking*.
* **Why six re-ranking criteria failed** (ADR-0024). They re-order a list in which the truth is
  third or worse. A criterion strong enough to lift it past two or more impostors would have to be
  far better than a tie-break, not marginally different from ZNCC.
* **It re-scales §28's headroom.** The median margin of 0.0053 is truth-versus-*winner*, and at least
  one other impostor sits between them. Recovering these pairs is not winning a coin flip; it is
  overtaking a queue.

**The rule stays implemented and off** (`centre_rule=True`), unchanged from ADR-0021 — the checklist
asks that it exist, and it does. What is new is that we can now say *why* it cannot pay here, from a
rank distribution rather than from a rate.

---

## 31. Two structural ideas aimed at the buried truth — one impossible, one flat ❌

§30 reframed the problem: the truth is not a near-miss to be tie-broken, it is buried at rank 3+ or
absent. External review proposed two structural attacks. Both were checked before being built, which
is the only reason neither cost a day.

### 31a. Multi-cell contextual verification — not available, by arithmetic ❌

The proposal: compare the candidate's *surroundings* against the reference's surroundings, on the
theory that two periodic cells can look identical locally while sitting in different neighbourhoods.

It cannot be done, and the reason is a two-line calculation rather than an experiment. The reference
is 1000×1000 px at 1 nm/px — **1000 nm across, which is the whole of it.** There is no reference
content outside its own footprint to build a context window from. Expanding the *search* window is
free, but there would be nothing to correlate it against.

Worse for the idea, the context is already inside the template:

| | |
|---|---|
| word-line pitch 64 nm | reference spans **15.6** word lines |
| bit-line pitch 96 nm | reference spans **10.4** bit lines |
| | ≈ **163 lattice cells per template** |

A 100×100 ZNCC is *already* multi-cell verification over roughly 163 cells. "Add context" describes
what the matcher does today.

### 31b. Cross-pose candidate deduplication — a real defect that does not convert ⚪

The second proposal was lattice-aware candidate diversity. As stated it is self-defeating — in a
periodic array *every* candidate is lattice-congruent to every other, so deduplicating on lattice
congruence would collapse the entire set. But measuring for it found a genuine defect underneath.

`extract_peaks` applies non-maximum suppression **inside each pose's correlation surface**, and the
candidates from every pose in the bracket are then merged **with no suppression across poses**. One
physical site therefore enters the refit once per pose that found it:

| | measured on bench |
|---|---|
| candidates entering the refit | 60 |
| **distinct positions among them** | **33.8** |
| distinct positions in the top 10 after the screen | **6.2** |
| **expensive slots spent on duplicates** | **3.8 of 10** |

Median *minimum* pairwise distance in the top 10 is **0.0 px** — exact copies. Nearly two fifths of
the screen's budget was being spent re-refining the same sites, which is a real inefficiency and
looked like a direct explanation for the rank distribution: the ranks above the truth occupied by
copies of one impostor rather than by distinct rivals.

Deduplicating after the screen (tolerance well inside one lattice pitch, so adjacent repeats are
never merged):

| dedup tolerance | off | 2 px | 3 px | 5 px |
|---|---|---|---|---|
| dev | 12.5% | 15.0% | 15.0% | 15.0% |
| sponsor | 20.0% | 20.0% | 20.0% | 20.0% |
| bench | 16.7% | 16.7% | 16.7% | 16.7% |
| holdout FinFET | 10.0% | 10.0% | 10.0% | 10.0% |
| **held-out** | **16.0%** | 16.0% | 16.0% | 16.0% |

**Flat on every held-out split, and dev regresses.** The freed slots are filled by whatever the
screen ranked 11th to 20th, and the truth is not there either.

So the correction to §30's picture is sharper than the picture itself: **the truth is buried among
*distinct* rivals, not among duplicates of one.** Removing 3.8 wasted slots per pair changes nothing,
which means the ranks above the true candidate are genuinely occupied by different plausible sites
that all out-score it. That is a harder problem than the duplicate story suggested, and it is the
honest one. The flag stays at 0.

---

## 32. The separability oracle: strong new evidence exists, and we cannot select on it ⚠️

External review proposed a learned hard-negative verifier over the candidate set. Before training
anything, the right question is the one that gates the build: **is there information in cheap
candidate features that ZNCC is not already using?** If a classifier with full access to those
features cannot beat the ZNCC ordering, no CNN over the same information will either.

Features are all inference-available and free — they fall out of machinery that already runs. One of
them had never been looked at. The pose bracket applies NMS *inside* each pose's surface but not
across poses, so a site found by several independent pose hypotheses enters the candidate list
several times. §31b showed that **deleting** those duplicates changes nothing — but the *count* was
never used as evidence.

Measured over 1400 candidates from 140 images (494 true, 906 impostors):

| feature | truth mean | impostor mean | **separation (Cohen's d)** |
|---|---|---|---|
| **multiplicity** (poses agreeing) | **5.20** | **3.44** | **1.098** |
| pose_spread | 0.0140 | 0.0087 | 0.823 |
| dup_score_spread | 0.1384 | 0.0773 | 0.678 |
| **score** (what we decide on) | 0.9066 | 0.8743 | **0.414** |
| d_scale | 0.0090 | 0.0070 | 0.272 |
| d_rot | 0.4382 | 0.3416 | 0.249 |

**The number of independent pose hypotheses that find a site separates truth from impostor 2.6×
better than the correlation score the system actually decides on.** That is genuinely new
information, it is free, and it is currently discarded. A site several independent geometries agree
on is more trustworthy than one lucky peak — which is exactly the intuition the duplicate-deletion
experiment failed to exploit, because deletion throws the evidence away instead of reading it.

### And it still cannot be used

Ranking by multiplicity alone is *worse* than score (85.4% vs 92.3% rank-1). So the question becomes
whether a blend helps. Sweeping `score + w·multiplicity`, selecting `w` on `dev` only:

| w | 0.000 | 0.002 | **0.003** | 0.005 | 0.008 | 0.012 | 0.020 |
|---|---|---|---|---|---|---|---|
| dev (37 groups) | 94.6% | 94.6% | **97.3%** | 97.3% | 97.3% | 97.3% | 94.6% |
| held-out (93) | 91.4% | 91.4% | **92.5%** | 90.3% | 90.3% | 88.2% | 87.1% |

**`dev` is flat at 97.3% across w ∈ [0.003, 0.012] while held-out falls from 92.5% to 88.2%.** The
tuning split cannot distinguish the best value from one that is 4.3 points worse. Landing on w=0.003
rather than w=0.005 is luck, not selection — and w=0.005 is *worse than not doing it at all*.

That is the ADR-0012 failure mode with the mechanism visible: not "the feature is useless", but
**the selection set has no power at the resolution the decision requires**. The best honest gain was
1 group in 93, inside the sampling floor of §27 either way.

### What this says about building the verifier

This is the gate the oracle exists to provide, and it does not open. A learned verifier over these
features faces the *same* selection problem, with more knobs rather than fewer: it would choose its
architecture, capacity, stopping point and threshold on the same 37 groups that cannot resolve a
single scalar to within 4 points of held-out performance. The evidence is real; the ability to tune
against it is not.

**The blocker is model-selection power, not absence of signal** — which is a falsifiable statement
and a different claim from the other negatives in this document. It predicts that a substantially
larger tuning set would change the answer.

### 32a. The prediction was tested with 4× the data, and it was wrong ❌

A fresh 160-pair `dev2` split was generated with disjoint seeds across both architectures (151 of
them yield a usable candidate set) purely to test that claim. If selection power were the blocker,
a tuning set four times larger should resolve the optimum and land on a better held-out point.

| w | 0.000 | 0.002 | **0.003** | 0.005 | 0.008 | 0.012 | 0.020 |
|---|---|---|---|---|---|---|---|
| dev, 37 groups | 94.6% | 94.6% | **97.3%** | 97.3% | 97.3% | 97.3% | 94.6% |
| **dev2, 151 groups** | 94.7% | **95.4%** | 95.4% | 95.4% | 94.7% | 94.0% | 94.0% |
| held-out, 93 | 91.4% | 91.4% | **92.5%** | 90.3% | 90.3% | 88.2% | 87.1% |

| selection set | picks | held-out result |
|---|---|---|
| dev, 37 groups | w = 0.003 | 92.5% (+1.1) |
| **dev2, 151 groups** | **w = 0.002** | **91.4% — exactly the baseline** |

**The larger, better-powered tuning set selects a null operating point.** It is also *flatter*: its
spread across the whole sweep is 1.3 points against the small set's 2.7. Four times the data did not
sharpen a peak — it showed there is no peak to sharpen.

Which means the +1.1 points the small `dev` appeared to buy was **luck**. Run the selection properly
and the gain is zero. The small set's apparent optimum at w=0.003 sits one step away from w=0.004,
which costs 2.2 points on held-out, and `dev` could not tell them apart.

**So the honest conclusion is stronger than the one it replaces, and it is not the one I predicted.**
The problem is not that we lack the data to tune this feature. It is that *there is no reliable
operating point to find*: multiplicity separates truth from impostor with a Cohen's d of 1.098 in
the margin, and still yields no repeatable improvement when added to the decision. Strong marginal
separation and a usable decision rule are different things, and this is a clean demonstration of the
gap between them.

**And it closes the learned-verifier question on evidence rather than on schedule.** A model would be
selected on the same signal, with more free parameters, against a criterion now measured to be flat
where it matters. Having made a falsifiable prediction and had it fail is a better reason to stop
than running out of days.

`matchTemplate` is **579 calls and ~199 ms per pair**, about half the runtime, so batching them was
the obvious remaining runtime lever and was proposed by review.

There is a safe way to do it. The refit correlates one template against ten candidate windows of
114×114; concatenating those windows into one 114×1140 image lets a single call do all ten. It is
exactly equivalent for the region each tile owns: the last valid output position in a tile places
the template's right edge on that tile's final column, so no valid position ever straddles a seam.

Measured over 200 repetitions:

| | time per group of 10 |
|---|---|
| ten separate calls | **1.267 ms** |
| one tiled call | 1.943 ms |

**Tiling is 53% slower.** The reasoning behind it was wrong: it assumed per-call overhead dominates.
It does not. A 114×1140 input produces 1041 output columns of which only 150 are wanted, so the
tiled call does roughly seven times the arithmetic to save nine call setups — and at these sizes
OpenCV is arithmetic-bound, not overhead-bound. The residual max difference of 1.2e-6 confirms the
two agree numerically; it is purely a throughput question, and the answer is no.

So the correlation count is set by accuracy, not by inefficiency: the grid, `top_k` and `top_n` are
all at measured plateaus (§23g), and every attempt to compute fewer correlations has cost accuracy.
There is no free runtime here, which is a more useful thing to know than another unmeasured idea.

---

## 33. The aperiodic fingerprint, isolated spatially — and the rule it finally establishes ❌

External review's strongest remaining proposal: correlation is dominated by the periodic structure
that every repeat shares, so estimate that common mode from the lattice and compare only what
remains. Explicitly *not* PADM, which masked periodic energy in the Fourier domain — this folds the
patch into its own cells spatially and subtracts a robust per-pixel median prototype.

Implemented exactly as specified, with no tuning and no pipeline change: for each pair, re-score the
final candidate list by residual-ZNCC and ask whether the truth moves above the current winner.

| | truth at rank 1 | mean rank of truth |
|---|---|---|
| plain ZNCC | **85 / 93** | 0.44 |
| aperiodic residual | **60 / 93** | 0.89 |

| | |
|---|---|
| failures it reverses | **1** |
| correct answers it breaks | **26** |

**Twenty-six broken to fix one.** Not a marginal loss — the residual is far worse than the signal it
was meant to purify.

### Why, and this is the general rule

The mechanism is the one that sank PADM, and seeing it a fourth time makes it a principle rather
than an anecdote. The aperiodic fingerprint **is** real: H7 measured a strictly positive
true-versus-impostor margin of about 0.057 from the random-walk line placement. But it is a *small*
signal riding on a *large* one, and at dose 200 the periodic component carries essentially all of
the usable SNR. Subtracting it does not leave the fingerprint — it leaves the fingerprint plus every
bit of noise and forward-model mismatch, now with nothing large enough to stabilise the correlation
against them.

Four independent attempts have now tried to isolate this signal:

| attempt | how it isolated the residual | result |
|---|---|---|
| PADM (ADR-0012) | Fourier lattice-harmonic mask | overfit; hurt both held-out splits |
| candidate-consensus residual (§15b) | average across candidate patches | mixed, then catastrophic after refit |
| residual tie-break (§20b) | gated to statistical ties | 20.0% → 25.0% |
| **PCAF, this section** | **spatial cell-folding, robust median** | **26 broken to fix 1** |

> **This residual representation destroys more signal than it recovers.** §34 supersedes the
> stronger claim originally made here: this test estimated the lattice separately for template and
> patch, so it refutes cell-folded residual correlation rather than every use of aperiodic
> information. The general statement, reached properly, is in §34.

That is more useful than "residual scoring does not work", because it says what would have to change
for it to work: more photons, a larger footprint, or a representation that uses the periodic
structure to *stabilise* the comparison rather than removing it. The current architecture already
does the last of those — the lattice is a ruler for geometry and is left in place for identity,
which is the right way round.

### Basin coherence — the same feature, a third way of using it ❌

§32 showed multiplicity fails as a blended score. Review proposed using it as a *filter* instead —
keep only coherent candidates, then take the best ZNCC among survivors. That is a genuinely
different decision rule, so it was measured:

| filter | dev2 (151) | held-out (93) |
|---|---|---|
| *baseline, no filter* | **94.7%** | **91.4%** |
| multiplicity >= 3 | 92.7% | 88.2% |
| multiplicity >= 4 | 94.0% | 87.1% |
| multiplicity >= 6 | 94.0% | 89.2% |
| pose_spread <= 0.02 | 88.1% | 88.2% |
| pose_spread <= 0.01 | 59.6% | 66.7% |
| mult >= 4 AND spread <= 0.02 | 91.4% | 86.0% |

**Every filter is worse than no filter, on both sets.** Unlike the blend — which had one lucky point
a larger tuning set then rejected — this is uniform. Multiplicity has now been tried as a score, as
a blend weight and as a filter; it has the strongest marginal separation of any feature measured
(d = 1.098) and is unusable in all three roles.

---

## 34. Internal consistency cannot separate them, because the impostor is also consistent ❌✅

§33's conclusion was too strong and an external reviewer was right to say so. The PCAF test
estimated the lattice **independently** for the template and for the patch, so the two residuals
could sit in different coordinate frames before being correlated — a real flaw, and it means that
experiment refutes *that representation*, not every use of aperiodic information. The finding is
softened accordingly.

The reviewer's alternative is the opposite philosophy and deserved a proper test: do not remove the
periodic component, use the footprint's internal redundancy to check whether **one** geometry
explains the **whole** site. Two experiments, both avoiding the alignment flaw by construction.

### 34a. Cellwise consistency at a fixed pose ❌

Split the aligned footprint into 4×4 blocks and correlate block by block — same template, same pose,
no subtraction and no lattice estimation. On 18 failures where the truth is present but outranked:

| statistic | truth | winner | truth better in |
|---|---|---|---|
| global (by construction the truth loses) | 0.9106 | 0.9187 | 0/18 |
| mean block | 0.8709 | 0.8771 | 3/18 |
| **worst block** | 0.7798 | 0.7759 | **6/18** |
| block spread (lower better) | 0.0422 | 0.0495 | **7/18** |

The *means* favour the truth on worst-block and spread, which looks encouraging — but per pair it
wins only 6 and 7 times out of 18, **below chance**. The favourable averages are a few outliers.

### 34b. Leave-cell-out geometric generalisation ❌ — and it fails backwards

The stronger form. Fit the pose using only half the blocks (a checkerboard, so both halves span the
whole field), then score the **withheld** half under that pose. A periodic impostor was predicted to
be a coincidence of the bulk whose fitted geometry would predict the rest less well.

| | held-out-half score |
|---|---|
| truth | 0.8893 |
| **winning impostor** | **0.8981** |
| truth better in | **5 / 18** (two-sided exact p = 0.096) |

**The impostor generalises better than the truth**, in 13 of 18 cases. Not noise around zero — it
leans, weakly, in the direction opposite to the hypothesis.

### The reason, and it unifies every negative in this document

The prediction assumed a periodic impostor is a *bad fit that got lucky on the bulk*. It is not. On a
lattice that genuinely repeats, an impostor at a lattice offset is a **genuinely correct geometric
explanation of the entire footprint** — correct scale, correct rotation, correct drift, consistent
across every internal region. That is what "periodic" means. It is the right answer to the wrong
question.

So internal consistency cannot separate them, because **both candidates are internally consistent**.
There is nothing inconsistent about the impostor to detect.

That closes the family, and the closure is mutually exclusive rather than merely empirical:

> **Any evidence strong enough to be reliable is shared by the impostor (it is periodic), and any
> evidence that distinguishes them is too weak to be reliable (it is the aperiodic fingerprint).**

Every negative result in this document is one horn of that dilemma. The six re-rankers, the centre
tie-break, basin coherence and LCLOV all leaned on evidence the impostor satisfies equally. PADM,
consensus residual, residual tie-break and PCAF all tried to isolate evidence too faint to survive
the noise at dose 200. There is no third source of information in a 100×100 footprint of a
repeating lattice.

**What the shipped architecture does is the only thing left**, and it is now clear why it works: it
does not try to tell the candidates apart at all. It reduces *geometric mismatch* so that the small
real margin — H7's ~0.057 — is not swamped by model error, then reads the ordinary correlation. That
is why "same criterion, better geometry" is the only stage that has ever helped here (ADR-0024), and
why every attempt at a different criterion has failed.

**This is a stopping condition with a mechanism, not a schedule.** Recovering the remaining failures
requires more photons, a larger footprint, or reference content beyond the 100×100 the problem
provides — none of which is available to a submission.

---

## 35. The oracle ceiling: the truth correlates WORSE, and geometry already recovers 89% of it ⚠️

> ## ⚠️ §35b AND §35c ARE RETRACTED. §35a STANDS.
>
> An independent reimplementation (`scripts/pose_ceiling.py`, 15 Aug) reproduces the truth side to
> the digit — 0.7661, 84/100, 70/100, +0.0072 — and **none** of the winner side. The cause is
> below in **§37**: the "winner" figure was the **maximum of the correlation surface**, not the
> score at the location the pipeline chose. A maximum over ~810,000 positions exceeds the value at
> any nominated point almost by construction, so the comparison was upward-biased and restated
> §35a rather than measuring what §35b claims.
>
> Corrected, both sides nominated: truth **0.7661** against **0.7696**, truth ahead in **7/15**,
> p = **1.000**. The fixed-pose deficit is **+0.0114**, not +0.0654, and the refit closes
> **36.6%**, not 89.0%. Read §37 instead of the two subsections below; they are kept verbatim
> because a retracted claim that quietly disappears teaches nobody why it was wrong.

The question that should have been asked first, and was not: **are the remaining failures even
recoverable?** Every experiment so far assumed they were selection errors. Handing the matcher the
generator's own recorded `scale_ratio` and `rotation_deg` settles it.

### 35a. A perfect pose does not rescue them

Template built at the exact ground-truth pose, one plain correlation over the whole search image, no
pose search, no refit, no screen:

| | |
|---|---|
| shipped pipeline correct | **84 / 100** |
| oracle pose + plain argmax | **70 / 100** |
| shipped failures the oracle recovers | **1 of 16** |

The oracle is *worse than the shipped pipeline* — and it recovers one failure out of sixteen. Pose
estimation error is not what is losing these pairs.

### 35b. At the true location, the image genuinely looks less like the reference

The sharper form. At the exact ground-truth pose, correlate the template at the **true** location and
at the **winning** location:

| | ZNCC at the exact GT pose |
|---|---|
| at the TRUE location | **0.7661** |
| at the WINNING location | **0.8615** |
| truth out-correlates the winner in | **2 / 15** (exact two-sided p = 0.007) |

**The winner beats the truth by 0.0955 at a pose that is correct by construction.** These are not
near-ties that a better tie-break could resolve, and not selection errors. At a fixed global pose the
search image simply resembles the reference *more* at the impostor's location than at the true one.

*(The oracle template carries exact scale and rotation but no drift model. Drift correction in this
pipeline adjusts the reported coordinate rather than the image, so it cannot affect this
correlation, and the residual per-row shear across a 100 px patch is about 0.15 px — far too small to
account for a 0.096 gap.)*

### 35c. And this is what the refit is actually doing

Strictly paired — the same 8 failures, measured both ways:

| | deficit (winner − truth) |
|---|---|
| at a fixed pose, exact GT scale and rotation | **+0.0654** |
| after the per-candidate refit | **+0.0072** |
| **fraction of the deficit the refit closes** | **89.0%** |
| gap reduced in | 6 / 8 pairs |

**The per-candidate refit recovers 89% of a deficit nobody had measured.** It takes a 0.065
disadvantage — which no scoring rule could overcome — and reduces it to 0.007, roughly 3.6x the
correlation sampling noise of ~0.002.

### Why this explains every negative in this document

The project has spent its effort hunting for **0.007** of signal while the quantity that actually
governs the outcome is **0.065**, and geometry had already taken 0.058 of it.

* **"Same criterion, better geometry" is the only stage that has ever worked** (ADR-0024) because
  reducing geometric mismatch is the only lever with any leverage. That was an empirical rule; it is
  now a measured one.
* **Six re-ranking criteria failed** because they were competing for a residual near the noise floor.
* **Isolating the aperiodic fingerprint failed** (§33) because the periodic component is what the
  refit uses to close the 0.058; removing it discards the mechanism.
* **Leave-cell-out generalisation failed** (§34) because at a fixed pose the impostor is a genuinely
  better explanation — that is exactly what 0.8615 against 0.7661 means.

**This is a ceiling for a family of methods, stated precisely.** What the experiment establishes is
that *a decision rule reading the fixed-pose correlation cannot fix these pairs* — at that pose the
truth is behind by 0.065, so no re-ranking of that surface reaches it. It does **not** establish that
no method could: a richer forward model would change the score itself rather than re-read it. That
possibility is tested directly in §36.

The honest headline is not "16% mis-lock remains". It is: **at a fixed pose the true site is behind
by 0.065; DriftLock's geometry recovers 89% of that, and the remainder is at the noise floor.**

---

## 36. What physics is the refit approximating with geometry? Measurably, almost none ✅

§35 showed the refit closing 89% of a 0.065 deficit, which raises a sharp question an external
reviewer put well: **is the optimiser using geometric freedom to compensate for a forward model that
is missing something?** If so, supplying the missing physics directly should help the true site more
than the impostor — a *differential* gain, which is the only form that matters. Two candidates, both
tested as oracles on the 8 paired failures without touching the pipeline.

### 36a. An explicit PSF degree of freedom — real, and 30x too small

The reference is rendered sharper than the search image; if the template is systematically too
sharp, correlation may prefer a wrong site whose texture happens to suit it. Sweeping a Gaussian
blur over the template at each candidate's own refitted pose:

| | |
|---|---|
| ZNCC gain, truth | **+0.0013** |
| ZNCC gain, winner | +0.0009 |
| **differential** | **+0.0003**, truth gains more in **7/8** (p = 0.070) |
| deficit, before → after | +0.0094 → +0.0091 |
| best sigma, truth / winner | 0.45 / 0.40 |

**The effect is real and it is negligible.** Seven of eight favouring the truth, with a consistent
optimum near sigma 0.45, says the template genuinely is a touch too sharp. But it buys 0.0003
against a 0.0094 deficit — it would close **3%** of the gap. The refit has already absorbed
essentially all of the available photometric mismatch.

### 36b. Spatial micro-deformation — and it goes the wrong way ❌

The other candidate: anisotropic scale plus shear, on top of the rigid pose, as a low-order stand-in
for smooth acquisition distortion the current model cannot express.

| | |
|---|---|
| gain, truth | +0.0010 |
| gain, **winner** | **+0.0014** |
| **differential** | **−0.0004**, truth better in only **4/8** (p = 1.000) |
| deficit, before → after | +0.0094 → +0.0098 |

**The impostor gains more.** Extra spatial freedom *widens* the gap by 4%.

That is not a surprise once stated — it is the same asymmetry that sank refit-*gain* ranking at
80–92% (§15d) and that the screen exists to bound (§23f): a candidate with more mismatch to absorb
has more to gain from being allowed to move. It now has a third independent measurement, and this
one is at the level of the final decision rather than the candidate field.

### The answer to the reviewer's question

**The refit is not compensating for missing physics.** It is recovering geometry, and it has taken
89% of what is there. Of the three plausible missing degrees of freedom (§36c adds the third), one
is worth 3% of the remaining gap and two are negative. There is no large unmodelled acquisition effect for the
optimiser to have been silently absorbing.

Which sharpens §35 rather than contradicting it: the 0.065→0.007 closure is real *geometry*
recovery, not an artefact of the model compensating for itself. And it explains why the shipped
architecture is shaped the way it is — rigid pose plus per-candidate refit is not an approximation to
a richer model we failed to build; on this data it is very nearly the whole of what is available.

---

### 36c. Line-jitter correction before correlation — the worst of the three ⚠️

> **⚠️ 36c DOES NOT REPRODUCE, AND THE SIGN REVERSES.** An independent implementation of the same
> blind per-row estimator measures the differential at **+0.0378 favouring the truth, 7/8**, where
> this one measured −0.0310 favouring the winner. Two implementations of a blind estimator
> disagreeing about the sign means the quantity is implementation-dependent, not that one of them
> found a result. §36a and §36b both reproduce (36b exactly). See §37.

The last forward-model lever, and the one with the best physical motivation. The generator applies
per-row shear and jitter; this pipeline's drift stage corrects the *reported coordinate*, not the
image, so the template is correlated against a patch that is still geometrically distorted.
Correcting the image first should sharpen the true peak.

Implemented blind and regularised: per-row horizontal offset by 1D correlation against the template
row, then a **quadratic fit in y** (a scan-drift prior, 3 degrees of freedom, clipped to +/-2 px) so
noise cannot drive individual rows.

| | |
|---|---|
| gain, truth | **−0.0312** |
| gain, winner | −0.0002 |
| **differential** | **−0.0310**, truth better in 2/8 |
| deficit, before → after | +0.0094 → **+0.0404** |

**It widens the gap more than fourfold**, and the mechanism is visible in the asymmetry: the winner
is essentially unaffected while the truth loses 0.031. The true site is *already well aligned*, so a
blind per-row estimate has nothing to recover and can only inject noise into a good fit. The
impostor, already misaligned, has nothing to lose.

### The pattern across all three, which is the actual result

| added degree of freedom | differential | verdict |
|---|---|---|
| PSF blur | **+0.0003** (7/8) | real, closes 3% |
| anisotropic scale + shear | **−0.0004** (4/8) | winner gains more |
| line-jitter, quadratic in y | **−0.0310** (2/8) | destroys the truth's alignment |

> **Every degree of freedom added to the forward model either helps negligibly or helps the wrong
> candidate.** The more freedom, the worse the differential — monotonically, across three
> independent parameterisations.

This is the same asymmetry as §15d (refit-*gain* ranking, 80–92% mis-lock), §23f (why the screen must
bound the field) and §36b, now measured a fourth time and at the level of the final decision. A
candidate that already fits well cannot benefit from extra freedom; one that fits badly can. Freedom
is not neutral — it is a resource that flows to whoever has more mismatch to absorb.

**Which reframes the shipped architecture as a positive design choice rather than a limitation.**
Rigid pose plus a *bounded* per-candidate refit is not an approximation to a richer model we lacked
time to build. It is the measured optimum: enough freedom to close 89% of the geometric deficit
(§35), bounded tightly enough that impostors cannot exploit it. Every attempt to loosen that bound,
in any direction, has cost accuracy.

### On the code-review challenge to §36b

An external review suggested §36b might be invalid because it passed `integrate_reference(ref, sc)`
into a warp that also applies `sc`, double-scaling the reference. Checked directly rather than
argued: `integrate_reference` returns a **1000×1000** array — it box-integrates and does *not*
resize — and the experiment's warp at `ax = sh = 0` reproduces `build_template(ref, sc, ro)` with
**max |difference| = 0.000000**. Same forward model as the shipped pipeline, bit-identical. The
result stands.

---

## 37. §35 does not reproduce: a point value was compared against a maximum ❌

**The rule that caught it was our own:** §35 was promoted to `scripts/oracle_ceiling.py` — but only
§35a was. §35b, §35c and all of §36 stayed in a scratchpad file that was later overwritten, so the
project's headline finding was the one number a judge could not regenerate. Writing
`scripts/pose_ceiling.py` to close that gap re-measured it, and it did not come back the same.

### 37a. What reproduces and what does not

*(Both columns below were measured against the configuration as it stood on the morning of 15 Aug,
when the pipeline scored 84/100. ADR-0032 later took it to 89/100, which changes the failure set
these statistics are computed over — the current figures are in `results/pose_ceiling.csv` and in
STATE §2a. This table is the record of the **retraction**, so it is deliberately left at the numbers
that were in dispute.)*

| quantity | published (§35/§36) | reimplementation | verdict |
|---|---|---|---|
| shipped correct / oracle correct | 84/100, 70/100 | 84/100, 70/100 | ✅ exact |
| oracle rescues | 1 of 16 | 1 of 16 | ✅ exact |
| ZNCC at the **true** location | 0.7661 | **0.7661** | ✅ exact |
| deficit **after** the refit | +0.0072 | **+0.0072** | ✅ exact |
| micro-warp differential (§36b) | −0.0004, 4/8 | **−0.0004, 4/8** | ✅ exact |
| ZNCC at the **winning** location | 0.8615 | **0.7696** | ❌ |
| truth out-correlates the winner | 2/15, p = 0.007 | **7/15, p = 1.000** | ❌ |
| deficit at the **fixed** pose | +0.0654 | **+0.0114** | ❌ |
| fraction the refit closes | 89.0% | **36.6%** | ❌ |
| line-jitter differential (§36c) | −0.0310, 2/8 | **+0.0378, 7/8** | ❌ sign reversed |

Every truth-side quantity reproduces to the digit. Every winner-side quantity does not. That
pattern localises the fault precisely, and it is not in the template builder, the pose, or the
candidate capture — all of which the truth side exercises identically.

### 37b. The cause: a maximum is not a measurement at a location

Scoring the same 15 failures three ways at the same oracle pose:

| where the oracle template is scored | mean ZNCC | truth ahead of it |
|---|---|---|
| at the **true** location | 0.7661 | — |
| at the location the **pipeline chose** | **0.7696** | **7 / 15** |
| at the **global maximum** of the correlation surface | **0.8915** | 0 / 15 |

The published 0.8615 and 2/15 sit with the surface maximum, not with the pipeline's answer.

**A maximum over ~810,000 positions is selected *because* it is the largest.** Comparing it against
the value at one nominated point is upward-biased by construction — the comparison cannot come out
any other way, and it does not become a measurement of the impostor by being labelled "the winning
location". What it actually says is that the argmax is not at the truth, which is §35a.

*(The reimplementation's own surface maximum is 0.8915 against the published 0.8615, and 0/15
against 2/15. The residual difference is consistent with the original having excluded a
neighbourhood of the truth or read the top of the candidate list rather than the raw surface; it
does not change which of the three columns the published figure belongs to.)*

### 37c. What is true instead — and it is a sharper result, not a weaker one

Both sides nominated, same oracle pose, same 15 failures:

> **At the generator's exact pose the true site and the site the pipeline chose are statistically
> indistinguishable: 0.7661 against 0.7696, truth ahead in 7 of 15, p = 1.000.**

And paired on the 8 failures where the truth reached the final comparison:

| | deficit (winner − truth) |
|---|---|
| at the exact oracle pose | **+0.0114** |
| after the per-candidate refit | **+0.0072** |
| **the refit closes** | **36.6%** (reduced in 7/8) |

So the correct statement of the ceiling is about **margin**, not about direction:

* The retracted version said the truth is a *worse* explanation by 0.065, which would have made
  these pairs unreachable by any rule reading that surface. **That is not what the data says.**
* What the data says is that the two sites are separated by roughly **0.003 to 0.011** of
  correlation — the level at which sampling noise and forward-model mismatch live. The truth is not
  behind; it is *tied*.

This is a better fit to everything else in this document, and it needed no special pleading:

* **Six re-rankers failed** (ADR-0024) because they were asked to resolve a margin of ~0.01. That
  remains the practical conclusion, and it rests on six direct measurements that are unaffected by
  this retraction.
* **The unifying explanation (STATE §6) is strengthened**, not weakened: evidence strong enough to
  be reliable is shared by the impostor; evidence that separates them is at the noise floor. We can
  now put a number on "at the noise floor" — about 0.01.
* **The refit's contribution is real but smaller than claimed**: it closes 36.6% of the fixed-pose
  deficit, in 7 of 8 pairs.

**What must not be said any more:** that these were "never selection errors", that "no re-ranker
could ever reach them", or that geometry recovers 89% of anything. What may be said: at the exact
pose the margin between the truth and its impostor is about 0.01, which is why six criteria failed
to resolve it, and the refit closes about a third of it.

### 37d. An open lead, flagged rather than buried

The line-jitter differential reversed sign to **+0.0378 favouring the truth in 7/8** (p = 0.070).
That is **larger than the +0.0114 fixed-pose deficit**, so if it is real it would flip these pairs.
Three reasons it is not a finding yet: n = 8, it is an *oracle* measurement rather than a pipeline
stage, and an earlier implementation of the same idea measured the opposite sign. It is recorded
here as the one live lead, to be settled the only way that counts — implemented in the pipeline and
measured on all four splits — not quoted as a result.

### 37e. The process failure, stated plainly

Two rules already in `CLAUDE.md` would each have caught this, and neither was applied:

* **R2, no number typed by hand.** These numbers never entered `results/`. They went from a
  scratchpad print straight into `FINDINGS.md`, `STATE.md`, `HANDOFF.md` and `README.md`. The
  verifier that fails the build on an untraceable deck number never saw them, because they were
  never on a slide.
* **R8, independent re-derivation.** The red-team pass covered the accuracy numbers, which are
  generated by `evaluate.py`. It did not cover the *interpretive* measurement that the whole
  argument rested on — precisely because that one had no script.

**A result with no script is not a result.** The fix is mechanical: `scripts/pose_ceiling.py` is
committed, emits `results/pose_ceiling.csv`, and is listed in the regeneration commands.

**Nothing shipped is affected.** Accuracy, runtime, the configuration and the ablation are all
untouched — 20.0 / 16.7 / 10.0, aggregate 16.0%. This retraction is entirely about what we may
claim the remaining 16 failures *mean*.

---

## 38. Global scan-field calibration: the correction is fair, and fairness is why it fails ❌

An external review proposed the one architecture the project had not tried, and proposed it for the
right reason. Every deformation experiment so far (§36b, §36c) estimated a correction from **each
candidate's own patch**, which hands every candidate its own geometry — exactly the freedom that
flows to whoever has more mismatch to absorb. The alternative: measure the scanner **once, from the
whole search image, before any candidate exists**, and correct the image every candidate is scored
against. Lattice-averaging followed by line-by-line registration is established practice for
periodic scanned microscopy, so this is not a novel gamble.

Built as `src/driftlock/scanfield.py`, measured by `scripts/global_jitter.py` into
`results/global_jitter.csv`, validated by `tests/test_scanfield.py`. ADR-0030 applied from the start.

### 38a. There is genuinely something to correct, and the estimator finds it

The generator's raster stage is `out[y, x] = clean[y, x + shear·y/(H−1) + jitter_y]`. On every
split here that is a **1.5 px** shear and a **0.5 px** per-row jitter, and they are not comparable:

| | across a 100 px footprint | reachable by the shipped pipeline |
|---|---|---|
| shear, 1.5 px end-to-end | **0.15 px** | yes — the drift stage removes its linear part |
| jitter, σ = 0.5 px, **white in y** | **0.5 px per row** | **no** — no smooth model can represent it |
| reference's own jitter | 0.5 px at 1 nm/px → **0.05 px** after ↓10 | negligible |

**The search image's per-row jitter is the largest uncorrected geometric error in the pipeline.**

The estimator recovers it. On a synthetic lattice with a jitter we chose, the residual is under half
the input RMS (`tests/test_scanfield.py`), and on real pairs the measured field RMS is **0.547 px**
against the generator's 0.500 px.

### 38b. It sharpens the true site — and the impostor by the same amount

ZNCC at the true location, at the generator's exact pose, rises **+0.0226** on ten dev pairs
(0.8553 → 0.8779), up on 8 of 10. A control that resamples the image with an all-zero field moves it
by **+0.0000**, so interpolation costs nothing and the gain is the correction.

That lift is **twice the entire +0.0114 fixed-pose deficit** (§37c). It should have been decisive.
Measured as a *differential* on the 27 dev pairs where the gates fired:

| ZNCC lift from the global correction | |
|---|---|
| at the **true** location | **+0.0297** |
| at the **chosen** (impostor) location | **+0.0301** |
| **differential** | **−0.0003**, truth lifted more in **8 / 27** |

> **The impostor is a real lattice site, imaged through the same scanner, so removing the scanner's
> jitter sharpens it by exactly as much. A global correction is fair by construction — and being
> fair is precisely why it cannot break a tie.**

This is the sharpest statement of the project's central asymmetry yet, and it arrives from the
opposite direction to all the others. §15d, §23f and §36b showed that *unfair* freedom flows to the
wrong candidate. §38b shows that *fair* improvement flows to both. **There is no third option: a
correction either privileges a candidate or it does not, and neither one selects the truth.**

It also retires §36c. Two candidate-local implementations disagreed about the sign of a per-row
jitter correction (+0.0378 against −0.0310, §37d). Neither was measuring physics — both were
measuring how much unfairness their particular estimator happened to hand each candidate. The
physical version of the same correction has a differential of **−0.0003**, at the fourth decimal,
alongside PSF blur (+0.0000, §36a) and micro-warp (−0.0004, §36b). **Every fair forward-model
improvement this project has measured lands at the fourth decimal.**

### 38c. The trap: correcting the image destroys the drift estimator

Worth recording on its own, because the obvious implementation is wrong in a way that produces no
error and no warning.

`estimate_drift_shear` measures the shear as a **median over row pairs** whose displacement is
`shear·gap/(H−1)` plus the difference of two per-row jitters. At a 1.5 px shear the signal in any
one pair is ~0.15 px and the jitter difference is ~0.7 px: **the estimator works precisely because
the jitter is zero-median noise it can average away.** Remove the jitter first and that noise is
replaced by the calibration's own correlated residual, which does not cancel.

Measured on ten dev pairs, shear estimated on the corrected image against a true 1.50:

| | |
|---|---|
| estimates on the **original** image | median 1.074 — noisy but sane |
| estimates on the **corrected** image | **−1.96, +2.89, −3.95, +17.04** — median 1.094, spread destroyed |
| position error | **0.139 → 1.173 px** |

The fix is exact rather than empirical: the correction does not touch the shear, so the shear is
read off the **original** image and applied to the coordinate found in the corrected one. That
recovers 1.173 → 0.296 px. A stage that removes noise another stage depends on is a real class of
bug, and the only reason it was caught is that the position metric moved.

### 38d. Pipeline result on dev — the split we are allowed to tune on

Frozen configuration, same pairs, the only difference being the corrected search image. *(All of §38
was measured against the configuration as it stood before ADR-0032, so "shipped" here means dev at
12.5% rather than the 7.5% it reads today. The comparison is internally paired and unaffected; only
the absolute baseline moved afterwards.)*

| dev, 40 pairs | mis-lock | median error, located | runtime |
|---|---|---|---|
| shipped | **12.5%** | **0.2575 px** | — |
| + global scan calibration | **15.0%** | 0.2963 px | **+101 ms** |
| | 0 fixed, **1 broke** | | |

**It does not improve mis-lock; it costs a pair, costs precision, and costs 26% of the runtime
budget.** The gates declined 13 of 40 pairs on estimator disagreement, so a third of the time it
correctly refuses to act.

The residual precision cost has a mechanism too. The template can only reference a row against its
own neighbourhood, so the field measured is `jitter_y − local_mean_jitter(y)`; what remains in the
corrected image is that local mean, ~0.14 px and **correlated** across nearby rows. White noise
averages away over the 100 rows of a footprint (0.5/√100 = 0.05 px); correlated noise does not.
**The correction trades white error for smaller-but-correlated error, and the matcher was already
exploiting the whiteness.**

Because the *selection* is what fails, a hybrid that took the coordinate from the original image
could recover the precision but not the mis-lock — the sites chosen are the ones measured above. Not
built, for that reason.

### 38e. Judged in the regime it targets — and it has no operating regime

ADR-0027 is the standing warning here: the median filter sat switched off for three days on a "no
effect" measured against data with no impulse noise. Every reporting split is generated at the same
nominal **0.5 px** jitter, so measuring a jitter corrector only there would repeat that mistake
exactly. Two stress splits, 6× apart, validation-only seeds:

| split | jitter σ | base mis-lock | with calibration | applied |
|---|---|---|---|---|
| dev | 0.5 px | 12.5% | **15.0%** (0 fixed, 1 broke) | 27 / 40 |
| `_stress/jitter15` | 1.5 px | 25.0% | **25.0%** (0, 0) | **0 / 24** |
| `_stress/jitter3` | 3.0 px | 63.3% | **63.3%** (0, 0) | **0 / 30** |

**Above the nominal jitter the gates decline every single pair** — the two estimators disagree by
2.0–2.7 px at σ = 1.5 and 2.2–3.9 px at σ = 3.0, against a 0.75 px tolerance. The gate is working;
there is simply nothing trustworthy to measure.

And the reason is structural rather than a tuning limit:

> A per-row lag search must stay below **half the lattice period** or the row locks onto the
> neighbouring repeat. At the DRAM bit-line pitch of 96 nm that is ~4.8 px at 10:1. **The
> correctable jitter range is bounded by exactly the periodicity that makes the localization problem
> hard in the first place.**

So the stage fires only in the regime where the jitter is small enough not to matter, and refuses in
every regime where it would. **There is no operating point at which it both fires and helps** — this
is not ADR-0027's mistake repeated, it is three regimes across a 6× range with the same answer.

### 38f. A defect in this experiment, found and fixed

The first jitter3 run reported **2 fixed and 3 broke on a split where the calibration never fired
once**. That is impossible if the arms are identical when the gates decline — and they were not: the
shipped drift stage sizes its row separation with `gap_for_rotation(measured_rotation)`, while the
reroute in §38c calls `estimate_drift_shear` at its default gap. The declined arm now reuses the
base result by construction, and the clean re-run is **63.3% → 63.3%, 0 fixed, 0 broke**.

Worth recording because the wrong version was *plausible* — five pairs moving on a heavy stress
split reads like a real effect, and it would have been reported as one.

### 38g. What this settles

The review that proposed this was right about the architecture and right that it was untested. The
answer is not "the idea was bad" but something more useful:

* **Global is the correct design.** The candidate-local versions (§36c) were not measuring physics;
  they were measuring how much unfairness their particular estimator handed each candidate, which is
  why two implementations disagreed about the sign. Building it fairly resolved that contradiction.
* **And fairness is fatal.** A correction applied to the whole image lifts every lattice site
  equally, because every lattice site was imaged through the same scanner. There is no third
  option: a correction either privileges a candidate or it does not, and neither selects the truth.
* **The forward model has nothing material left in it.** Four independent additions — PSF blur
  (+0.0000), micro-warp (−0.0004), candidate-local jitter (contradictory), global scan field
  (−0.0003) — all land at the fourth decimal against a margin of 0.0114.

Not shipped. `src/driftlock/scanfield.py` is kept, tested and unreferenced by the pipeline, because
the measurement is the deliverable.

---

## 39. Supercell search: the only higher-order structure is the one blind to our failure ❌

The second idea from the same review, and the cheapest high-information experiment available. If the
array were secretly `A B A C A B A D` rather than `A A A A`, a site would carry a *context* even
though a cell does not, and identity would be readable from structure instead of from an aperiodic
fingerprint sitting near the noise floor. That would attack the failure mechanism without inventing
a new final score — the one shape of idea this project had not exhausted.

`scripts/supercell.py` → `results/supercell.csv`. 72 measurements: 6 pairs × 3 splits × both images
× both axes.

### 39a. The statistic, and the null that makes it mean anything

Correlate each image with itself displaced by `k` primitive lattice periods, k = 1…24. A plain
lattice gives a smoothly decaying `r(k)`. A supercell of order N adds a **modulation** — `r(k)` runs
high whenever k is a multiple of N, because those displacements land on the same cell type. Detrend
`r(k)` in log-k, then take the strongest spectral component of the residual.

**The first run of this was uninterpretable and it is worth saying why.** It reported a median
"modulation strength" of 0.94, which reads like a strong effect. It is not: on a 24-point series the
largest of ~12 spectral components is *naturally* about one RMS. The statistic is scale-free but not
self-calibrating. A 400-permutation null — shuffle the residual, which destroys ordering while
preserving the values exactly — is what turns it into a measurement. Given §37, shipping a
statistic without its null was not an option.

### 39b. There IS higher-order structure, and it is order 2

| | |
|---|---|
| measurements with p < 0.05 | **33 / 72** (3.6 expected by chance) |
| measurements with p < 0.01 | 17 |
| median p | 0.057 |
| order among the significant hits | **2 → 17 hits**, 3 → 6, 24 → 6 (series length, a detrend artifact), others → 4 |

So the array is not a plain lattice, and the statistic is sensitive enough to prove it. But the
order is **2**, and order 2 is the `(i+j)%2` contact checkerboard — H8, confirmed on day one and
already modelled by the generator. Nothing at order 4, 8 or any larger repeating motif survives.
That is exactly what the generator predicts: line positions are a random walk
(`pos += pitch + N(0, 1.5 nm)`, H7), and a random walk has no repeating motif to find.

### 39c. Why the structure that exists cannot help

> **The dangerous confusion is the parity-*preserving* diagonal shift** (+1 word-line *and* +1
> bit-line, H8). By construction that shift leaves `(i+j)%2` unchanged.

So the single piece of higher-order periodic structure in these images is precisely **blind to the
one confusion that produces our failures**. A parity-aware test rejects single-axis shifts — which
the pipeline already gets right — and says nothing whatever about the diagonal shift, which is what
it gets wrong.

This is a negative result with a positive control inside it: the method detected real structure at
9× the chance rate, so its silence about larger orders is evidence rather than insensitivity.

---

## 40. Is the MAXIMUM the wrong statistic? Split-inconsistent, and my explanation was wrong ⚠️

The strongest idea in the latest review, and the only one that is not a new criterion. ADR-0024 bans
re-ranking by a *new* criterion; this re-reads the *same* ZNCC from the *same* pose grid the refit
already computes, summarised differently.

The motivation is our own measurement. §23f found that handing a wide pose bracket to the whole
candidate field is worse than handing it to ten survivors — a wide search helps impostors **more**.
That is a multiple-comparisons effect: every candidate gets 25 attempts at a flattering pose, and a
candidate whose pose surface is rough has more chance of getting lucky than one whose surface is
flat and genuinely high.

| | pose grid | max |
|---|---|---|
| truth | 0.762 0.768 0.766 0.764 0.765 | 0.768 — consistently good |
| impostor | 0.751 0.752 **0.769** 0.753 0.750 | 0.769 — one lucky sample |

`scripts/pose_evidence.py` caches every pose grid once (1400 candidates, 140 pairs, 100% with a
grid) and sweeps selectors offline, so every arm sees identical data and the comparison is exactly
paired. Free parameters chosen on `dev` and frozen before the reporting splits were scored (R5).

### 40a. It works — on one split, and backwards on another

| selector | sponsor | bench | FinFET | aggregate | flips | McNemar |
|---|---|---|---|---|---|---|
| **max** (shipped) | 20.0% | 13.3% | 10.0% | 15.0% | — | — |
| top-3 mean | 20.0% +1/−1 | 16.7% +0/−1 | 6.7% +1/−0 | 15.0% | 54 | 1.000 |
| **log-sum-exp, β=5** | **5.0% +6/−0** | **20.0% +1/−3** | 6.7% +1/−0 | **10.0%** | 49 | 0.227 |
| grid mean | 10.0% +5/−1 | 20.0% +1/−3 | 6.7% +1/−0 | 12.0% | 46 | 0.549 |
| max − λ·std | 22.5% +0/−1 | 13.3% +0/−0 | 10.0% +0/−0 | 16.0% | 10 | 1.000 |

**On the sponsor's own distribution, integrating instead of maximising fixes six pairs and breaks
none** — 20.0% → 5.0%, and 6/0 alone is p = 0.031. On our bench it goes the other way, +1/−3.
Aggregate p = 0.227.

*(These are candidate-selection numbers read off the cached grids, before sub-pixel and drift
correction, so they are not the shipped rates — `max` reads 13.3% on bench where the pipeline
reports 16.7%. All five arms share that proxy, so the paired comparison is valid and the absolute
values are not quotable.)*

### 40b. My explanation was wrong, and the test says so

The obvious mechanism: the sponsor split is fixed at 10:1 and 0° (H9), so its pose grid straddles
the true pose and every sample is near-optimal — averaging is nearly free there, while on our data
part of the grid covers genuinely wrong poses and averaging mixes them in. That predicts the split
pattern. It is also testable *within* a split, which is the stronger comparison (ADR-0029).

| bench + FinFET, split at the median pose offset | n | max | lse | fixed | broke |
|---|---|---|---|---|---|
| near-nominal pose | 30 | 3 | 4 | 1 | 2 |
| far from nominal | 30 | 4 | 4 | 1 | 1 |

**No difference.** Integration does not help more where the pose is near-nominal, so the mechanism I
proposed is not the one operating. The sponsor gain is real and currently unexplained.

### 40c. The bug that made it look catastrophic, and what it teaches

Implemented in the pipeline behind `pose_evidence_beta`, the first run made things dramatically
**worse** — the four sponsor failures went from 14.4, 14.3, 21.5 and 95.2 px to 57.6, 57.4, 37.5
and 271.7 px.

The cause is worth stating precisely because it generalises. `refit_candidates` returns the
screened-out candidates merged back in, and **their grids come from the 2×2 narrow screen rather
than the 5×5 wide pass**. A narrow grid is flat and high by construction — every sample sits near
the candidate's own pose — so its log-sum-exp is close to its maximum, while a wide grid necessarily
includes poses that are wrong and averages lower. Ranking the two together compares statistics
computed over *different supports*, and systematically promotes exactly the candidates the screen
had already rejected.

> **A statistic is only comparable over the same support.** The maximum happens to be robust to this
> — it is the same maximum whatever the grid — which is precisely why the defect was invisible until
> the summary changed.

Restricting the re-order to the wide-refit survivors fixes it, and the same three sponsor failures
then resolve to **0.053, 0.032 and 0.111 px**, with correctly-located pairs unchanged to the fourth
decimal.

Note that the offline sweep was **unaffected**: it caches only the top ten candidates, and those
were all survivors. So the proxy and the pipeline disagreed for a reason that existed only in the
pipeline — which is exactly why a proxy result is a reason to run the real thing rather than a
substitute for it.

### 40d. Pipeline confirmation, all four splits

The frozen configuration against the same configuration with `pose_evidence_beta = 5`, same pairs,
paired:

| split | shipped | + pose evidence | |
|---|---|---|---|
| dev *(tuning)* | 12.5% | **7.5%** | +2/−0 |
| sponsor | 20.0% | **5.0%** | +6/−0 |
| bench | 16.7% | 23.3% | **+1/−3** |
| held-out FinFET | 10.0% | **6.7%** | +1/−0 |
| **reporting aggregate** | **16.0%** | **11.0%** | +8/−3, p = 0.227 |

Over all 140 pairs including dev: **+10/−3, exact McNemar p = 0.092**.

Three of four splits improve, including both held-out ones, and the cost is nothing — the stage
re-reads numbers the refit has already computed, so it adds no correlations and no measurable
runtime. Against that: **bench regresses**, and one split moving the wrong way is the pattern behind
ADR-0012 and ADR-0021.

Two things temper the bench result. It is 3 discordant pairs out of 30, and ADR-0029 measured two
*identically-parameterised* splits at 20.0% and 26.7% — a 6.7-point swing from seed alone, so a
10-point swing on n = 30 is inside the documented noise. And bench is not distinguished from FinFET
by generator or envelope: both are ours, same 9–11:1 and ±2°, and FinFET improved.

### 40e. The 160-pair split settles it — and the stage ships

`dev2` had 160 generated pairs sitting unused. Running the same paired comparison there roughly
triples the evidence:

| dev2, 160 pairs | mis-lock | |
|---|---|---|
| shipped | 11.2% | |
| + pose evidence | **6.9%** | **+7 / −0**, exact McNemar **p = 0.016** |

Seven fixes, zero breaks, on the largest split available. Pooling every split measured:

| split | n | fixed | broke |
|---|---|---|---|
| dev | 40 | +2 | 0 |
| dev2 | 160 | +7 | 0 |
| sponsor | 40 | +6 | 0 |
| bench | 30 | +1 | **3** |
| held-out FinFET | 30 | +1 | 0 |
| **total** | **300** | **+17** | **3** |

> **Exact McNemar over 300 paired pairs: p = 0.0026.** Four splits of five improve with **zero**
> breaks, and the one regression is 3 pairs out of 30 — inside the seed-to-seed noise ADR-0029
> measured on identically-parameterised splits.

**Shipped.** It clears every bar this project has set for a selection change:

* it is not a new criterion — same ZNCC, same grid, different summary, which is what ADR-0024
  actually permits;
* its one free parameter was chosen on `dev` and confirmed on four splits that had no part in
  choosing it;
* it improves the two genuinely held-out splits (sponsor's independent generator, and a held-out
  architecture);
* **it costs nothing.** The grid is already computed by the refit; this re-reads numbers rather
  than adding correlations, so there is no runtime change to trade against.

The mechanism is still not fully explained — §40b refuted the pose-offset hypothesis — and that is
stated rather than papered over. What is established is the effect, its size, and its sign, on 300
paired pairs.

### 40f. The failure decomposition confirms it acted where it should

The decomposition (§3) splits every failure by the stage that lost it, and it was regenerated after
the change without being consulted first:

| stage that lost it | before | after |
|---|---|---|
| never a candidate | 3 | **3** |
| cut by the screen | 4 | **4** |
| **outscored at the final comparison** | **9** | **4** |

**The stage cut the outscored bucket by more than half and left the other two exactly where they
were.** Outscored is the only bucket a selection change can touch — a candidate that was never
proposed, or was cut before the wide refit ran, is out of its reach by construction. So this is not
a headline number moving for an unexamined reason; it is the predicted bucket moving and the other
two holding still.

That is also the sharpest available answer to the §37 question of whether the remaining failures
were *selection* errors. Some of them were, and the margin that decided them was recoverable — not
by scoring harder, but by reading the score that was already there without the maximum's bias.

### 40g. The pose surface has nothing left in it beyond mean-versus-max ❌

The obvious follow-up, and the review's top recommendation once §40 landed: if reading the grid as
evidence beats reading its maximum, read *more* of it. The grid is a likelihood over the nuisance
pose, so its **shape** should carry information a single interpolation between mean and max cannot —
how concentrated the evidence is, and how many independent chances the candidate really had.

Four more statistics, on the same cached grids, so the comparison is exactly paired and costs
nothing. All parameters chosen on `dev` and frozen; **the reference is the shipped LSE**, not the
maximum it already replaced, so nothing re-credits a gain that is already banked.

| selector | sponsor | bench | FinFET | aggregate |
|---|---|---|---|---|
| **lse β = 5 — shipped** | **5.0%** | 20.0% | **6.7%** | **10.0%** |
| grid mean | 10.0% | 20.0% | 6.7% | 12.0% |
| plain maximum | 20.0% | 13.3% | 10.0% | 15.0% |
| top-3 mean | 20.0% | 16.7% | 6.7% | 15.0% |
| `max − λ·σ` | 22.5% | 13.3% | 10.0% | 16.0% |
| **extreme-value, effective trials** | 22.5% | 13.3% | 10.0% | 16.0% |
| peakiness (`max − median`) | 25.0% | 13.3% | 10.0% | 17.0% |
| **entropy-penalised** | 25.0% | 16.7% | 10.0% | 18.0% |

**Every one is worse, and each breaks 6–8 sponsor pairs the LSE gets right.**

Two of these were designed to be the principled version of something that already half-worked. The
effective-trials correction estimates `N_eff` per candidate from the lag-1 autocorrelation of its
own surface — a fixed look-elsewhere term cannot reorder anything, because every candidate draws the
same number of samples, so smoothness is the only thing that differs. It is the right correction and
it does not help. The entropy penalty asks whether the true site concentrates its evidence and the
impostor spikes; it makes things measurably worse.

> **The usable direction is toward averaging, and everything that adds surface *shape* degrades.**
> `mean` (12.0%) is the closest competitor to `lse β=5` (10.0%); every statistic that reads the
> grid's structure rather than its central tendency lands at 15–18%.

So the pose surface is not a rich object with more to extract. It is a noisy sample of one number,
and the whole value of §40 is that averaging estimates that number better than maximising does. That
also explains why β = 5 sits near the mean end of the family rather than at some interesting middle.

### 40h. Where the truth actually sits in the screen's ranking

The review's next target was the screen: 4 of the 11 remaining failures are lost there, so an
uncertainty-preserving cut should recover them. That sits oddly against §23d, which measured
`refit_screen_top_n` at 6, 10, 15 and 20 and found it **flat**. Both cannot be true unless the truth
is ranked far below any of those cuts — so measure the rank before building anything.

All 11 failures, with the rank the *screen* assigns the true site among 60 candidates:

| where the truth is | failures | ranks |
|---|---|---|
| **absent** — never a candidate | 3 | — |
| **survives the screen and still loses** | 4 | 0, 0, 0, 2 |
| **cut by the screen** | 4 | **12, 14, 25, 29** |

On *correct* pairs the truth's screen rank is median **0**, p90 **0** — the screen is excellent
almost always, and these four are its genuine misses.

**And the contradiction resolves.** A top-15 cut reaches two of them, a top-30 cut reaches all four.
§23d found widening flat because *recovering a candidate is not winning*: the truth entered the wide
refit and then lost the final comparison to the plain maximum. **ADR-0032 replaced that selector.**
So the question is open again for a reason, not out of optimism — measured in §40i.

### 40i. The screen widens, and it is strictly dominant ✅

Same frozen configuration, only `refit_screen_top_n` varying, every pair scored under all four cuts:

| `top_n` | dev | sponsor | bench | FinFET | reporting | runtime |
|---|---|---|---|---|---|---|
| **10** *(was shipped)* | 7.5% | 5.0% | 23.3% | 6.7% | **11.0%** | ×1.00 |
| 15 | 7.5% | **0.0%** | 23.3% | 6.7% | 9.0% | ×0.96 |
| 20 | 7.5% | **0.0%** | 23.3% | 6.7% | 9.0% | ×1.01 |
| **30** | **5.0%** | **0.0%** | **20.0%** | 6.7% | **8.0%** | ×1.05 *(see caveat)* |

> **+4 fixed, 0 broken over 140 pairs. Not one split regresses, and the sponsor split reaches
> 0.0% mis-lock.**

Three things make this shippable rather than a lucky draw:

* **`dev` alone selects 30** (5.0% against 7.5% at every narrower cut), so the choice is made on the
  tuning split and the reporting splits only confirm it (R5).
* **Zero breaks everywhere.** The exact McNemar is p = 0.125 — four discordant pairs all falling one
  way is the best attainable outcome at this sample size, exactly as ADR-0029 describes.
* **The cost is well below ×3, but it is NOT yet cleanly measured.** The ×1.05 above comes from the
  interleaved sweep, which held conditions constant across configurations but ran on a loaded
  machine, and a loaded machine compresses relative differences. The clean re-measure was rejected
  by the benchmark's own gate: **baseline control 76 ms against a quiet-machine 22 ms.** The
  ratio-to-baseline column drifts as well, because the heavier workload throttles harder than the
  control (20.8x before, 25.9x while throttled). Honest bound: **between ×1.05 and roughly ×1.9,
  pending a settled-machine run.** What is structural is that tripling the candidate count does not
  triple the work - the wide refit groups candidates by pose and builds each template once (§23's
  hoist), so extra candidates cost correlations, not template construction.

**And it only works now.** This is the same knob §23d closed. What changed is not the knob but what
receives its output: a wider field hands impostors more chances (§23f), and the plain maximum is
precisely the statistic that cashes those chances in. Once selection stopped rewarding the luckiest
sample, the cost of a wider field fell below its benefit.

That is a general lesson worth more than the three points: **a parameter measured as "flat" is flat
against the pipeline it was measured in.** ADR-0027 said stages must be judged in the regime they
target; this says the same about *configuration*, and the trigger to re-open it was a contradiction
between two of our own recorded results rather than a new idea.

**The ablation makes the interaction explicit, and it is the cleanest evidence in the document:**

| configuration | sponsor | bench | FinFET | aggregate |
|---|---|---|---|---|
| **DEFAULT** — top_n = 30 **+** pose evidence | **0.0%** | 20.0% | 6.7% | **8%** |
| top_n = 10 + pose evidence | 5.0% | 23.3% | 6.7% | 11% |
| top_n = 30, **no** pose evidence | 20.0% | 16.7% | 10.0% | 17% |
| top_n = 10, no pose evidence | 20.0% | 16.7% | 10.0% | 17% |

> **The last two rows are identical to the decimal.** Widening the screen without the evidence
> selector is worth *exactly nothing* — which is §23d's flat result, reproduced on demand. The two
> stages are not additive; the second only exists because the first landed.

**The decomposition confirms the mechanism, again without being consulted first:**

| stage that lost it | before §40 | after §40 | after §40i |
|---|---|---|---|
| never a candidate | 3 | 3 | **3** |
| **cut by the screen** | 4 | 4 | **0** |
| outscored at the final comparison | 9 | 4 | 5 |

**The screened bucket is empty.** Three of the four recovered pairs became correct outright; one
reached the final comparison and lost there, which is why *outscored* ticks from 4 to 5. Each of the
two stages moved exactly the bucket it addresses and left the others alone — and *absent* has not
moved at all through any of this, because nothing yet built touches candidate generation.

---

## 42. The three invisible sites: each is found by a different representation ✅

After §40i the failure decomposition is **3 absent / 0 screened / 5 outscored**, and `absent` is the
one bucket nothing built so far can reach — the true site never enters the candidate set, so no
selection rule of any kind applies. It is also the only bucket that has not moved through any change
made in this project.

The tempting move is to build a proposal-union pipeline. `scripts/proposal_forensics.py` exists to
avoid doing that blind, and asks the cheap diagnostic question first: **does any representation have
a peak near the truth?** If none does, the information is not there and a union cannot conjure it.

Every representation is scored at the generator's **exact recorded pose**, so none is ever blamed
for a pose error, and the truth's rank is taken among the top 30 non-maximum-suppressed peaks at the
pipeline's own suppression radius.

| absent failure | intensity | edge | variance | residual |
|---|---|---|---|---|
| bench 4 | ABSENT | ABSENT | **6** | ABSENT |
| bench 17 | 13 | **1** | 12 | ABSENT |
| finfet 17 | ABSENT | ABSENT | ABSENT | **0** |
| **controls — pairs already solved** | 10/12 | 10/12 | **11/12** | **11/12** |

> **All three are visible, and no single representation sees more than two of them.** Variance finds
> bench 4 and bench 17; the residual finds finfet 17, which variance misses entirely. The union of
> intensity + variance + residual covers all three.

Three things worth stating precisely:

* **`bench 17` is partly a pose failure, not a representation failure.** Plain intensity ranks it
  13th at the *oracle* pose, so the information was always in the channel the pipeline already uses
  — the pipeline lost it because it was searching at an estimated pose.
* **The residual is not PADM.** §8's PADM removed periodic frequencies with a Fourier mask and used
  the result as a *ranking* score with two tuned constants, and it overfit. This builds the periodic
  prediction by averaging the image over its own lattice translations, subtracts it, and uses the
  result **only to propose locations**. A representation can be useless at ranking and still be
  useful at proposing; those are different claims, and only the first was ever tested.
* **The controls are the evidence.** A representation that ranked the truth first everywhere would
  have found nothing. Variance and the residual rank it in the top 30 on 11 of 12 pairs the pipeline
  already solves *and* on cases plain intensity cannot see at all.

**A methodological note on this measurement.** The first version used a suppression radius of
`0.6 × template size` = 60 px and reported the truth ABSENT on 4 of 12 pairs the pipeline solves
correctly. That is a property of the measurement, not of the representations: suppressing a 60 px
neighbourhood deletes the truth whenever a stronger repeat sits within half a footprint. The
pipeline's own radius is 6 px — a fraction of a *lattice pitch*, not of the template.

### 42b. The union converts two of the three, and costs 1.6× runtime

Built as `src/driftlock/proposals.py`: each channel proposes locations at the same poses as the main
pass, and proposals are merged by **position only**. Their scores come from a different surface and
never enter the comparison — the existing ZNCC and the existing refit re-score everything on the
original intensity image. That is what keeps this a *coverage* change rather than a ranking one, and
what stops it drifting into ADR-0024 territory by accident.

On the three sites the pipeline could not see:

| absent failure | shipped | + variance, residual |
|---|---|---|
| bench 4 | 148.572 px | **0.142 px** |
| finfet 17 | 73.402 px | **0.271 px** |
| bench 17 | 66.891 px | 66.891 px — unchanged |

`bench 17` resists even with the `edge` channel added, and the reason is instructive: edge ranked it
**1st at the oracle pose**, but the pipeline searches at an *estimated* pose. The channel sees the
site; the pipeline never looks there. That is a pose failure wearing a representation failure's
clothes.

| variant | dev *(tuning)* | sponsor | bench | FinFET | total | runtime |
|---|---|---|---|---|---|---|
| **off — shipped** | 5.0% | 0.0% | 20.0% | 6.7% | **8.0%** | ×1.00 |
| variance + residual, k=5 | 5.0% **+0/−0** | 0.0% | 16.7% | 3.3% | **6.0%** | **×1.62** |
| variance + residual, k=10 | 7.5% **+0/−1** | 0.0% | 16.7% | 6.7% | 7.0% | ×1.66 |
| + edge, k=5 | 5.0% +0/−0 | 0.0% | 16.7% | 3.3% | 6.0% | ×1.84 |
| + edge, k=10 | 7.5% +0/−1 | 0.0% | 16.7% | 6.7% | 7.0% | ×1.89 |

**+2 fixed, 0 broken on the reporting splits, p = 0.500.** The `edge` channel buys nothing over
variance + residual and costs a further 0.22×, so it is out on its own evidence.

**`dev` says nothing, and that matters.** +0/−0 on the one split the configuration may be chosen
from. All dev contributes is ruling out k = 10, which breaks a pair. Taken alone that is exactly the
shape of a result that should not ship — a gain visible only on splits that are not allowed to
select it (ADR-0012, ADR-0021).

So the 160-pair `dev2` split was run as the strongest independent evidence available:

| split | n | shipped | + variance, residual | |
|---|---|---|---|---|
| dev *(tuning)* | 40 | 5.0% | 5.0% | +0/−0 |
| **dev2** | 160 | 6.9% | **5.6%** | **+2/−0** |
| sponsor | 40 | 0.0% | 0.0% | +0/−0 |
| bench | 30 | 20.0% | **16.7%** | +1/−0 |
| held-out FinFET | 30 | 6.7% | **3.3%** | +1/−0 |
| **total** | **300** | | | **+4 / −0** |

> **Four fixed, zero broken across 300 pairs, exact McNemar p = 0.125** — every split improves or
> holds, and the reporting aggregate is 8.0% → 6.0%. That is the same signature as ADR-0034.

**But it is not free, and that is the whole of the decision.** ×1.62 runtime against a figure that
is already above this project's own 300 ms target and, as of this writing, **not certified at all**
(§40i). Accuracy is bought here, not found.

### 42c. One channel does all the work, and the other two are pure cost

The sweep above compared *unions*, which cannot say which channel earned anything. Measured
separately, on the reporting splits:

| channel, alone | sponsor | bench | FinFET | total | candidate pool |
|---|---|---|---|---|---|
| off | 0.0% | 20.0% | 6.7% | **8.0%** | 60 |
| variance | 0.0% | 20.0% | 6.7% | **8.0%** | 63 |
| **residual** | 0.0% | **16.7%** | **3.3%** | **6.0%** | 63 |
| edge | 0.0% | 20.0% | 6.7% | **8.0%** | 63 |
| variance + residual | 0.0% | 16.7% | 3.3% | 6.0% | 66 |

> **The residual carries the entire gain. Variance and edge contribute nothing and cost runtime.**

**And the provenance says the mechanism is the intended one**, which is the check that separates a
rescue from an accident:

| variant | truth proposed by intensity | by variance | by residual | never proposed | winner from an auxiliary channel |
|---|---|---|---|---|---|
| off | 97 | — | — | **3** | — |
| residual | 97 | 0 | **2** | 1 | `residual: 1` |
| variance + residual | 97 | 1 | 2 | **0** | `residual: 1` |

The auxiliary channels are not manufacturing impostors that then win — across 100 pairs exactly
**one** auxiliary-proposed candidate ever wins, and it is a rescue. Three outcomes look identical in
an aggregate mis-lock number (rescuing the truth, duplicating a site intensity already found,
proposing a new impostor), and only provenance tells them apart.

### 42d. Oracle-pose visibility does not transfer — in either direction

§42's forensics said `bench 4` was found by **variance** (rank 6) and that the residual could not see
it at all. End to end, the opposite is true: `variance` alone fixes nothing, and the residual fixes
both bench and FinFET.

The forensics measured visibility at the generator's **exact** pose. The pipeline searches at an
*estimated* pose, and which representation survives that difference is not predictable from the
oracle measurement. §42 already noted this for `bench 17` — where intensity sees the site at rank 13
but the pipeline never looks there — and assumed it cut one way. It cuts both.

**So the oracle forensic is a screening tool, not a design tool.** It answers "is the information
present anywhere?", which is worth knowing before building. It does not answer "which channel should
ship", and the per-channel end-to-end ablation is the only thing that does.

### 42e. What shipped, and the side effect it caused

`proposal_channels = "residual"`, `proposal_top_k = 3` — k = 3, 5 and 8 measure identically, so the
fewest extra candidates wins on parsimony rather than on reporting-split performance. Reporting
aggregate **8.0% → 6.0%**; sponsor 0.0%, bench 16.7%, FinFET 3.3%.

The decomposition, regenerated afterwards:

| stage that lost it | before §42 | after |
|---|---|---|
| **never a candidate** | 3 | **1** |
| cut by the screen | 0 | **1** |
| outscored at the final comparison | 5 | **4** |

**Two of the three invisible sites are recovered — and one new failure is created.** `finfet 25` was
outscored at screen rank 29; the extra proposals inflate the pool and push it to rank **32**, past
the top-30 cut, so it is now `screened`. That is the honest cost of coverage: a wider pool has more
competition in it, and a candidate sitting one place inside the cut can be displaced by candidates
that are themselves useless. Net −2 failures, but not a free win.

The one remaining `absent` is **bench 17**, which §42 already identified as partly a *pose* failure:
plain intensity ranks it 13th at the oracle pose, so the information is in the channel the pipeline
already uses and the pipeline simply never looks there. No proposal channel fixes that; a better
pose bracket might.

---

## 43. H11: the sponsor's fields are pitch-heterogeneous; ours are uniform ✅

Looking at the sponsor's own published sample images — rather than at their source — settles a
structural question nobody had asked. Their 10× search image shows eight mats whose **pitches
visibly differ**: a coarse bright grid beside a very fine one beside a high-contrast wide one. Their
`src/presets.py` has six DRAM presets spanning **48 nm to 240 nm** of bit-line pitch, a 5× range.

Measured directly, dominant x-period per 3×3 block of the search image:

| | block periods (px) | spread |
|---|---|---|
| **sponsor, id 0** | 23.8, 7.2, 17.6 / 14.5, 14.5, 18.6 / 14.5, 10.7, 9.5 | **16.6** |
| sponsor, id 1 | 9.5, 7.1, 14.5 / 7.2, 14.5, 7.1 / 10.7, 9.5, 14.5 | 7.4 |
| sponsor, id 2 | 7.2, 23.8, 7.3 / 7.2, 7.2, 9.5 / 10.7, 10.7, 23.9 | 16.7 |
| **ours, bench id 0** | 23.8 × 9 | **0.1** |
| ours, bench id 1 | 6.8 × 9 | 0.0 |
| ours, bench id 2 | 23.8 × 8, 25.7 | 1.9 |

> **The sponsor's search fields carry substantial spatial variation in lattice pitch, consistent
> with several layout/preset types in one image. Ours are near-uniform** — `_pick_preset` is called
> once per sample and the whole canvas is built from it.

*Stated at exactly the strength the evidence supports.* The measurement establishes **pitch
heterogeneity within their fields and near-uniformity within ours**. It does not establish that the
generator assigns one preset per mat — that would need their layout source, which the published
summary does not expose. The visual impression from their sample images is consistent with per-mat
variation, and it is left as an impression.

### Why this matters more than it looks

**It explains the sponsor split being easier than our own bench.** On a multi-pitch field, most mats
are trivially wrong — a reference whose lattice is 9.6 px cannot be confused with a mat at 23.8 px,
because ZNCC collapses. The effective impostor population is only the mats that share the
reference's preset. On our uniform field **every mat is a plausible impostor**.

That reframes the reporting table. sponsor is at 0.0% and our bench at 16.7%, and the natural
reading is that we tuned to the sponsor. The measurement points the other way: **our uniform-pitch
generator removes the cheap pitch-based rejection cue and therefore stress-tests within-pitch
ambiguity far more aggressively.** How much of the 0.0%-versus-16.7% gap that accounts for is *not*
established here — only that a mechanism exists which cuts in that direction.

### What is NOT claimed

This does not say the evaluation data will be easy. It says one specific axis — inter-mat pitch
diversity — is present in the sponsor's generator and absent from ours, and that its presence
*reduces* ambiguity rather than adding it. Our splits are the conservative case on this axis, which
is the right side to be wrong on.

**Deliberately not "fixed".** Adding multi-preset mats to our generator would make our numbers look
better while testing less. The uniform-pitch field is retained precisely because it is the harder
one, and this section is the evidence for saying so rather than an assertion that our data is
harder.

---


## 44. The bucket that was never in the decomposition: a correct pick, moved off ✅

The failure decomposition has sorted every mis-lock into ABSENT / SCREENED / OUTSCORED since §30.
All three are ways of **choosing** the wrong candidate. It never had a bucket for choosing the right
one and then moving off it, so for six days that failure mode could not be counted — and one of the
six remaining failures was it.

### 44a. How it surfaced: a forensics file that could not have been right

`results/failure_mechanism.csv` reported `score_margin = 0.0` on all four outscored failures, with
`winner_scale` and `truth_scale` identical to the last decimal in every row. That is not a
measurement, it is a fixed point: the script was comparing the truth against itself.

The cause is ADR-0032. `failure_decomposition.py` hooks `_refit_once` and reads the winner off
`out[0]`, but two things happen after that call returns — `refit_candidates` merges the screened-out
candidates back in, and the pipeline then re-orders the wide-refit survivors by pose evidence before
taking `candidates[0]`. **The truth is frequently still rank 0 by refit score while losing on
evidence**, which is exactly the effect ADR-0032 introduced, so `out[0]` *was* the truth on all four.
`pose_ceiling.py` had been fixed for this; the fix was never propagated.

Corrected, the same four pairs report something worth knowing:

| pair | ZNCC margin | evidence margin | truth rank |
|---|---|---|---|
| `bench 3` | **−0.0018** | +0.0014 | 2 |
| `bench 13` | **−0.0312** | +0.0105 | 3 |
| `bench 19` | **−0.0060** | +0.0003 | 1 |
| `bench 21` | 0.0000 | 0.0000 | **0** |

The ZNCC margin is **negative** on three of four: the truth correlates *better* and still loses,
because since ADR-0032 the pipeline does not rank on correlation. That is the stage working as
designed — it buys 5 pairs and costs these — but it had never been visible.

And `bench 21` has truth rank **0**. The pipeline picked the true candidate and reported 6.54 px.

### 44b. Which stage moves the answer, measured

`scripts/refine_forensics.py` records the position after each of the three stages that run once a
candidate is committed to. Over 354 pairs:

| stage | median | p95 | max |
|---|---|---|---|
| `_refine_pose_local` | 0.000 px | 0.000 | 1.000 |
| sub-pixel DFT | 0.250 px | 0.424 | 0.707 |
| **drift correction** (clean 300) | **0.652 px** | **2.077** | **24.254** |
| **drift correction** (all 354, incl. jitter stress) | **0.713 px** | **3.772** | **33.937** |

The first two stages are bounded by construction — a pose polish and a sub-pixel peak fit cannot
move an answer far — and they stay bounded under stress. The drift stage is neither.

Two pairs in the 300 clean ones select within 5 px of ground truth and are reported past it. Both
are the drift stage; nothing else in 300 pairs is:

| pair | selected at | reported at | \|shear\| |
|---|---|---|---|
| `dev2 100` | 0.789 px | 23.478 px | **50.386** |
| `bench 21` | 0.923 px | 6.539 px | **14.751** |

The generator's true shear is **1.50 px on every split**. These are not large corrections, they are
wrong ones — and the stage is terminal, so nothing downstream can catch them.

### 44c. Why the threshold is not a tuned knob

On the 283 clean pairs correct today, `|shear|` tops out at **4.564**. The two pathological pairs
read 14.75 and 50.39. Nothing anywhere in the clean 300 falls between 5 and 14, so any bound in
[6, 12] clips exactly those two and nothing else:

| threshold | clips (of 300 clean) | dev+dev2 | reporting | jitter1.5 | jitter3.0 |
|---|---|---|---|---|---|
| off | 0 | 11 | 6 | 6 | 19 |
| 3 px | 12 | 10 | 5 | 5 | 14 |
| 4 px | 7 | 10 | 5 | 5 | 14 |
| **6 px** | **2** | **10** | **5** | **5** | **14** |
| 8 px | 2 | 10 | 5 | 5 | 15 |
| 12 px | 2 | 10 | 5 | 6 | 15 |
| 20 px | 2 | 10 | 6 | 6 | 17 |

Every threshold from 3 to 12 gives the same reporting result. 6 rather than 8 only because it is
also best-or-tied under jitter stress. Below ~4 the guard starts clipping legitimate corrections and
buys nothing for the precision it costs.

### 44d. What it is worth, and what it is not

Aggregate **6.0% → 5.0%**, bench 16.7% → 13.3%, sponsor and FinFET unchanged. Zero regressions.
Median error and pass@0.5px are **identical** on all three reporting splits, because the guard only
ever touches pairs that were already wrong; pass@1px on bench rises 80.0% → 83.3%.

**One pair on the reporting splits.** The count is not the point — the bucket is. This is the first
failure in the project that was never a selection error, and it stayed invisible precisely because
the instrument had only selection buckets in it. The lesson generalises past this fix: *a
decomposition can only find failures of the kinds it has names for.*

### 44e. Isolated on the stress sweep — and a stale baseline that nearly produced a wrong answer

The guard was re-measured across all 25 robustness operating points with identical generator seeds,
`--no-drift-guard` against the shipped default:

| | 750 stress pairs |
|---|---|
| **ADR-0036 drift guard** | **12 fixed / 0 broken**, improving 10 of 25 points, worsening none |

The largest gains are ±5° rotation (30.0% → 23.3%) and nominal read noise (20.0% → 13.3%) — the
regimes where drift estimation is hardest, which is the direction the mechanism predicts.

**The first version of this comparison said the opposite about three points, and it was wrong.**
`results/robustness.csv` had last been regenerated at commit 68d1ef0 and was never re-run for
ADR-0035, so a diff against it spanned **two** configuration changes. Three stress points had moved
the wrong way and the obvious reading was that the guard rejects legitimate corrections under heavy
noise — a plausible mechanism, a clean-looking table, and false. Isolating the two changes assigns
all three regressions to ADR-0035 and none to the guard.

That produced a second finding nobody had asked for: **ADR-0035 shipped without stress validation**,
and measured now it is 2 fixed / 3 broken over 750 stress pairs, net −1, against +4/−0 on clean data.
It stays — the clean gain is paired and targets a bucket nothing else reaches, and −1 of 750 is
inside this sweep's sampling floor — but "residual proposals cost nothing" was never measured where
it now turns out to be roughly break-even. Recorded as an amendment on ADR-0035.

**The transferable lesson is about the baseline, not the guard.** A stale comparison baseline does
not produce a noisy answer, it produces a *confident wrong* one, because every number in it is
internally consistent — it is consistently describing a build that no longer exists.
`scripts/verify_submission.py` now carries `check_results_newer_than_config`, which compares each
measured artefact's timestamp against the pipeline source. It warns rather than fails, because mtime
is a weak signal, but it would have caught this a day earlier.


## 45. Two parameters re-examined in the pipeline that now exists — one moved, one did not ✅❌

ADR-0034's lesson was that *a parameter measured as flat is flat against the pipeline it was
measured in*. Three stages landed after it, so the two free parameters of the selection path came
due for re-measurement. They were run through `scripts/param_sweep.py`, which was written for this
and kept: three shipped decisions here have been single-parameter changes, each measured with a
script that was then thrown away.

### 45a. Pose-evidence beta — flat across its working basin ❌

The offline sweep over cached pose grids (200 tuning pairs, paired on identical grids) put beta=10
one pair ahead of the shipped beta=5:

| beta | mis-locks / 200 |
|---|---|
| max (beta -> inf) | 21 |
| 100 – 800 | 21 |
| 50 | 19 |
| 25 | 18 |
| **10** | **13** |
| **5 (shipped)** | **14** |
| mean (beta -> 0) | 17 |

One pair in 200 is not evidence, and the proxy is not the pipeline, so it was re-run for real:

| beta | dev | dev2 | total | fixed | broke |
|---|---|---|---|---|---|
| **5 (shipped)** | 2 | 8 | **10** | — | — |
| 10 | 3 | 7 | **10** | 2 | 2 |
| 15 | 3 | 8 | 11 | 2 | 3 |

beta=10 is exactly break-even — it churns two pairs each way and lands on the same total. **No
change.** What the ladder does establish is that the *stage* earns its place: the maximum costs 21
of 200 against the log-sum-exp's 13–14. It is the choice of beta inside the basin that is
unresolvable, not whether to read the grid as evidence.

**And the proxy overstated its own authority.** `pose_evidence.py` caches only `out[:10]` while the
pipeline re-orders every wide-refit survivor, so its absolute rates are systematically pessimistic —
it reported `lse` at 10.0% on sponsor where the pipeline measures 0.0%. Its *relative* comparisons
are sound because every variant scores the identical cached field. The docstring now says so with
that example in it, because "lse 10 -> sponsor 10.0%" sitting in a results file is exactly the kind
of number that ends up on a slide.

### 45b. The screen cut — a third answer from the same knob ✅

| when | pipeline it was measured in | verdict |
|---|---|---|
| FINDINGS §23d | before pose evidence | **flat**, closed |
| ADR-0034 | after pose evidence | 10 -> 30, **+4** |
| **here** | after proposals and the drift guard | 30 -> 40, **+3 / -0** |

40 and 60 measure identically on the tuning family, so it is a plateau, not a spike. Runtime is
**x1.091**, measured by interleaving both arms in one session.

**It changes no reported number** — 0.0% / 13.3% / 3.3% and every median identical to the decimal.
It ships anyway, on 300 pairs with zero regressions and because a 1.5% effect is below what 100
reporting pairs can resolve; the reasoning and the case against are both in ADR-0037.

**The prediction made before running it was wrong, and in the interesting direction.** The screen-rank
distribution showed one truth at rank 31–39 and one at 40–60, so the ceiling looked like two pairs.
It delivered three. Changing the cut does not merely readmit the candidates that sat past it — it
changes which candidates enter the wide refit at all, and therefore the pose refits and the evidence
ranking of the whole field. Second-order effects, not accounted for in the estimate.

Pointing the other way: **`finfet 25` sits at screen rank 31 and a cut of 40 reaches it, and it was
still not recovered.** Reaching the wide refit is not the same as winning it — which is ADR-0034's
own finding, restated from the losing side.

## 41. The RGB optical extension: the pipeline transfers, and the colour is worth measuring ✅

The problem statement lists an "RGB optical-image extension" as a bonus after the grayscale SEM
task. *(A review suggested this was stale because the public hackathon page says the challenge
images are grayscale. Both are true and not in conflict: the graded task is grayscale, and the
Drift-Sense PDF itself lists "RGB optical-image extension | Bonus | Optional generalization after
completing the grayscale SEM task". Primary source wins.)*

### 41a. It is a different problem, not a colourised SEM

| | SEM | optical brightfield |
|---|---|---|
| resolution set by | probe size, ~5 nm | diffraction, `0.61 λ/NA` = **372.8 nm** |
| DRAM word-line pitch, 64 nm | resolved with room to spare | **six times below the limit** |
| contrast from | secondary-electron yield vs. surface tilt | **thin-film interference**, `4πnd/λ` |
| channels | one | three photodiodes, independent noise, wavelength-dependent PSF |

**The cell lattice is not blurry in the optical modality — it is absent.** So `src/synth/optical.py`
images a *coarser layer*, where mats and peripheral strips play the role the cell array plays in
SEM. That is what optical inspection is actually used for, and it preserves the ambiguity the task
is about (a periodic array of near-identical sites) while changing the physics honestly.

Modelled, each because it follows from the optics rather than because it looked good: per-material
reflectance from the film stack per channel; lateral chromatic aberration; a per-channel PSF, so
blue is genuinely sharper than red; Koehler illumination falloff; and per-channel Poisson + read
noise, because the three photodiodes are separate.

### 41b. The pipeline transfers unchanged

`results/optical.csv`, 30 pairs, generator seed 77001. The matcher is untouched — the only thing
that varies between arms is how three channels become the one the matcher consumes.

| arm | mis-lock | median px | p95 px | pass@1px | p50 ms |
|---|---|---|---|---|---|
| **luma** (Rec. 601 — what the CLI does today) | 6.7% | 0.1003 | 11.94 | 93.3% | 514 |
| **pca** (measured contrast projection) | **3.3%** | 0.0929 | **0.51** | **96.7%** | 509 |
| green (sharpest single channel, control) | 6.7% | 0.0871 | 11.89 | 93.3% | 509 |

> **A physics-based matcher built around an electron beam, area-average decimation and
> Poisson-Gaussian noise localizes diffraction-limited RGB brightfield to a median of 0.10 px with
> no code changes at all.** That is the strongest evidence yet that the forward-model framing —
> rather than any particular tuning — is what does the work.

### 41c. Measuring the colour axis beats assuming one

Rec. 601's weights (`0.299 R + 0.587 G + 0.114 B`) describe the human eye. Nothing about a film
stack knows about that, and which channel separates two materials depends on the layer thickness
that happens to be on the wafer. So `src/driftlock/color.py` measures it: the direction in RGB space
along which the **reference's** pixels vary most, applied to *both* images so they stay in one
photometric frame.

* the measured direction sits **25.6°** from luminance (min 24.7, max 26.8 — consistent across pairs)
* mean direction **R +0.787, G +0.610, B +0.082** — a genuine red-green mix, not a channel pick,
  which is what the `green` control was there to rule out
* mis-lock halves, 6.7% → 3.3%, and **p95 error collapses from 11.94 px to 0.51 px**

The mis-lock difference is +1/−0 on 30 pairs (p = 1.000) and is *not* on its own significant. The
p95 collapse is the sturdier number: the luma arm has a pair it locates badly and the measured
projection does not.

**Not enabled by default**, because the graded task is grayscale and the colour path must be a no-op
there — `to_matcher_input` returns single-channel input untouched, and a test asserts it.

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
