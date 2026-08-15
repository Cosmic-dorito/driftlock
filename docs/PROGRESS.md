# PROGRESS — live tracker

**Deadline 16 Aug 2026.** Update this when you clear a gate, not retroactively.
If a gate slips, say so here rather than quietly carrying it.

> **⏩ Resuming after a break? Read the RESUME HERE section at the top of `docs/HANDOFF.md` first.**
> It carries the current numbers, the shipped config, the single next action, and the list of things
> already measured and refuted so they are not retried.

**Execution model: sequential.** One stage at a time, in dependency order. The governing rule:
**do not start a stage until the previous one has a measured number in `results/`.**

---

## Stage 0 — Scaffolding ✅ COMPLETE (11 Aug)

| # | Item | Status |
|---|---|---|
| 0.1 | `git init`, folder layout, `.gitignore`, `.gitattributes`, `LICENSE`, `pyproject.toml`, `.editorconfig` | ✅ |
| 0.2 | `CLAUDE.md` written **before** any code | ✅ |
| 0.3 | `docs/SPEC.md` extracted from the AMAT PDF; PDF moved to `reference/` | ✅ |
| 0.4 | `docs/DECISIONS.md` seeded with ADR-0001…0009 | ✅ |
| 0.5 | `docs/PLAN.md` = the approved plan | ✅ |
| 0.6 | Manifest schema + CLI signatures frozen in `CLAUDE.md` | ✅ |
| 0.7 | `.venv` + pinned `requirements.txt`; OpenCV 5 API surface verified | ✅ |
| 0.8 | `Makefile` + `make.ps1` | ✅ |
| 0.9 | README skeleton | ✅ |
| 0.13 | `verify_submission.py`, `smoke_test.*`, `package_submission.py`, `fetch_reference_generator.sh` | ✅ |
| 0.14 | `tests/test_deps_api.py` — API contract locked (8 tests, ruff clean) | ✅ |
| 0.10 | Push to a GitHub remote | ⬜ **user action** — no remote configured yet |

### Findings from Stage 0 — read before writing code

Settled empirically (rule R7 — test, don't trust memory). Both would have cost hours later:

1. **Python 3.14 is fine.** The plan originally said downgrade to 3.11. Wrong: `cp314` wheels exist
   across the stack and torch 2.12.1+cpu was already installed. (ADR-0002)
2. **`phase_cross_correlation` must use `normalization=None`.** The scikit-image default `'phase'`
   silently returns ~zero shift on blurred images — 2.8 px error on a true 2.86 px displacement at
   blur σ=3. Our search images *are* blurred by the beam PSF. (ADR-0009)

Also: `findTransformECC` recovers sub-pixel translation to **0.037 px** (`MOTION_AFFINE`) on
band-limited data, validating plan step A9. And benchmark sub-pixel methods on **band-limited**
images only — white-noise test signals alias under interpolation and understate accuracy ~7×.

---

## Stage 1 — Verify the foundations (R3) ✅ COMPLETE (11 Aug, win-2)

Everything downstream rests on facts read from the sponsor's *source code*, not from running it.
Confirm each on real generated pairs before building on it.

| # | Item | Status |
|---|---|---|
| 1.1 | Clone the sponsor generator into `third_party/` | ✅ |
| 1.2 | Generate ~50 pairs from it | ✅ 40 pairs, `data/_sponsor/verify` |
| 1.3 | Confirm or refute **H1–H9**; record in `docs/DECISIONS.md` | ✅ all confirmed, +H10 |
| 1.4 | Write `tests/test_geometry.py` with an **asymmetric** hand-derived case | ✅ |

**🚦 GATE 1: every hypothesis marked confirmed or refuted, with evidence.**
If one is refuted, the plan changes — say so immediately rather than building on it.

---

## Stage 2 — Baseline and measurement harness ✅ COMPLETE (11 Aug, win-2)

Reproduce the floor before claiming to beat it. Without a measured baseline, the ablation table has
no first row and no improvement can be substantiated (R6).

| # | Item | Status |
|---|---|---|
| 2.1 | `src/driftlock/io.py` — image loading, the single `(row,col)↔(x,y)` conversion site (ADR-0007) | ✅ |
| 2.2 | `evaluate.py` — Euclidean error; pass@5/4/2/1 px; sub-pixel; mean/median/p95/worst; runtime with hardware + timing method | ✅ |
| 2.3 | Reproduce the sponsor baseline (`INTER_AREA` + `matchTemplate` argmax over 5 scales) | ✅ 25.0% mis-lock, 1.102 px |
| 2.4 | Record baseline numbers into `results/` as ablation row 1 | ✅ |

**🚦 GATE 2 CLEARED.** Baseline reproduces to the digit on both machines (win-2 / MacBook Air M2).

---

## Stage 3 — Our generator (30% of the score) ✅ COMPLETE (12 Aug, MacBook Air M2)

| # | Item | Status |
|---|---|---|
| 3.1 | DRAM 6F² layout at 1 nm/px; mat/strip zoning | ✅ `src/synth/layout.py` |
| 3.2 | SE edge brightening; charging shading; beam PSF (the physics the starter omits) | ✅ `src/synth/imaging.py` |
| 3.3 | Poisson shot + Gaussian detector noise, independent RNG streams per acquisition | ✅ |
| 3.4 | **Rotation (0–2°) and scale (9:1–11:1)** — the starter can produce neither | ✅ |
| 3.5 | **Fractional crop origins** → continuous GT, so sub-pixel claims are honest | ✅ (see 3.9) |
| 3.6 | FinFET layout | ✅ `data/holdout_finfet` |
| 3.7 | Full metadata + seeds; manifest per the frozen schema; `ambiguity_level` | ✅ |
| 3.8 | Determinism test: same seed → byte-identical images | ⬜ |
| 3.9 | **GT half-pixel convention corrected** — ours sat 0.5 px from the sponsor's for the same physical case, which alone would have failed every sub-pixel claim on our own benchmark | ✅ 12 Aug |
| 3.10 | **Per-mat pitch randomisation removed** — physically wrong (pitch is a design rule) and it destroyed magnification measurability | ✅ 12 Aug |

**🚦 GATE 3 CLEARED for the dataset itself.** Splits: `bench` (30, reporting), `dev` (40, tuning),
`holdout_finfet` (30, held out). Determinism test (3.8) still outstanding.

---

## Stage 4 STATUS — SUPERSEDED (12 Aug, evening, MacBook Air M2)

> ⚠️ **Historical. The numbers below are two generations old.** They are kept because the
> reasoning is still the record of how the pose problem was solved. For current results see
> the generated headline in `docs/RESULTS.md`, which is regenerated from `results/`.

**The rotation/scale envelope now works.** It previously did not work *at all*: on our own
generator the shipped pipeline mis-located 95% of pairs. Root cause was that the template builder
could only express magnifications in ~1% steps, so no pose search could ever have found the right
one (ADR-0014).

| Split | | Mis-lock | Median | pass@1px | pass@0.5px | Runtime p50 |
|---|---|---|---|---|---|---|
| sponsor `verify` | baseline | 25.0% | 1.102 | 40.0% | 17.5% | 37 ms |
| | **now** | 27.5% | **0.297** | **70.0%** | **67.5%** | 371 ms |
| bench (ours, ±2°, 9–11:1) | baseline | 76.7% | 326.9 | 10.0% | 3.3% | 38 ms |
| | **now** | **33.3%** | **0.556** | **60.0%** | **46.7%** | 406 ms |
| holdout FinFET | baseline | 90.0% | 359.9 | 3.3% | 3.3% | 38 ms |
| | **now** | **33.3%** | **0.706** | **66.7%** | **33.3%** | 398 ms |

Three bugs found by measurement, two of which the sponsor's data structurally could not reveal:
scale quantisation in the forward operator (ADR-0014), our generator's GT sitting half a pixel from
the sponsor's convention (ADR-0016), and the drift estimator mistaking rotation for drift
(ADR-0017, then solved outright by the two-axis cancellation).

**Still the binding constraint: the mis-lock rate**, now 27.5–33.3%. Candidate recall says the
ceiling is ~7.5%. Two re-rankers have been tried and both failed honestly (PADM overfit;
coarse-level consensus harmful). This is where the remaining localization points are.

---

## Stage 4 STATUS — SUPERSEDED (12 Aug, earlier)

> ⚠️ **Historical.** Kept for the reasoning, not the numbers. Current results live in
> `docs/RESULTS.md` (generated).

**Shipped and validated on held-out data:** sub-pixel DFT + blind drift correction.

| Split | mis-lock | median | pass@1px | pass@0.5px | runtime |
|---|---|---|---|---|---|
| verify (tuned) | 25.0% | 1.102 → **0.238** | 40% → **75%** | 18% → **72%** | 50 ms |
| held-out dram | 20.0% | 0.952 → **0.301** | 50% → **80%** | 23% → **67%** | 48 ms |
| held-out FinFET | 30.0% | 1.091 → **0.422** | 43% → **70%** | 13% → **60%** | 48 ms |

**Removed as overfit:** PADM re-scoring (helped the tuned split by 5 pts, hurt held-out dram by 6.7
and FinFET by 13.3). See ADR-0012. Its removal also cut runtime from 224 ms to 50 ms.

**The mis-lock rate is unchanged from baseline and is now the only thing capping the score.**
Candidate recall says the answer is in the top-20 92.5% of the time, so the ceiling is ~7.5% — but
any re-ranker must be validated on held-out architectures before it is believed, and gated to fall
back to the argmax when unsure. Refinement fails gracefully; re-ranking fails destructively.

---

## Stage 4 — Tier A matcher (the ML-optimal core)

Add one stage at a time and measure each against the previous. Anything that does not help goes in
the ablation table as a negative result with its number (R9).

| # | Item | Status |
|---|---|---|
| 4.1 | A1 Generalized Anscombe Transform | ⬜ |
| 4.2 | A2 phase congruency + median + row destriping | ⬜ |
| 4.3 | A3 exact forward operator (`INTER_AREA`) | ⬜ |
| 4.4 | A6 top-K candidates, NMS at lattice pitch | ⬜ |
| 4.5 | A8 ambiguity index + literal closest-to-centre rule | ⬜ |
| 4.6 | A4 per-pair blind self-calibration | ⬜ |
| 4.7 | A5 lattice-as-a-ruler pose estimation + fallback chain | ⬜ |
| 4.8 | A7 periodic–aperiodic decomposition | ⬜ |
| 4.9 | A9 sub-pixel (upsampled DFT, `normalization=None`) + ECC affine | ⬜ |

**🚦 GATE 4: median Euclidean error < 0.5 px, beating the Stage-2 baseline on the same data.**

---

## Stage 5 — Provably good (Tier B)

| # | Item | Status |
|---|---|---|
| 5.1 | B1 differentiable analysis-by-synthesis | ⬜ |
| 5.2 | B2 Cramér–Rao bound + achieved-vs-CRLB plot | ⬜ |
| 5.3 | B3 conformal prediction confidence + empirical coverage check | ⬜ |
| 5.4 | Cross-generator validation (ours **and** the sponsor's) | ⬜ |
| 5.5 | Failure case visualized with root cause; runtime profiling | ⬜ |
| 5.6 | Full ablation table | ⬜ |

**🚦 GATE 5 — CORE FREEZE.** A submittable package exists from this moment.
Everything after is additive and behind flags.

---

## Stage 7 — Solving the mis-lock ✅ (12 Aug, win-2)

> Numbers in this section were current when written. **The single source of truth for current
> results is the generated headline in `docs/RESULTS.md`.**

The binding constraint since Stage 4 was selection, not precision. It is now substantially better.

**What was tried:** an oracle-pose diagnostic (proving pose was *not* the bottleneck),
candidate-consensus periodic cancellation (mixed), refit-gain ranking (catastrophic),
refit + consensus (catastrophic), and **per-candidate pose refit (works)**. All five recorded with
numbers in `docs/FINDINGS.md` §15.

| Split | before | after | change |
|---|---|---|---|
| sponsor (40) | 27.5% | **25.0%** | −2.5 pts |
| bench (30, ours) | 33.3% | **30.0%** | −3.3 pts |
| **holdout FinFET (30)** | 33.3% | **16.7%** | **−16.6 pts** |

Sponsor worst-case error also fell from 271.71 px to 95.17 px, and FinFET pass@5px rose from 66.7%
to 83.3%.

**Why it generalised where three re-rankers did not:** it re-*scores* each candidate at its own best
pose rather than re-*ranking* by a new criterion, so it removes an unequal handicap instead of
introducing a preference (ADR-0019). The largest gain landing on the architecture it was never tuned
on is the signature of a real effect.

**Cost:** p50 ~780 ms → ~1200 ms measured back-to-back. Above our 300 ms aspiration; `top_k` is the
dial. Stated as a limitation rather than hidden.

**Runtime caution recorded:** absolute timings on this machine drifted by up to 3× for identical
code over a long session and did not recover after idling. Only back-to-back measurements are
comparable, and every quoted runtime comes from such a pairing.

---

## Stage 6 — Deliverables ✅ COMPLETE (12 Aug, win-2)

| # | Item | Status |
|---|---|---|
| 6.1 | `REFERENCES.md` complete — all five columns, every row VERIFIED (R1) | ✅ 6 verified |
| 6.2 | README with exact commands, results, assumptions, limitations | ✅ |
| 6.3 | **Solution PPT** on the sponsor's 12-slide structure | ✅ `solution_presentation.pptx` |
| 6.4 | `verify_submission.py --strict` clean | ✅ 16 passed, 0 failed, 0 pending |
| 6.5 | Clean-machine dry run: unzip `dist/` somewhere fresh, identical numbers | ✅ all 8 metrics bit-identical |

**🚦 GATE 6 CLEARED. A complete, submittable package exists.**

### All results re-measured on Windows (12 Aug)

The project was developed on a MacBook Air M2 and the folder was moved to a Windows machine. The
`.venv` did not survive the move (it pointed at `/opt/anaconda3`), so it was rebuilt, and **every
metric was regenerated here** so that `results/` and the stated hardware agree — the spec requires
runtime to be reported with its hardware, and quoting Mac timings from a Windows submission would
have been wrong.

**The accuracy numbers reproduced exactly across the two platforms** — bench baseline 76.7%
mis-lock and 326.905 px median on both. Only runtime differs, as it should.

| Split | | Mis-lock | Median | @5px | @1px | @0.5px | Runtime p50 |
|---|---|---|---|---|---|---|---|
| sponsor (40) | baseline | 25.0% | 1.102 | 75.0% | 40.0% | 17.5% | 24 ms |
| | **DriftLock** | 27.5% | **0.297** | 72.5% | **70.0%** | **67.5%** | 236 ms |
| bench (30, ours) | baseline | 76.7% | 326.905 | 23.3% | 10.0% | 3.3% | 20 ms |
| | **DriftLock** | **33.3%** | **0.556** | **66.7%** | **60.0%** | **46.7%** | 231 ms |
| FinFET (30, held out) | baseline | 90.0% | 359.893 | 10.0% | 3.3% | 3.3% | 20 ms |
| | **DriftLock** | **33.3%** | **0.706** | **66.7%** | **66.7%** | **33.3%** | 266 ms |

The deck is generated by `scripts/make_deck.py`, which reads `results/` at build time — so R2 is
enforced by construction rather than by discipline. It caught a real defect on its first run: the
CLI example on the implementation slide used two invented coordinates, which is exactly the class of
number that check exists to find. The example now reads a real prediction out of
`results/predictions_sponsor.csv`.

---

## Stage 8 — Screening the refit ✅ (13 Aug, win-2)

> Current numbers live in the generated headline in `docs/RESULTS.md`.

The §21d accuracy/runtime frontier — "2 points of mis-lock costs 3× runtime" — was an artefact of
the implementation, not a property of the problem, exactly as §22's correction hedged it might be.

| | held-out mis-lock | p50 |
|---|---|---|
| previously shipped (narrow refit) | 22.0% | 296 ms |
| wide dense, unscreened | 20.0% | 601 ms |
| **shipped now: wide dense + screen** | **18.0%** | **427 ms** |

**No split regressed, and all three reported splits improved:** sponsor 25.0 → 22.5%, bench
23.3 → 16.7%, holdout FinFET 16.7 → 13.3%. The `dev` tuning split was unchanged at 12.5% — an
earlier draft of this line said "every split improved", which was not true and is exactly the kind
of claim R6 exists to catch.

**How.** The recorded next action (hoist box-integration out of the refit's rotation loop) worked
and was bit-identical, but addressed only 6% of the cost. Profiling found the real driver: `top_k`
is per *pose*, so the refit receives 60 candidates and sweeps each over 25 poses — 1500 correlations
per pair. Screening with the cheap narrow grid and giving only the top 10 the dense one is **faster
and more accurate**, because the wide sweep is then centred on an already-corrected pose. ADR-0025,
FINDINGS §23.

Two packaging defects surfaced while re-verifying: a stale `*.rebuilt.pptx` had been committed, and
`package_submission.py` chose the deck by `next(glob("*.pptx"))` — so the zip could have shipped the
stale deck. Both fixed (FINDINGS §23h).

---

## Stage 9 — Stress testing, and what it found ✅ (14 Aug, win-2)

> Current numbers live in the generated headline in `docs/RESULTS.md`.

Searching the problem statement for deliverables we were not producing turned up a graded one:
*"Results across multiple noise levels, target positions, scales and rotations."* Every number in
`results/` came from a single operating point. Building that sweep (`scripts/robustness_sweep.py`,
22 points, validation-only seeds) then produced three findings, only one of which was about the
localizer.

| | held-out mis-lock |
|---|---|
| start of the day | 22.0% |
| **end of the day** | **16.0%** (20.0 / 16.7 / 10.0 across sponsor / bench / FinFET) |

Paired against the configuration it replaced, on the same 100 pairs: **0 regressions, 6 fixes,
exact McNemar p = 0.031.** Strictly dominant and significant.

**1. A stage rejected in the one regime where it could not work.** The median filter was recorded as
"no effect" (§3) and sat off for three days — measured on splits with `salt_pepper_prob = 0`. In its
actual regime it is worth 16.7% → 6.7%, costs −3 ms, and breaks 0 of 100 held-out pairs. Shipped
(ADR-0027). Row destriping got the same fair re-test and stays off, confirmed harmful.

**2. The sweep found a bug in our generator, not our localizer.** Barrel distortion read 53.3%
mis-lock with a *median error of 9.09 px* — the wrong shape for a mis-lock. The residual pointed
radially inward on 97% of pairs and fitted `a·r²` at R² = 0.811. Ground truth had been computed
before barrel was applied, so the label described a different image than the one saved. Fixed with a
solved inverse map and a hand-derived test; median fell to 1.19 px (ADR-0028). No reported number
moved — `barrel_distortion_k` defaults to 0.

**3. Our own mechanism claim was refuted, for the second time.** §23f predicted that in an outscored
failure the winning impostor travelled further in pose. Measured: 0 of 9, winners travel *less*.
The A/B/C/D ablation stands; the explanation does not, and is marked rather than rewritten.

Also: `results/significance.csv` now generates Wilson intervals and the paired test, after the sweep
accidentally ran the nominal configuration twice and got 20.0% and 26.7% from identical parameters
(ADR-0029). And the ablation's DEFAULT row now derives from `localize.py::build_config` — it had
silently drifted the moment the shipped config changed.

---

## Stage 10 — A retraction, and the largest accuracy gain since the refit ✅ (15 Aug, win-2)

> Current numbers live in the generated headline in `docs/RESULTS.md`.

| | aggregate mis-lock |
|---|---|
| start of the day | 16.0% |
| after reading the pose grid as evidence | 11.0% |
| **end of the day** | **8.0%** (**0.0** / 20.0 / 6.7 across sponsor / bench / FinFET) |

**1. The headline finding was retracted.** §35 — *"at the generator's exact pose the true site
correlates 0.065 worse than the impostor, and the refit recovers 89%"* — was measured once in a
scratchpad, printed to a terminal, and hand-copied into four documents. It never entered `results/`,
so neither R2 nor R8 could reach it. Writing it down properly (`scripts/pose_ceiling.py`) re-measured
it: the "winner" figure had been the **maximum of the correlation surface**, not the score at the
location the pipeline chose, and a maximum over ~810,000 positions beats any nominated point by
construction. Corrected, the truth (0.7661) and its impostor (0.7696) are *statistically
indistinguishable* — the margin is ~0.01, not a deficit. FINDINGS §37, ADR-0030: **a result with no
script is not a result.**

**2. Two literature-backed directions were built and closed.** A global scan-field calibration
(§38) measures the scanner from the periodic array and corrects the whole search image once, before
any candidate exists. It genuinely works — ZNCC at the true site rises **+0.0297** — and it changes
nothing, because it lifts the impostor by **+0.0301**. *A global correction is fair by construction,
which is exactly why it cannot break a tie.* A supercell search (§39), with a 400-permutation null,
found real higher-order structure at **order 2** — the `(i+j)%2` checkerboard, which is by
definition blind to the parity-*preserving* diagonal shift that causes our failures.

**3. And then the one that worked.** Reading the refit's pose grid as **evidence** rather than
taking its maximum: the maximum over ~25 poses is upward-biased, and the bias grows with how rough
that candidate's pose surface is, so a candidate that peaked once outranks one that was consistently
good. Same ZNCC, same grid, different summary — not a new criterion — and it adds no correlations.

| split | n | before | after | |
|---|---|---|---|---|
| dev *(tuning)* | 40 | 12.5% | 7.5% | +2/−0 |
| dev2 | 160 | 11.2% | **6.9%** | +7/−0 |
| sponsor | 40 | 20.0% | **5.0%** | +6/−0 |
| bench | 30 | 16.7% | 23.3% | +1/**−3** |
| FinFET | 30 | 10.0% | **6.7%** | +1/−0 |

**+17 fixed / −3 broken over 300 pairs, exact McNemar p = 0.0026** (ADR-0032). The failure
decomposition, regenerated without being consulted first, confirms it acted where it should: the
**outscored** bucket fell 9 → 4 while *absent* (3) and *screened* (4) held exactly still.

**4. And then the screen widened — because the selector changed.** §23d had measured
`refit_screen_top_n` at 6/10/15/20 and found it **flat**, so the cut point was closed. That sits
badly against 4 failures being lost at the screen, and both cannot be true unless the truth ranks
below every cut tested. Instrumenting it: on the four screened failures the truth sits at rank
**12, 14, 25 and 29** of 60, while on *correct* pairs its rank is median 0, p90 0. A wider cut always
did reach them — it never converted, because the recovered candidates were handed to the plain
maximum. With pose evidence selecting instead: **+4 fixed / 0 broken over 140 pairs**, no split
regressing, sponsor to **0.0%**, and aggregate 11.0% → **8.0%** (ADR-0034). The decomposition's
*screened* bucket went 4 → **0**.

> **A parameter measured as "flat" is flat against the pipeline it was measured in.** The trigger
> was a contradiction between two of our own recorded results, not a new idea.

**5. The RGB optical bonus shipped** (§41, ADR-0033). Not a colourised SEM — at `0.61 λ/NA` = 372.8
nm the 64 nm cell lattice is *absent*, so the modality images a coarser layer. The unchanged
pipeline localizes diffraction-limited RGB brightfield to **0.10 px median**, and measuring the
colour projection instead of assuming Rec. 601 luminance halves mis-lock (6.7% → 3.3%) and collapses
p95 error from 11.94 px to **0.51 px**.

---

## Stage 7 — Stretch, all flag-gated

Stop wherever time runs out; each is independently shippable.

| # | Item | Status |
|---|---|---|
| 7.1 | Lattice-aware transformer re-ranker (`--no-rerank` must still work) | ⬜ |
| 7.2 | SOTA comparison: RoMa v2 / EfficientLoFTR / XFeat | ⬜ |
| 7.3 | Robustness sweep beyond spec (8:1–12:1, ±5°, 2× noise) | ⬜ |
| 7.4 | Interactive drift demo + 60–90 s video | ⬜ |
| 7.5 | RGB optical extension (the scored bonus) | ⬜ |

**Submit on the morning of 16 Aug with the buffer intact — not at the deadline.**

---

## Blockers / open questions

| Raised | Item | Status |
|---|---|---|
| 11 Aug | No GitHub remote configured — user action | ⬜ open |
| 11 Aug | Git identity set repo-local as "DriftLock Team" / user email; change if real names wanted | ⬜ open |
