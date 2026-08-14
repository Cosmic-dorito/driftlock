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

## 29. Batching the correlations — refuted by microbenchmark ❌

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
