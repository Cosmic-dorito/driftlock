# STATE — complete snapshot, 15 Aug 2026

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
| `scripts/verify_submission.py --strict` | **19 passed, 0 failed, 0 pending** |
| tests | **37 pass** |
| lint | ruff clean |
| clean extract of `dist/` | reproduces all 15 accuracy metrics **exactly** |
| deck | `solution_presentation.pptx`, 12 slides, every number generated from `results/` |

### Measured results

| Split | mis-lock | median px | pass@1px | pass@0.5px | screen recall | runtime p50 |
|---|---|---|---|---|---|---|
| sponsor `verify` (40) | **20.0%** | 0.251 | 77.5% | 72.5% | 90.0% | 406 ms |
| bench (30, ours) | **16.7%** | 0.342 | 76.7% | 63.3% | 86.7% | 397 ms |
| holdout FinFET (30) | **10.0%** | 0.220 | 83.3% | 66.7% | 90.0% | 391 ms |

**Aggregate 16/100 = 16.0%.** Baselines 25.0 / 76.7 / 90.0%. Runtime certified against a 19–20 ms
baseline control, ratio ~20×.

Paired against the previous configuration on the same 100 pairs: **0 regressions, 6 fixes, exact
McNemar p = 0.031.**

### Shipped configuration — `localize.py::build_config`

```python
PipelineConfig(label="driftlock", subpixel=True, drift_correction=True,
               pose_search=True, top_k=10, candidate_refit=True,
               median_filter=True,
               refit_steps=5, refit_scale_span=0.03, refit_rotation_span=1.5,
               refit_screen_steps=2, refit_screen_top_n=10)
```

---

## 2. The two findings that carry the submission

### 2a. The oracle ceiling — what the architecture actually contributes (§35)

Given the generator's **exact** `scale_ratio` and `rotation_deg`:

| | ZNCC at the exact GT pose |
|---|---|
| at the **true** location | **0.7661** |
| at the **winning** location | **0.8615** |
| truth out-correlates the winner in | **2 / 15** (exact two-sided p = 0.007) |

**At a fixed pose the true site correlates *worse* than the impostor by 0.065.** These were never
selection errors — correlation is maximised elsewhere. An oracle-pose plain argmax scores 70/100
against the shipped 84/100 and recovers 1 of 16 failures.

Strictly paired on the same 8 failures:

| | deficit (winner − truth) |
|---|---|
| at the exact oracle pose | **+0.0654** |
| after the per-candidate refit | **+0.0072** |
| **refit closes** | **89.0%** (gap reduced in 6/8) |

> The headline is not "16% mis-lock remains". It is: **at a fixed pose the true site is behind by
> 0.065; DriftLock's geometry recovers 89% of that.**

Regenerate: `python scripts/oracle_ceiling.py` → `results/oracle_ceiling.csv`.

*Caveat kept deliberately:* the 0.002 IID correlation standard error is a **scale, not a calibrated
floor** — SEM pixels are blurred, periodic and interpolated, so effective sample size is far below
10,000. And the ceiling is for **rules reading the fixed-pose correlation**, not for every
conceivable method.

### 2b. Freedom flows to the wrong candidate (§36)

Three degrees of freedom added to the forward model, measured as *differential* gain (truth minus
winner) on the 8 paired failures:

| added freedom | truth | winner | **differential** | truth better in |
|---|---|---|---|---|
| PSF blur | +0.0013 | +0.0009 | **+0.0003** | 7/8 (p = 0.070) — closes 3% |
| anisotropic scale + shear | +0.0010 | +0.0014 | **−0.0004** | 4/8 |
| line-jitter, quadratic in y | −0.0312 | −0.0002 | **−0.0310** | 2/8 |

> **Every degree of freedom either helps negligibly or helps the wrong candidate — monotonically.**

A candidate that already fits well cannot benefit from extra freedom; one that fits badly can. This
is the fourth measurement of that asymmetry (§15d refit-gain at 80–92%, §23f the screen, §36b,
§36c). **The shipped `rigid pose + bounded refit` is the measured optimum, not an approximation to a
richer model we lacked time to build.**

---

## 3. Failure decomposition — where the remaining 16 live

`results/failure_decomposition.csv`, 100 pairs:

| stage that lost it | count | can a better ranker fix it? |
|---|---|---|
| never a candidate | 3 | no |
| cut by the screen | 4 | no — the wide stage never sees it |
| outscored at the final comparison | 9 | in principle; six criteria have failed |

**The true candidate is never the runner-up.** Across 15 instrumented held-out failures: rank ≤2 in
**0**, rank ≤3 in 1, rank ≤5 in 4, absent from the top 20 in **7**. Any idea of the form "break the
tie between the top two" is dead on arrival — the tied set is populated by *other impostors*.

Under **charging streaks** the mode inverts: 23.3% ABSENT vs 3.3% OUTSCORED. `top_k` at 10/20/30 is
flat at 33.3%, so the peak is **erased, not demoted**.

---

## 4. Robustness envelope

`results/robustness.csv`, 25 operating points, validation-only seeds (90,000,000+), disjoint from
every reporting and tuning split.

| axis | in-spec | beyond spec |
|---|---|---|
| dose (32× range) | 13.3–20.0% | 16.7% at 8× noisier |
| read noise σ | 26.7% at nominal | 6.7% at 4× |
| **scale** | 16.7% at 9–11:1 | **40.0%** at 8–12:1 |
| rotation | **10.0%** at 0°/±1°/±2° | 16.7% at ±3°, 26.7% at ±5° |
| charging streaks | — | **33.3%** ← named by the spec |
| barrel distortion | — | 43.3% ← *not* named by the spec |
| salt-and-pepper | — | 6.7% (with the median filter) |
| mixed (spec + 4× noise) | — | 23.3% |
| mixed (everything, beyond spec) | — | 46.7% |

Degradations **compose roughly additively**; no new failure mode emerges. Target position: no
dependence detectable in this 100-pair sample (`results/position_strata.csv`, all Wilson intervals
overlap, patterns non-monotone).

---

## 5. Everything closed, with its number

**Do not retry any of these.** Each has a measurement or a mechanism.

### Selection / scoring
| direction | result |
|---|---|
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
| PSF blur | +0.0003, closes 3% (§36a) |
| micro-warp | −0.0004 (§36b) |
| line-jitter correction | −0.0310 (§36c) |

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

Nothing algorithmic is queued, and that is a conclusion rather than a schedule artefact.

1. **Determinism test** (PROGRESS 3.8) — still outstanding.
2. **RGB optical extension** — the explicit scored bonus, never started.
3. **Deck and demo polish** — where the remaining marks are.

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
python scripts/oracle_ceiling.py
python scripts/run_ablation.py --manifest sponsor=... --manifest bench=... --manifest finfet=...
python scripts/failure_analysis.py && python scripts/make_failure_case.py --manifest data/bench/manifest.csv
python scripts/make_results_doc.py && python scripts/make_deck.py
python scripts/verify_submission.py --strict && python scripts/package_submission.py
```

**Runtime caveat:** the benchmark self-heats. The first heavy run after idle reads ~1.6× slow *with a
clean baseline control* — the control is 19 ms and completes inside the CPU's boost window while a
400 ms call does not. Both gates (control level and p95/p50 dispersion) must pass.
