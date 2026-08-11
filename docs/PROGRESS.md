# PROGRESS — live tracker

**Deadline 16 Aug 2026.** Update this when you clear a gate, not retroactively.
If a gate slips, say so here rather than quietly carrying it.

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

## Stage 1 — Verify the foundations (R3) 🔄 IN PROGRESS

Everything downstream rests on facts read from the sponsor's *source code*, not from running it.
Confirm each on real generated pairs before building on it.

| # | Item | Status |
|---|---|---|
| 1.1 | Clone the sponsor generator into `third_party/` | 🔄 |
| 1.2 | Generate ~50 pairs from it | ⬜ |
| 1.3 | Confirm or refute **H1–H9**; record in `docs/DECISIONS.md` | ⬜ |
| 1.4 | Write `tests/test_geometry.py` with an **asymmetric** hand-derived case | ⬜ |

**🚦 GATE 1: every hypothesis marked confirmed or refuted, with evidence.**
If one is refuted, the plan changes — say so immediately rather than building on it.

---

## Stage 2 — Baseline and measurement harness

Reproduce the floor before claiming to beat it. Without a measured baseline, the ablation table has
no first row and no improvement can be substantiated (R6).

| # | Item | Status |
|---|---|---|
| 2.1 | `src/driftlock/io.py` — image loading, the single `(row,col)↔(x,y)` conversion site (ADR-0007) | ⬜ |
| 2.2 | `evaluate.py` — Euclidean error; pass@5/4/2/1 px; sub-pixel; mean/median/p95/worst; runtime with hardware + timing method | ⬜ |
| 2.3 | Reproduce the sponsor baseline (`INTER_AREA` + `matchTemplate` argmax over 5 scales) | ⬜ |
| 2.4 | Record baseline numbers into `results/` as ablation row 1 | ⬜ |

**🚦 GATE 2: baseline measured and written to `results/metrics.csv`.**

---

## Stage 3 — Our generator (30% of the score)

| # | Item | Status |
|---|---|---|
| 3.1 | DRAM 6F² layout at 1 nm/px; mat/strip zoning | ⬜ |
| 3.2 | SE edge brightening; charging shading; beam PSF (the physics the starter omits) | ⬜ |
| 3.3 | Poisson shot + Gaussian detector noise, independent RNG streams per acquisition | ⬜ |
| 3.4 | **Rotation (0–2°) and scale (9:1–11:1)** — the starter can produce neither | ⬜ |
| 3.5 | **Fractional crop origins** → continuous GT, so sub-pixel claims are honest | ⬜ |
| 3.6 | FinFET layout | ⬜ |
| 3.7 | Full metadata + seeds; manifest per the frozen schema; `ambiguity_level` | ⬜ |
| 3.8 | Determinism test: same seed → byte-identical images | ⬜ |

**🚦 GATE 3: 30+ committed bench pairs; `verify_submission.py` clears the dataset checks.**

---

## Stage 4 STATUS (12 Aug) — precision solved, selection unsolved

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

## Stage 6 — Deliverables

| # | Item | Status |
|---|---|---|
| 6.1 | `REFERENCES.md` complete — all five columns, every row VERIFIED (R1) | ⬜ |
| 6.2 | README with exact commands, results, assumptions, limitations | ⬜ |
| 6.3 | **Solution PPT** on the sponsor's 12-slide structure | ⬜ |
| 6.4 | `verify_submission.py --strict` clean | ⬜ |
| 6.5 | Clean-machine dry run: unzip `dist/` somewhere fresh, identical numbers | ⬜ |

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
