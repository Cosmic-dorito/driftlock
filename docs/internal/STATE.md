# STATE — complete snapshot, 16 Aug 2026

**One file, self-contained.** If you read nothing else, read this. It carries the shipped
configuration, every measured number, every closed direction with its evidence, and the reasons the
project stopped where it did. `docs/HANDOFF.md` has the cold-start instructions; `docs/FINDINGS.md`
has the full experiment write-ups this summarises; `docs/DECISIONS.md` has the ADRs.

**Deadline 18 Aug 2026** (moved from the 16th, confirmed by the organiser).

---

## 1. Where the submission stands

**Complete, verified, packaged.** If time ran out now, ship `dist/drift-lock-submission.zip`.

| | |
|---|---|
| `scripts/verify_submission.py --strict` | **20 checks** |
| tests | **65 pass** |
| lint | ruff clean |
| clean extract of `dist/` | reproduces all 15 accuracy metrics **exactly** |
| deck | `solution_presentation.pptx`, 12 slides, every number generated from `results/` |

### Measured results

| Split | mis-lock | median px | pass@1px | pass@0.5px | runtime p50 |
|---|---|---|---|---|---|
| sponsor `verify` (40) | **0.0%** | 0.179 | 97.5% | 92.5% | 632 ms (32.4×) |
| bench (30, ours) | **13.3%** | 0.300 | 83.3% | 66.7% | 568 ms (29.1×) |
| holdout FinFET (30) | **3.3%** | 0.214 | 90.0% | 76.7% | 564 ms (28.9×) |

*Every cell above is `results/metrics_{sponsor,bench,finfet}.csv` and `results/runtime.csv`.
Re-derived independently from `predictions_*.csv` + manifests on 16 Aug: all fifteen accuracy
figures reproduce exactly. **Do not hand-edit this table** — an earlier version carried
pass@0.5px 63.3/73.3 and runtimes 664/590/586 from a superseded benchmark pass.*

**Aggregate 5/100 = 5.0%.** Baselines 25.0 / 76.7 / 90.0%. Four stages, three on 15 Aug (each only
working because of the one before it) and one on 16 Aug:

| change | aggregate | bucket it moved |
|---|---|---|
| pose grid read as evidence (ADR-0032) | 16.0% → 11.0% | outscored 9 → 4 |
| screen widened 10 → 30 (ADR-0034) | 11.0% → 8.0% | screened 4 → 0 |
| lattice residual proposals (ADR-0035) | 8.0% → 6.0% | absent 3 → 1 |
| drift correction bounded (ADR-0036) | 6.0% → **5.0%** | a bucket that did not exist |
| screen cut widened 30 → 40 (ADR-0037) | 5.0% → 5.0% | **nothing reported** — +3/−0 tuning, +5/−2 stress |

**ADR-0036 is a different kind of fix and worth reading as one.** The first three all improve
*candidate selection*. The fourth is the first failure in the project that was **never a selection
error**: on `bench 21` the pipeline chose the true candidate — rank 0, 0.92 px from ground truth —
and the terminal drift correction then moved the answer 7.5 px off it. It stayed invisible for six
days because the failure decomposition had only selection buckets (ABSENT / SCREENED / OUTSCORED) in
it, and *a decomposition can only find failures of the kinds it has names for*. See §44.

The residual proposal runs at **half resolution** (`proposal_level=2`): +0/−0 across all 300 pairs
at **0.79× the full-resolution *residual configuration*** — not 0.79× baseline; the whole system still runs 26–30× the control — because a proposal only has to say "look near here" and the refit
finds the exact location on the intensity image. L4 was also tested and loses 2 pairs — the
aperiodic signal survives one halving, not two.

**Runtime: CERTIFIED on 18 Aug — both gates pass.** `results/runtime.csv` records
`absolute_ms_representative, yes`. Baseline control **18.8 ms** against the 22 ms quiet-machine
reference, dispersion **1.145** against the 1.18 threshold, measured on the shipped configuration.

| split | p50 | p95 | × baseline |
|---|---|---|---|
| sponsor | 672 ms | 716 | 35.8× |
| bench | 604 ms | 669 | 32.1× |
| FinFET | 621 ms | 758 | 33.1× |

**The earlier failures were real, and so was the wrong diagnosis.** Two attempts on 16–17 Aug were
refused by the control gate at 86–88 ms, and the cause was recorded as sustained down-clocking on
the evidence that `Win32_Processor.CurrentClockSpeed` read 1400 MHz against a 3800 MHz maximum. That
reading is worthless: on 18 Aug it still read 1400 MHz **while the CPU was under full load**, so WMI
was reporting a static nominal value and never the live frequency. The genuine signal was always the
benchmark's own control arm, which is why the gate is built on it. The machine was simply hot from
an hour of robustness sweeps; once idle, the same command certified on the first attempt.

*Working rule earned here: when a health gate and a system metric disagree, trust the one that
measures the thing you care about. The control arm runs the same code on the same machine; a
vendor-reported clock is an assertion about hardware that may not even be sampled.*

**The trade, measured:** the 15 Aug morning configuration ran 394/377/382 ms at ~20× baseline at
16.0% mis-lock. The four changes cost **≈×1.5 runtime for 16.0% → 5.0%**. There is no published
runtime limit; the faster narrow-refit configuration remains reachable by config and is in the
ablation. ADR-0036 itself is free — it replaces a correction with a comparison.

Paired against the previous configuration (§40, ADR-0032), stated at both levels because the two
answer different questions:

| | fixed | broke | exact McNemar |
|---|---|---|---|
| **three reporting splits only** (100 pairs, none used for tuning) | **+8** | 3 | **p = 0.227** |
| all five splits (300 pairs, incl. dev + dev2) | +17 | 3 | p = 0.0026 |

**`dev` and `dev2` are the tuning family**, so the pooled p is a statement about reproducibility,
not about independent significance. The independent evidence is the first row: a large, consistent
improvement that does **not** reach p < 0.05 on 100 pairs. Four of five splits improve with zero
breaks; `bench` was the single regression at that step (16.7% → 23.3%) and the two changes after it
took `bench` back to 16.7%. The regression is kept on the record rather than quietly absorbed.

**Bonus modality (§41, ADR-0033).** RGB optical brightfield, 30 pairs: the unchanged pipeline
reaches **6.7% mis-lock and 0.100 px median**, and measuring the colour projection instead of using
luminance takes that to **3.3%** with p95 error 11.94 → **0.51 px**.

### Shipped configuration — `localize.py::build_config`

<!-- BEGIN GENERATED CONFIG -->

*Generated by `scripts/make_results_doc.py` from `localize.py::build_config`. Do not edit by hand — regenerate.*

```python
PipelineConfig(
    median_filter=True,  # ADR-0027
    pose_search=True,
    top_k=10,
    candidate_refit=True,  # ADR-0019
    refit_scale_span=0.03,
    refit_rotation_span=1.5,
    refit_steps=5,
    refit_screen_steps=2,  # ADR-0025
    refit_screen_top_n=40,  # ADR-0037
    pose_evidence_beta=5.0,  # ADR-0032
    proposal_channels='residual',
    proposal_top_k=3,
    proposal_level=2,  # ADR-0035
    subpixel=True,
    drift_correction=True,
    drift_max_shear_px=6.0,  # ADR-0036
    label='driftlock',
)
```

Every field not listed is at its `PipelineConfig` default, which reproduces the sponsor's baseline.

<!-- END GENERATED CONFIG -->

**Newest stage — read the pose grid as evidence, not as its maximum (§40, ADR-0032).** The maximum
over ~25 poses is upward-biased, and the bias grows with how rough that candidate's pose surface is,
so a candidate that peaked once outranks one that was consistently good. Same ZNCC, same grid,
different summary — so it is not a new criterion (ADR-0024) — and it costs no correlations at all.
Paired over **300 pairs across five splits: +17 fixed / −3 broken, exact McNemar p = 0.0026.**

**And then the screen widened, 10 → 30 (§40h–40i, ADR-0034).** §23d had measured this exact knob as
flat and closed it. Instrumenting the screen showed the truth sitting at rank **12, 14, 25 and 29**
on the four screened failures, so a wider cut always did reach them — it never converted, because
the candidates it recovered were handed to the plain maximum. Once the selector changed, the same
knob was worth **+4 fixed / 0 broken over 140 pairs**. *A parameter measured as "flat" is flat
against the pipeline it was measured in.*

Its runtime cost was re-measured on a settled machine and is in `results/runtime.csv`
(632/568/564 ms p50, control 19.5 ms). Only the dispersion gate is marginal — see above.

---

## 2. The two findings that carry the submission

### 2a. The oracle ceiling — the margin is ~0.01, and the truth is tied, not behind (§35a, §37)

> **⚠️ Corrected 15 Aug.** An earlier version of this section claimed the truth correlates **0.065
> worse** than the impostor (2/15, p = 0.007) and that the refit recovers **89%**. That did not
> reproduce: the "winner" figure was the **maximum of the correlation surface**, not the score at
> the location the pipeline chose, and a max over ~810,000 positions beats any nominated point by
> construction. Full retraction and cause in **FINDINGS §37**. The numbers below are the
> reimplementation's, and they are regenerable.

Given the generator's **exact** `scale_ratio` and `rotation_deg`:

| | | |
|---|---|---|
| shipped pipeline correct | **89 / 100** | ⚠️ measured before ADR-0034/0035; the pipeline is now 94/100 |
| oracle pose + plain argmax | **70 / 100** | rescues 3 failures, loses 22 it had |

**Pose estimation error is not what loses these pairs** — a perfect pose is far *worse* than the
shipped pipeline, because it has no refit and no evidence stage. (§35a.)

At that exact pose, on the 10 failures where both windows fit:

| ZNCC at the exact GT pose | mean | truth ahead |
|---|---|---|
| at the **true** location | **0.7181** | — |
| at the location the **pipeline chose** | **0.6759** | **4 / 10**, p = **0.754** |

**At the correct pose the true site and its impostor remain statistically indistinguishable** — the
truth is now nominally *ahead* on the mean, and 4/10 with p = 0.754 says that means nothing either
way. The paired subset (truth present at the final comparison) is down to **3 pairs** since
ADR-0032, so the "fraction of the deficit the refit closes" is no longer estimable and the script
now reports it as such rather than dividing by a near-zero denominator.

> The headline is not "6% mis-lock remains". It is: **at the correct pose the true site and its
> impostor are separated by about 0.01 of correlation or less — the level at which sampling noise
> and model mismatch live. Six re-ranking criteria failed to resolve it; reading the pose surface as
> evidence rather than as a maximum resolved part of it (§40).**

Regenerate: `python scripts/pose_ceiling.py` → `results/pose_ceiling.csv`.

*Two caveats kept deliberately:* correlation sampling noise on these patches is a **scale, not a
calibrated floor** — SEM pixels are blurred, periodic and interpolated, so the effective sample size
is far below the pixel count. And this measures **rules reading the fixed-pose correlation**, not
every conceivable method.

**Do not say** these were "never selection errors", or that "no re-ranker could ever reach them", or
that geometry recovers 89% of anything. Those followed from the retracted figure. What the evidence
supports is that the available margin is ~0.01, and that six criteria aimed at it all failed.

### 2b. Extra forward-model freedom buys almost nothing (§36, §37a)

> **⚠️ Corrected 15 Aug.** The earlier claim — "every degree of freedom helps the wrong candidate,
> **monotonically**" — rested on §36c, whose sign **reverses** under an independent implementation.
> §36a and §36b reproduce (§36b exactly). The monotone claim is withdrawn.

Three degrees of freedom added to the forward model as *oracles* — never pipeline stages — measured
as *differential* gain (truth minus winner) on the 8 paired failures. A gain that lifts both
candidates equally changes no decision and is worth nothing.

| added freedom | truth | winner | **differential** | truth better in | status |
|---|---|---|---|---|---|
| PSF blur | +0.0003 | +0.0002 | **+0.0000** | 7/8 (p = 0.070) | reproduces in sign |
| anisotropic scale + shear | +0.0010 | +0.0014 | **−0.0004** | 4/8 (p = 1.000) | ✅ reproduces exactly |
| line-jitter, quadratic in y | −0.0276 | −0.0654 | **+0.0378** | 7/8 (p = 0.070) | ❌ sign reversed vs §36c |

What survives: **PSF blur is real and negligible** (consistent 7/8, differential at the fourth
decimal), and **spatial micro-deformation helps the impostor more** (−0.0004, exactly reproduced).
Neither justifies a richer forward model.

**That lead is now closed (§38).** The line-jitter differential of +0.0378 was never physics. Built
properly — measured once from the whole search image, before any candidate exists, so the same
correction applies to every candidate — the differential is **−0.0003** (truth +0.0297, impostor
+0.0301, truth ahead in 8/27). Both earlier implementations were measuring how much *unfairness*
their particular estimator handed each candidate, which is why they disagreed about the sign.

The shipped `rigid pose + bounded refit` remains the measured optimum among everything actually
tried; that rests on the ablation, which is unaffected.

---

## 3. Failure decomposition — where the remaining 16 live

`results/failure_decomposition.csv`, 100 pairs:

| stage that lost it | **now** | start of 15 Aug | after §40 | after §40i | after §42 | after §44 |
|---|---|---|---|---|---|---|
| never a candidate | **1** | 3 | 3 | 3 | 1 | 1 |
| cut by the screen | **0** | 4 | 4 | 0 | 1 | 1 |
| outscored at the final comparison | **4** | 9 | 4 | 5 | 4 | 3 |
| *selected correctly, then moved off* | **0** | — | — | — | 1 | 0 |

**5 failures total: 1 absent, 0 screened, 4 outscored.** The only named one left is `bench 17`
(absent, a pose-search interaction). The fourth row did not exist as a category until §44;
`bench 21` occupied it and ADR-0036 emptied it.

**`finfet 25` moved from `screened` to `outscored` and that is the clearest thing ADR-0037 did.**
It sat at screen rank 31 against a cut of 30. Widening to 40 admitted it — the screen stopped being
what lost it — and it then lost at the final comparison anyway. The bucket moved; the pair did not.
*Reaching the wide refit is not the same as winning it.*

**The three `outscored` failures lose on evidence, not on correlation.** With the forensics
corrected (§44a), the ZNCC margin is **negative** on all three — the truth correlates *better* and
still loses, because since ADR-0032 the pipeline does not rank on correlation:

| pair | ZNCC margin | evidence margin | truth rank |
|---|---|---|---|
| `bench 3` | −0.0018 | +0.0014 | 2 |
| `bench 13` | −0.0312 | +0.0105 | 3 |
| `bench 19` | −0.0060 | +0.0003 | 1 |

That is ADR-0032 working as designed — it buys 5 pairs and costs these three — but it had never been
visible, because the mechanism file was comparing the truth against itself (§44a).

**Each stage moved exactly the bucket it addresses.** Pose evidence cut *outscored* 9 → 4; widening
the screen emptied *screened* 4 → 0; residual proposals took *absent* 3 → 1.

**And the last one has an honest side effect.** `finfet 25` was outscored at screen rank 29; the
extra proposals inflate the pool and push it to rank 32, past the top-30 cut, so it is `screened`
again. A wider pool has more competition in it. Net −2 failures, not a free win.

The one remaining `absent` is **bench 17**, which is partly a *pose* failure: plain intensity ranks
it 13th at the oracle pose, so the information is in the channel the pipeline already uses and the
pipeline never looks there. No proposal channel fixes that (§42).

**The true candidate is never the runner-up.** Across 15 instrumented held-out failures: rank ≤2 in
**0**, rank ≤3 in 1, rank ≤5 in 4, absent from the top 20 in **7**. Any idea of the form "break the
tie between the top two" is dead on arrival — the tied set is populated by *other impostors*.

Under **charging streaks** the mode inverts: 23.3% ABSENT vs 3.3% OUTSCORED. `top_k` at 10/20/30 is
flat at 33.3%, so the peak is **erased, not demoted**.

---

## 4. Robustness envelope

`results/robustness.csv`, 25 operating points, validation-only seeds (90,000,000+), disjoint from
every reporting and tuning split.

*Regenerated 16 Aug for ADR-0035 + ADR-0036 + ADR-0037. It had been stale since 68d1ef0 — it survived the
ADR-0035 config change untouched and four documents quoted it. Every figure below is
`results/robustness.csv`; do not hand-edit them.*

| axis | in-spec | beyond spec |
|---|---|---|
| dose (32× range) | 0.0–13.3% | 6.7–13.3% at 2–8× noisier |
| read noise σ | 13.3% at nominal | 3.3% at 2×, 6.7% at 4× |
| **scale** | 16.7% at 9–11:1, 10.0% at fixed 10:1 | **33.3%** at 8–12:1 |
| rotation | **3.3%** at ±2°, **0.0%** at ±1°, 10.0% at 0° | 10.0% at ±3°, **20.0%** at ±5° |
| charging streaks | — | **30.0%** ← named by the spec |
| barrel distortion | — | **33.3%** ← *not* named by the spec |
| salt-and-pepper + speckle | — | 6.7% (with the median filter) |
| beam spot 12 nm | — | 10.0% |
| gamma + vignette | — | 3.3% |
| mixed (spec + 4× noise) | — | 13.3% |
| mixed (everything, beyond spec) | — | **40.0%** |
| **scan jitter** | 12.5% at σ = 0.5 | **25.0%** at σ = 1.5, **63.3%** at σ = 3.0 (§38e) |

⚠️ **The scan-jitter row predates ADR-0036 and is the one figure here not regenerated**, because it
comes from a separate experiment (`results/global_jitter_*.csv`), not from the sweep. §44c measures
the same regime under the guard and puts jitter σ=3.0 at 14 of 30 rather than 19, so 63.3% is
an upper bound on the current pipeline, not its measured value. Re-run
`scripts/global_jitter.py` before quoting it.

**Scan jitter is the most damaging degradation found so far**, and it was only measured because the
scan-field experiment needed a regime to be tested in (`results/global_jitter_edge.csv` and
`results/global_jitter_stress.csv`, validation seeds 91,000,001–2). At the nominal 0.5 px it is
invisible; by 3.0 px it took mis-lock to 63.3% on the pre-guard pipeline — worse than barrel
distortion (33.3%) or charging streaks (30.0%). It is 6× beyond anything the spec names, so this is
an envelope boundary rather than a shipping risk, but no other single axis comes close.

Degradations **compose roughly additively**; no new failure mode emerges. Target position: no
dependence detectable in this 100-pair sample (`results/position_strata.csv`, all Wilson intervals
overlap, patterns non-monotone).

---

## 5. Everything closed, with its number

**Do not retry any of these.** Each has a measurement or a mechanism.

### Selection / scoring
| direction | result |
|---|---|
| **pose grid read as evidence, not as its maximum** | ✅ **SHIPPED** — +8/−3 on the reporting splits (p = 0.227), +17/−3 pooled over 300 (§40, ADR-0032) |
| pose-surface *shape*: entropy, effective-trials extreme value, peakiness, top-3 | all **worse** than the shipped LSE, 15–18% against 10.0% (§40g) |
| **screen cut `top_n` 10 → 30** | ✅ **SHIPPED** — +4/−0 over 140 pairs at ×1.05 runtime; only pays off because of ADR-0032 (§40h–40i, ADR-0034) |
| **screen cut `top_n` 30 → 40** | ✅ **SHIPPED** — +3/−0 on 200 tuning pairs, +0/−0 on the 100 reported, **+5/−2 on 750 stress pairs** — and split by envelope that is **3 fixed / 0 broken INSIDE the spec range, 2/2 beyond it**. ×1.091 runtime. **Changes no reported number.** 60 measures identically, so it is a plateau (§45b, ADR-0037) |
| pose-evidence `beta` 5 → 10 or 15 | ❌ **flat** — beta=10 is +2/−2 on 200 tuning pairs, same total; 15 is worse. The offline proxy preferred 10 by one pair and did not survive the real pipeline (§45a) |
| six re-ranking criteria (PADM, coarse consensus, max-likelihood, refit-gain, lattice-phase, residual tie-break) | all failed — ADR-0024 |
| centre tie-break as default | ADR-0021 |
| centre tie-break **gated to statistical ties**, all thresholds | **0 fixes**, up to 57 breaks (§30) |
| multiplicity as a blended score | dev-selected gain vanishes on a 151-group set (§32a) |
| multiplicity as a **filter** | every threshold worse than none, both sets (§33) |
| learned verifier | closed by the above — same signal, more free parameters, flat criterion |

### Candidate generation
| direction | result |
|---|---|
| `top_k` ∈ {5,10,15,20,30} | flat (§23g) |
| `top_n` ∈ {6,10,15,20} | flat (§23d) |
| cross-pose dedup | 3.8/10 slots *are* duplicates; removing them changes nothing (§31b) |
| multi-cell context | **arithmetically impossible** — reference is 1000 nm total, already spans ~163 cells (§31a) |

### Residual / structure
| direction | result |
|---|---|
| PADM (Fourier mask), consensus residual, gated residual tie-break | all failed |
| PCAF (spatial cell-folding) | **26 broken to fix 1** (§33) |
| cellwise consistency at fixed pose | truth wins 6/18 and 7/18 — below chance (§34a) |
| leave-cell-out generalisation | **impostor generalises better**, truth 5/18 (§34b) |

### Forward model
| direction | result |
|---|---|
| PSF blur | differential at the fourth decimal, 7/8 (§36a) |
| micro-warp | −0.0004, 4/8 — the impostor gains more (§36b, reproduced exactly) |
| candidate-local line-jitter | superseded: both implementations were measuring their own unfairness, not physics (§38b) |
| **global scan-field calibration** | lifts the truth **+0.0297** and the impostor **+0.0301** — differential **−0.0003**, 8/27. dev mis-lock 12.5% → 15.0%, +101 ms. Declines every pair at σ = 1.5 and σ = 3.0, so it has **no operating regime** (§38) |
| supercell / higher-order periodicity | order 2 only — the checkerboard parity, which is **blind to the parity-preserving diagonal shift** that causes our failures (§39) |

### Generator distribution (§43)
| finding | evidence |
|---|---|
| **H11 — the sponsor's fields are pitch-heterogeneous; ours are near-uniform** | per-3×3-block dominant period spread **16.6 px** on their data vs **0.1 px** on ours; their `presets.py` spans 48–240 nm bit-line pitch |

On a multi-pitch field most mats are trivially wrong (a 9.6 px lattice cannot be confused with a
23.8 px one), so the impostor population collapses to mats sharing the reference's preset. On our
uniform field **every mat is live**. Stated at that strength only: this establishes *heterogeneity
vs uniformity*, **not** one-preset-per-mat, and **not** that our benchmark is "harder" — only that a
mechanism exists which removes a cheap rejection cue.

**Deliberately not "fixed".** Adding heterogeneous pitch would make our numbers look better while
testing less. A sponsor-like second family is worth adding as *validation*, never as a replacement.

**Consequence for the roadmap:** a regional-pitch candidate prior — the obvious idea from these
images — **cannot help our remaining failures**, because bench pitch spread is 0.1 px and every
impostor already matches the truth's pitch by construction. It is a *runtime* idea for
heterogeneous data, not an accuracy idea for the 6 failures.

### Candidate generation, second round
| direction | result |
|---|---|
| **lattice residual as a PROPOSAL channel** | ✅ **SHIPPED** — +4/−0 over 300 pairs, absent 3 → 1 (§42, ADR-0035) |
| variance / edge proposal channels | change **zero** pairs and cost runtime — measured negatives in the ablation (§42c) |
| half-resolution proposals | ✅ shipped — +0/−0 at 0.79× the *full-resolution residual config*; quarter resolution loses 2 pairs (§42) |
| auxiliary-quota screen (protect intensity candidates) | +1/−1, net zero — the mechanism is real, the trade is not (§42f) |
| oracle-pose forensics as a *design* tool | ❌ does not predict which channel ships; it is a screening tool only (§42d) |

### Other
| direction | result |
|---|---|
| batching correlations (tiled matchTemplate) | **53% slower** — arithmetic-bound, not overhead-bound (§29) |
| row destriping | 20.0% → 36.7% on clean data |
| destreak (artifact-aware) | breaks 1, fixes 0, +56 ms (§26b) |
| multi-basin refinement, pose interpolation, pose-regime routing, pose-excursion penalty | §21–22, ADR-0024 |
| **GPU / H100** | belongs to the **KLA track**, not Drift-Sense — verified in both primary sources (§18c) |

---

## 6. The unifying explanation

> **Any evidence strong enough to be reliable is shared by the impostor (it is periodic), and any
> evidence that distinguishes them is too weak to be reliable (it is the aperiodic fingerprint).**

Every negative is one horn:
- *shared by the impostor* — six re-rankers, centre tie-break, basin coherence, LCLOV
- *too faint at dose 200* — PADM, consensus residual, residual tie-break, PCAF

A periodic impostor is **not** a bad fit that got lucky. On a lattice that genuinely repeats it is a
correct geometric explanation of the entire footprint. Internal consistency cannot separate them
because *both are consistent*.

**Which is why "same criterion, better geometry" (ADR-0024) is the only stage that ever worked** —
the pipeline does not try to tell candidates apart. It reduces geometric mismatch so the small real
margin (H7 ≈ 0.057) is not swamped, then reads an ordinary correlation.

---

## 7. What is genuinely left

### ⚠️ Retracted: the "one live hypothesis" was already closed

An earlier version of this section proposed **multi-scale context for the `outscored` failures** —
comparing truth against impostor over a 20–40 px surrounding ring — and called it the one direction
with a live hypothesis. **It is not well-posed, and §31a had already closed it by arithmetic.**

The reference is 1000×1000 px at 1 nm/px: **1000 nm across, which is the whole of it.** At 10 nm/px
that is exactly the 100×100 footprint, so there is *no reference content outside the footprint* to
build a context window from. Widening the search window is free but there would be nothing to
correlate it against. Worse for the idea, the reference already spans ≈163 lattice cells, so a
100×100 ZNCC **is** multi-cell contextual verification — "add context" describes what the matcher
does today.

Listing it as live in §7 while §5 recorded it as closed was a contradiction inside this file. Kept
here rather than deleted, because the failure mode — a closed direction reappearing as a fresh idea
one section later — is the one this document exists to prevent.

Also still **not** worth building (§43): a regional-pitch candidate prior. It cannot reach these
failures, because our fields are uniform-pitch by construction and every impostor already matches
the truth's pitch. It is a *runtime* idea for heterogeneous data only.

### What is actually left

Nothing with a live accuracy hypothesis. The three remaining `outscored` failures lose on pose
evidence while winning on correlation (§3), which is the designed trade of ADR-0032 and not a defect
to fix; the oracle-pose measurement (§2a) says the available margin there is ~0.01 and six criteria
aimed at it have failed.

### Everything else

1. **Runtime dispersion gate** — 1.19 against a 1.18 threshold on a healthy machine. Either
   re-measure on a quieter box or re-derive the threshold from several sessions. **Do not widen it
   to make a number pass.**
2. **RGB optical extension** — shipped as a bonus (§41, ADR-0033), not polished.
3. **Determinism test** (PROGRESS 3.8) — still outstanding.
4. **Deck and demo polish** — where the remaining marks are.

Open user actions: no GitHub remote configured; git identity is repo-local "DriftLock Team".

---

## 8. Working rules learned the hard way

1. **Validate on every split** — reversed a conclusion twice (ADR-0012, ADR-0021).
2. **Do not re-rank by a new criterion** — six failures (ADR-0024).
3. **Evaluate a stage in the regime it targets** — the median filter sat off for three days on a "no
   effect" measured where there was no impulse noise (ADR-0027).
4. **Ground truth must pass through every geometric stage** — barrel was applied after the coordinate
   was frozen; the sweep read it as a 53.3% localizer failure (ADR-0028).
5. **Quote paired comparisons and the sample size** — two identically-parameterised splits measured
   20.0% and 26.7% (ADR-0029).
6. **Check code-review claims against the code.** The double-scaling challenge to §36b was refuted by
   one comparison: `integrate_reference` returns 1000×1000 and the warp reproduces `build_template`
   at max|diff| = 0.000000.
7. **Derive, never duplicate.** Five stale-constant defects: deck, README, ablation DEFAULT row,
   `failure_mechanism.csv` fixed filename, stress-cache accepting empty manifests.
8. **A result with no script is not a result.** §35's headline went from a scratchpad print straight
   into four documents, was never in `results/`, and did not survive reimplementation — the "winner"
   was a surface **maximum**, not a score at a location (§37). R2 and R8 would each have caught it;
   neither reaches a number that never entered `results/` and never reached a slide.
9. **Never compare a nominated value against a maximum.** A max over ~810,000 positions is selected
   *because* it is largest, so the comparison cannot come out any other way. Both sides of a paired
   comparison must be nominated the same way.
10. **A statistic is only comparable over the same support.** The pose-evidence stage first made
    things *worse* — 14.4 px to 57.6 px — because `refit_candidates` merges the screened-out
    candidates back in with grids from the **2×2 narrow screen** rather than the 5×5 wide pass. A
    narrow grid is flat and high by construction, so its log-sum-exp sits near its maximum while a
    wide grid averages in poses that are genuinely wrong. Ranking them together promotes exactly the
    candidates the screen rejected (§40d).
11. **A decomposition can only find failures of the kinds it has names for.** ABSENT / SCREENED /
    OUTSCORED are three ways of choosing the wrong candidate, so for six days a pair that chose the
    *right* candidate and was then moved off it by the terminal drift correction had nowhere to go
    and was silently filed as `outscored`. Adding one column — how far the answer moved after
    selection — found it immediately (§44, ADR-0036).
12. **When a stage changes what the pipeline decides, every instrument that reads a decision goes
    stale.** ADR-0032 re-orders candidates *after* the refit returns. `pose_ceiling.py` was fixed
    for that; `failure_decomposition.py` was not, so its mechanism file compared the truth against
    itself and printed a score margin of exactly 0.0 on every row for a day (§44a). A forensics
    output that cannot come out any other way is a bug, not a finding — treat an impossibly clean
    number as a defect report.
13. **An offline proxy and the pipeline can disagree for reasons that exist only in the pipeline.**
    The cached-grid sweep was unaffected by the bug above, because it keeps only the top 10 and
    those were all survivors. A proxy result is a reason to run the real thing, never a substitute.

---

## 9. Regenerating everything

```bash
python localize.py --manifest <split>/manifest.csv --out results/predictions_<name>.csv
python evaluate.py --manifest <split>/manifest.csv --predictions results/predictions_<name>.csv --out results/ --label <name>
python scripts/benchmark_runtime.py        # re-run and take the STEADY-STATE pass, not the first
python scripts/robustness_sweep.py
python scripts/position_strata.py
python scripts/failure_decomposition.py
python scripts/significance.py --baseline-predictions "sponsor=...,bench=...,finfet=..."
python scripts/oracle_ceiling.py       # 35a only
python scripts/pose_ceiling.py         # 35a + the corrected 35b/35c + 36 -> results/pose_ceiling.csv
python scripts/run_ablation.py --manifest sponsor=... --manifest bench=... --manifest finfet=...
python scripts/failure_analysis.py && python scripts/make_failure_case.py --manifest data/bench/manifest.csv
python scripts/make_results_doc.py && python scripts/make_deck.py
python scripts/verify_submission.py --strict && python scripts/package_submission.py
```

**Runtime caveat:** the benchmark self-heats. The first heavy run after idle reads ~1.6× slow *with a
clean baseline control* — the control is 19 ms and completes inside the CPU's boost window while a
400 ms call does not. Both gates (control level and p95/p50 dispersion) must pass.
