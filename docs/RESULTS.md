# RESULTS — all measurements

Every number produced so far, with the exact conditions that produced it. Generated numbers live in
`results/`; this file is the human-readable record of what they mean. Nothing here was typed by
hand from memory (rule R2).

**Last updated:** 12 Aug 2026 · **Deadline:** 16 Aug 2026

---

## 1. Test conditions

| Field | Value |
|---|---|
| Dataset | 40 pairs from the sponsor's published generator, `dram_1x`, seed 20260811 |
| Image sizes | reference 1000×1000 @ 1 nm/px · search 1000×1000 @ 10 nm/px |
| Reference footprint in search | exactly 100×100 px (verified, H1) |
| Ground truth | `(x0/10 + 50, y0/10 + 50)`, on a 0.1 px grid (verified, H2) |
| Hardware | Windows 11, x86-64 |
| Python / OpenCV | 3.14.3 / 5.0.0.93 |
| Timing method | `time.perf_counter()` around load + localize, per pair |
| Threads | single-threaded |

**Why this dataset.** It is the sponsor's own generator — the closest available proxy for the
evaluation data, and an *independent* one, since we did not write it. Cross-validating on a
generator we did not author is the only honest evidence that results are not an artefact of our own
data distribution.

**Known gap.** This generator produces **no rotation and no scale variation** (verified, H9), while
the spec says 9:1–11:1 and 1–2° will be tested. Those axes are therefore **untested** — which is the
main reason our own generator is required.

---

## 2. Headline result — validated on held-out data

Configuration: sub-pixel DFT + blind drift correction. No GPU, no learned weights, four
dependencies, ~50 ms per pair.

**Every number below is reported on three splits, only one of which was used for tuning.**

| Split | | Mis-lock | Median (px) | pass@1px | pass@0.5px | Runtime p50 |
|---|---|---|---|---|---|---|
| **verify** (tuned) | baseline | 25.0% | 1.102 | 40% | 18% | 29.9 ms |
| | **DriftLock** | 25.0% | **0.238** | **75%** | **72%** | 50.5 ms |
| **held-out dram seed** | baseline | 20.0% | 0.757* | 50% | 23% | — |
| | **DriftLock** | 20.0% | **0.301** | **80%** | **67%** | 47.8 ms |
| **held-out FinFET** | baseline | 30.0% | 0.943* | 43% | 13% | — |
| | **DriftLock** | 30.0% | **0.422** | **70%** | **60%** | 48.1 ms |

\* median among correctly-located pairs.

**What generalises and what does not.** Precision improves by a similar factor on all three splits,
including an architecture (FinFET) the pipeline was never tuned on. Sub-pixel pass rate roughly
**triples to quadruples** everywhere: 18%→72%, 23%→67%, 13%→60%.

**The mis-lock rate is unchanged from baseline on every split — deliberately.** Neither enabled
stage touches candidate selection; both are pure refinement applied after a location is chosen.
That makes them *strictly additive*: they cannot turn a correct pick into a wrong one, which is why
they transfer across architectures without retuning.

**The honest reading.** We have solved precision and **not** solved selection. Every pass rate is
capped by the mis-lock rate (25% / 20% / 30%), and that number is currently no better than the
sponsor's baseline. That is the whole of the remaining work on the localization score.

---

## 2b. Generalisation test — PADM removed ⚠️

**The most important negative result in the project**, and the reason the headline above looks
different from earlier drafts.

All parameters (PADM weight and bandwidth, drift gap) were tuned on one split: `dram_1x`, seed
20260811. Rule R5 requires checking that tuning transfers. It did not.

| Configuration | verify (tuned) | held-out dram | held-out FinFET |
|---|---|---|---|
| baseline mis-lock | 25.0% | 20.0% | 30.0% |
| **+ top-K + PADM + centre rule** | **20.0%** ✅ | **26.7%** ❌ | **43.3%** ❌ |
| + sub-pixel + drift | 25.0% | 20.0% | 30.0% |

PADM improved the split it was tuned on by 5 points and made **both** held-out splits worse — by 6.7
points on dram and **13.3 points** on FinFET. Its blend weight and spectral bandwidth were fitted to
one lattice geometry and did not survive a change of pitch or architecture.

**It has been disabled by default.** It remains in the codebase and in the ablation table as a
measured negative result rather than being deleted.

**Two things this cost, and one it saved.** The earlier headline of "20% mis-lock" was an
overfitting artefact and has been withdrawn. But removing PADM also removed its 185 ms of FFT work,
so runtime dropped from 224 ms to **50 ms** — a 4.5× speedup that directly helps the runtime half of
the localization score.

**Why it was caught.** Only because held-out splits were generated and tested before the result was
believed. A single-split evaluation would have reported 20% mis-lock and 78% sub-pixel, and the
evaluation set would have quietly disagreed.

---

## 2c. A property of the sponsor's generator worth knowing

While building the held-out splits, `dram_dense`, `dram_loose` and `dram_legacy` produced
**byte-identical images** (verified by md5).

Cause: `generate_fine_canvas_zoned` passes only `preset["kind"]` to `generate_zone_canvas`, so in
the zoned code path — which is the default — **every DRAM preset collapses to the same generator**,
and the pitch values in `presets.py` are ignored. Only `dram` vs `finfet` actually changes anything.

**Consequence for us:** the sponsor's generator offers far less diversity than its twelve preset
names suggest. Genuine variation in pitch, feature size and CD must come from **our own generator**,
which raises the value of P0 further.

---

## 3. Ablation — what each stage bought

Cumulative, 40 pairs. Each row enables one more stage than the row above.

| # | Stage | Mis-lock | Median (px) | pass@1px | pass@0.5px | Runtime (ms) |
|---|---|---|---|---|---|---|
| 1 | Sponsor baseline (INTER_AREA + ZNCC argmax) | 25.0% | 1.102 | 40% | 18% | 30 |
| 2 | + top-K = 20 candidates (A6) | 25.0% | 1.102 | 40% | 18% | 33 |
| 3 | + PADM residual re-scoring (A7) | **20.0%** | 0.975 | 52% | 20% | 218 |
| 4 | + closest-to-centre rule (A8) | 20.0% | 0.975 | 52% | 20% | 218 |
| 5 | + sub-pixel DFT (A9) | 20.0% | 0.975 | 52% | 20% | 219 |
| 6 | **+ blind drift correction** | 20.0% | **0.220** | **80%** | **78%** | 224 |

Two stages carry essentially all of the gain: **PADM** for the mis-lock rate, and **drift
correction** for precision. They fix different failure modes, which is why both are needed and why a
single headline metric would misrepresent either.

Top-K alone changes nothing — correctly. Keeping 20 candidates and then selecting by maximum score
returns exactly what the argmax returns. Its value is that it *preserves the correct answer* for a
later stage to recover; PADM is what does the recovering.

---

## 4. Stages that did NOT earn their place

Reported per rule R9. Each was implemented, measured, and left off by default.

| Stage | Measured effect | Why |
|---|---|---|
| Row destriping | mis-lock 18.8% → **31.2%** | Removes row-constant content to kill charging streaks, but DRAM word lines are **horizontal** — it deletes real signal. Streaks are also disabled in this data. |
| Median filter | no measurable change | `salt_pepper_prob=0` here; nothing to remove. Retained for robustness when impulse noise is present. |
| Generalized Anscombe (A1) | no change to the argmax | A monotone transform rescales scores without moving an integer peak. Untested rather than refuted — needs re-measuring at genuinely low dose. |
| Phase congruency (A2) | **100% mis-lock**, 324 px median | Implementation is broken. Reported as broken, *not* as "evaluated and rejected" — different claims. |
| ECC affine | no change, ever | `findTransformECC` fails and hits the fallback on every pair. Standalone it reaches 0.037 px, so the invocation is wrong, not the method. |

---

## 5. Blind drift estimation — validation

The single largest improvement. Validated against data generated at **known** shear values
(`--shear-amplitude-px`), 10 pairs each, gap = 100 rows.

| True shear (px) | Estimated | Std dev | Bias |
|---|---|---|---|
| 0.0 | 0.009 | 0.202 | +0.009 |
| 1.5 | 1.445 | 0.344 | −0.055 |
| 3.0 | 2.804 | 0.321 | −0.196 |
| 5.0 | 5.184 | 0.245 | +0.184 |

Essentially unbiased across the range, with scatter well below the ~0.84 px bias being removed.

**Gap sensitivity** (mean estimate at true shear = 1.5):

| Gap (rows) | Estimate | Std dev |
|---|---|---|
| 25 | 1.240 | 0.703 |
| 50 | 1.537 | 0.401 |
| **100** | **1.445** | **0.344** |

Larger gaps give a bigger drift signal relative to per-row measurement noise. Gap must stay well
inside one mat (~260 search px), so 100 is near the useful maximum.

**Against the oracle.** Correcting with the *true* shear from the manifest gives 0.062 px median
among located pairs; the blind estimate achieves **0.143 px**. So the estimator captures most of the
theoretically available correction, and the residual gap is the price of estimating rather than
knowing.

**Two failed approaches, kept because the failures are informative:**

| Approach | Result | Cause |
|---|---|---|
| Correlating distant horizontal bands | shifts of 291, 431 px — nonsense | Lattice periodicity aliased the correlation onto the wrong repeat |
| Same, lag constrained to ±4 px | estimates uncorrelated with truth (−0.90, −1.12, +0.26, −2.26 for true 0.0, 1.5, 3.0, 5.0) | The canvas is zoned in **both** directions with independently randomised mats, so distant bands are *different patterns*, not the same pattern displaced |
| **Adjacent rows, integrated** | tracked truth but ±0.7–1.7 scatter | Summing noisy per-row differentials random-walks: √1000 × 0.05 ≈ 1.6 px accumulated noise against a 1.5 px signal |
| **Rows at a fixed gap, fitted directly** ✅ | see table above | Same content, no integration, no random walk |

---

## 6. The binding constraint — candidate ranking

Every pass rate sits at 80% because of the 20% mis-lock rate. This measurement says whether that is
fixable and by how much.

**Question:** when the pipeline mis-locks, is the true location in the candidate set at all?

| K | Truth present in top-K | Median rank of truth |
|---|---|---|
| 1 | 75.0% | 1 |
| 5 | 87.5% | 1 |
| **20** | **92.5%** | 1 |
| 50 | 92.5% | 1 |
| **100** | **97.5%** | 1 |

**Candidate generation is not the bottleneck — ranking is.** A perfect re-ranker at K=20 would give
**7.5% mis-lock**; at K=100, **2.5%**. We currently achieve 20%.

That is the largest single improvement still available, and it would lift every pass rate from 80%
to roughly 92%.

**PADM parameter sweep** (mis-lock %, 40 pairs; baseline argmax = 25.0%):

| weight ↓ / bandwidth → | 0.002 | 0.004 | 0.006 | 0.010 | 0.020 |
|---|---|---|---|---|---|
| 0.2 | 27.5% | 27.5% | 25.0% | 22.5% | 25.0% |
| **0.4** | 32.5% | 32.5% | 25.0% | **20.0%** | 22.5% |
| 0.6 | 37.5% | 32.5% | 27.5% | 20.0% | 22.5% |
| 0.8 | 40.0% | 37.5% | 30.0% | 30.0% | 22.5% |
| 1.0 | 42.5% | 42.5% | 30.0% | 32.5% | 20.0% |

Narrow bandwidths are *worse than doing nothing*: the random-walk line placement broadens the true
spectral peaks, so a narrow mask leaves lattice energy in the "residual" — carrying exactly the
periodic signal PADM exists to remove. Raising K does not help either (22.5–30% at K=50/100): more
candidates simply add distractors PADM cannot discriminate.

**Conclusion.** Hand-designed residual scoring has plateaued at roughly a fifth of the available
gain. The gap between 20% achieved and 7.5% attainable is the quantitative case for a **learned
re-ranker**: the correct answer is in the set, the negatives are exactly definable
(lattice-equivalent positions), and the deterministic approach has demonstrably stalled.

---

## 7. Verified properties of the evaluation data

Full evidence in `results/hypotheses.md`; the load-bearing ones:

| ID | Property | Evidence |
|---|---|---|
| H1 | Reference footprint is exactly 100×100 px | `gt_box` 100×100 on every pair |
| H2 | GT on a 0.1 px grid; centre = origin + size/2 | Exact on all 40 pairs |
| H3 | Noise is Poisson then Gaussian | `Var = 1.75·mean + 426` over flat windows |
| H4a | `INTER_AREA` is the correct forward operator | ZNCC at truth: mean 0.835, min 0.580 |
| H4b | Plain argmax is defeated by periodicity | 10/40 mis-locate; worst 271.7 px |
| H7 | Aperiodic fingerprint exists | Impostor margin median 0.057, **min 0.0086** — strictly positive, so disambiguation is possible |
| H8 | A mis-lock is a hard failure | Rivals always >5 px away (median 45.5) but only 0.016 lower in score |
| H10 | Raster shear causes a systematic x bias | dx mean −0.837 vs dy +0.073; dx vs gt_y **r = −0.861** |

H7 and H8 together define the difficulty precisely: the discriminating signal exists but is **~4×
smaller than the score noise**. That is why ranking, not generation, is the bottleneck.

---

## 8. Runtime

| Stage | Median (ms) | Cumulative |
|---|---|---|
| Baseline correlation | 30 | 30 |
| + PADM (FFT decomposition) | +185 | 218 |
| + sub-pixel DFT | +1 | 219 |
| + drift estimation | +5 | 224 |

224 ms p50, 235 ms p95, single-threaded CPU, no GPU. Inside the 300 ms target but with a much
thinner margin than the baseline. PADM's FFTs dominate and are the obvious optimisation target if
runtime becomes binding.

---

## 9. Known gaps and untested axes

Stated plainly rather than discovered by a judge:

1. **Rotation and scale are untested.** The sponsor's generator produces neither (H9), yet the spec
   says 9:1–11:1 and 1–2° will be tested. **This is the single biggest risk to the localization
   score** and it is why our own generator is required.
2. **Worst-case error got worse** (271.71 → 629.59 px). When PADM re-ranks incorrectly it can
   promote a *more distant* candidate, so failures became rarer but more severe.
3. **20% mis-lock caps every pass rate at 80%.** Fixable to ~7.5% per §6, but not yet fixed.
4. **Only DRAM tested.** FinFET is supported by the sponsor's generator but not yet evaluated.
5. **One architecture preset, one noise setting.** No stratified results across dose, gamma,
   vignetting, speckle or salt-and-pepper — the sponsor's defaults leave most of those at zero.
6. **Phase congruency and ECC affine are broken**, not evaluated. Their rows in §4 report
   implementation failure, not a judgement about the methods.
