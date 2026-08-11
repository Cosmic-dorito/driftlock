# PROGRESS — live gate tracker

**Deadline 16 Aug 2026.** Update this when you clear a gate, not retroactively.
Put your initials and the date. If a gate slips, say so here rather than quietly carrying it.

Roles: **A** = Data/Physics · **B** = Algorithm · **C** = Eval/Packaging/Deck.
Owner assignment (fill in on Day 0): A = ____ · B = ____ · C = ____

---

## Day 0 — scaffolding (11 Aug, evening) — IN PROGRESS

| # | Item | Owner | Status |
|---|---|---|---|
| 0.1 | `git init`, folder layout, `.gitignore`, `.gitattributes`, `LICENSE`, `pyproject.toml`, `.editorconfig` | all | ✅ done |
| 0.2 | `CLAUDE.md` written **before** any code | all | ✅ done |
| 0.3 | `docs/SPEC.md` extracted from the AMAT PDF; PDF moved to `reference/` | all | ✅ done |
| 0.4 | `docs/DECISIONS.md` seeded with ADR-0001…0008 | all | ✅ done |
| 0.5 | `docs/PLAN.md` = the approved plan | all | ✅ done |
| 0.6 | Manifest schema + CLI signatures frozen in `CLAUDE.md` | all | ✅ done |
| 0.7 | `.venv` + pinned `requirements.txt`; OpenCV 5 API surface verified (ADR-0003) | all | ✅ done |
| 0.8 | `Makefile` + `make.ps1` with matching task names | all | ✅ done |
| 0.9 | README skeleton | C | ✅ done |
| 0.10 | Push to a private GitHub repo; all three clone and run `make setup` successfully | all | ⬜ **next** |
| 0.11 | Everyone fetches the sponsor generator and produces ~50 pairs locally | all | ⬜ |
| 0.12 | Assign A / B / C and record above | all | ⬜ |
| 0.13 | `scripts/verify_submission.py`, `smoke_test.*`, `package_submission.py`, `fetch_reference_generator.sh` | C | ✅ done |
| 0.14 | `tests/test_deps_api.py` — API contract locked (8 tests, ruff clean) | C | ✅ done |

**Exit criterion:** three people on three machines can each run `make setup` and `make test` green.

### Day 0 findings worth knowing before you write code

Two things were settled empirically tonight (rule R7 — test, don't trust memory), and both would
have cost hours if discovered later:

1. **Python 3.14 is fine.** The plan originally recommended downgrading to 3.11 out of caution about
   wheel availability. That was wrong: `cp314` wheels exist for the whole stack, and torch 2.12.1+cpu
   is already installed. No downgrade. (ADR-0002)
2. **`phase_cross_correlation` must be called with `normalization=None`.** The scikit-image default
   `'phase'` silently returns ~zero shift on blurred images — 2.8 px error on a true 2.86 px
   displacement at blur σ=3. Our search images *are* blurred by the beam PSF. (ADR-0009)

Also: `findTransformECC` recovers sub-pixel translation to **0.037 px** (MOTION_AFFINE) on
band-limited data, which validates plan step A9. And benchmark sub-pixel methods on **band-limited**
images only — white-noise test signals alias under interpolation and understate accuracy ~7×.

---

## Day 1 — foundations (12 Aug)

| # | Item | Owner | Status |
|---|---|---|---|
| 1.1 | **R3: verify H1–H9 empirically on real pairs**, log outcomes in `DECISIONS.md` | B | ⬜ |
| 1.2 | `tests/test_geometry.py` with an **asymmetric** hand-derived case, written *before* the matcher | B | ⬜ |
| 1.3 | Reproduce the sponsor baseline; record its numbers as our floor | B | ⬜ |
| 1.4 | Tier A steps A1–A3, A6, A8 | B | ⬜ |
| 1.5 | DRAM layout at 1 nm/px, zoning, SE edge brightening, PSF, Poisson + detector noise | A | ⬜ |
| 1.6 | First 50 pairs + manifest from our generator | A | ⬜ |
| 1.7 | `evaluate.py` with all spec-required metrics; manifest loader; plots | C | ⬜ |
| 1.8 | `smoke_test.sh` + `smoke_test.ps1`; `requirements.txt` finalized | C | ⬜ |
| 1.9 | Deck skeleton on the sponsor's 12-slide structure | C | ⬜ |

**🚦 GATE 1 (end of Day 1): ≥90% pass@5px on sponsor-generated data.**
If this fails, everything downstream is premature — stop and fix.

---

## Day 2 — the real algorithm (13 Aug)

| # | Item | Owner | Status |
|---|---|---|---|
| 2.1 | A4 per-pair blind self-calibration | B | ⬜ |
| 2.2 | A5 lattice-as-a-ruler pose estimation + fallback chain | B | ⬜ |
| 2.3 | A7 periodic–aperiodic decomposition | B | ⬜ |
| 2.4 | A9 sub-pixel (upsampled DFT) + ECC affine | B | ⬜ |
| 2.5 | Rotation + scale in the generator; FinFET; fractional origins; aperiodic content | A | ⬜ |
| 2.6 | Full 200-pair set with complete metadata and seeds | A | ⬜ |
| 2.7 | Ablation infrastructure | C | ⬜ |
| 2.8 | **Cross-generator run** (ours + sponsor's), stratified tables, figures | C | ⬜ |

**🚦 GATE 2 (end of Day 2): median Euclidean error < 0.5 px.**
Also: decide by EOD whether GAT and phase congruency actually beat plain ZNCC. Keep whichever wins
on data (R9 — a negative result goes in the ablation table with its number).

---

## Day 3 — provably good, then FREEZE (14 Aug)

| # | Item | Owner | Status |
|---|---|---|---|
| 3.1 | B1 differentiable analysis-by-synthesis | B | ⬜ |
| 3.2 | B2 Cramér–Rao bound + achieved-vs-CRLB plot | B | ⬜ |
| 3.3 | B3 conformal prediction confidence + coverage check | B | ⬜ |
| 3.4 | Failure case visualized with root cause; runtime profiling; determinism check | B | ⬜ |
| 3.5 | `REFERENCES.md` complete — all five columns, every row verified (R1) | A | ⬜ |
| 3.6 | Per-parameter physical justification for the generator | A | ⬜ |
| 3.7 | Full 300-pair run; all tables and plots final | C | ⬜ |
| 3.8 | README with exact commands; `pip freeze`; **clean-machine dry run** | C | ⬜ |
| 3.9 | Deck complete, every number traceable to `results/` | C | ⬜ |
| 3.10 | **R8 red-team pass** — C re-derives B's headline numbers blind; A re-checks physics claims | all | ⬜ |

**🚦 GATE 3 — CORE FREEZE, 14 Aug 18:00.**
From this moment a submittable package exists. Everything after is additive and behind flags.

---

## Day 4 — stretch only, all flag-gated (15 Aug)

Priority order. Stop wherever time runs out; each is independently shippable.

| # | Item | Owner | Status |
|---|---|---|---|
| 4.1 | C1 lattice-aware transformer re-ranker (`--no-rerank` must still work) | B | ⬜ |
| 4.2 | C2 SOTA comparison: RoMa v2 / EfficientLoFTR / XFeat on our pairs | B/C | ⬜ |
| 4.3 | C3 robustness sweep beyond spec (8:1–12:1, ±5°, 2× noise) | A/C | ⬜ |
| 4.4 | C4 interactive drift demo + 60–90 s video | C | ⬜ |
| 4.5 | C5 RGB optical extension (the scored bonus) | A | ⬜ |
| 4.6 | Final fresh-clone dry run; `make verify` green; every PPT number re-checked | all | ⬜ |

**Submit on the morning of 16 Aug with the buffer intact — not at the deadline.**

---

## Blockers / open questions

| Raised | By | Item | Status |
|---|---|---|---|
| 11 Aug | — | OpenCV resolves to 5.x on Py3.14; API surface needs verification (ADR-0003) | 🔄 checking |
| 11 Aug | — | Team roles A/B/C not yet assigned | ⬜ open |
| 11 Aug | — | GitHub remote not yet created | ⬜ open |
