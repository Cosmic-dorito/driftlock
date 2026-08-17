# SUBMISSION — requirements, status, and what is left

**Deadline: 18 August 2026** — extended from the 16th, confirmed by the organiser in writing
(Sanjay Subramanyan, 17 Aug 21:51). Submission needs the **GitHub link and the PDF** in the portal.

This file is the single checklist. It is transcribed from three primary sources and nothing in it is
inferred:

1. `Problem Statement 02_Applied Materials_ PS 2.pptx` — the official problem statement
2. `Idea-Submission-Template_Hackathon-2026-1.pptx` — the mandatory i4C deck template
3. The organiser Q&A webinar transcript (`Applied Materials Problem Statement: Key Concepts & Q&A`)

Where a requirement came from the transcript rather than a written document it says so, because a
spoken clarification is weaker evidence than a slide and should be treated that way.

---

## 1. How we are actually scored

From the problem statement, slide 8:

| Weight | Component |
|---|---|
| **50%** | Inference results — correct coordinates on their test data, **including computation time** |
| **30%** | Augmentation code producing real-like SEM images of FinFET/DRAM from literature study |
| **10%** | Root-cause identification / explainability on failure cases |
| Bonus | The same done for **RGB images of optical tools** |

### The tolerance ladder — the single most important thing in the transcript

> *"We start with a very liberal approach, okay, with five pixel error — how many cases do you pass?
> If you pass all of them, very good, we'll reduce it by four pixel, see how many pass, then we make
> it two pixels, one pixel, and then sub-pixel."*

**Scoring is a graded ladder at 5 / 4 / 2 / 1 / sub-pixel, not a single threshold.** This is exactly
the metric set `evaluate.py` already emits, and it is why the sub-pixel work matters far more than a
single mis-lock rate suggests: the sponsor's own baseline outputs `integer + 50.0` and therefore
**cannot score at all below 0.5 px**.

Where we stand on that ladder today:

| tolerance | sponsor (40) | bench (30) | FinFET (30) |
|---|---|---|---|
| ≤ 5 px | **100%** | 86.7% | 96.7% |
| ≤ 4 px | **100%** | 86.7% | 96.7% |
| ≤ 2 px | **100%** | 83.3% | 93.3% |
| ≤ 1 px | **97.5%** | 83.3% | 90.0% |
| **≤ 0.5 px** | **92.5%** | 66.7% | 76.7% |

### Runtime is a threshold, not a race

> *"If one is 1 second and another is 1.2 seconds, for us both are equal. But if one is 1 second and
> another is 10…"*

Computation time is judged at **order-of-magnitude**, not milliseconds. At ~0.6 s/pair we are inside
the band this describes. This materially reduces the weight of the uncertified-runtime caveat —
but it does not license quoting an uncertified number (see §5).

---

## 2. Component 1 — the deck

**Must use the i4C template**, with the core theme kept. The organiser confirmed in writing that
inner elements, content and even the background image may be replaced.

The template ships 10 slides; **slide 1 is an instructions slide and must be deleted**, leaving
exactly the nine the problem statement maps content onto:

| Template slide | Problem-statement mapping | What goes in |
|---|---|---|
| 2 — Team Details | Slide 1 | Team name, members, roles, college, contact ⚠️ **needs the team's real details** |
| 3 — Problem Statement Addressed | Slide 2 | Drift-Sense; why navigation-error recovery matters |
| 4 — Idea Description | Slide 3 | DRAM choice; classical ML; why beats template matching on periodic layouts |
| 5 — Proposed Solution | Slide 4 | Generator design, localization method, pipeline diagram, citations |
| 6 — Innovation and Uniqueness | Slide 5 | Periodic-ambiguity handling; the 10× scale approach |
| 7 — Impact and Benefits | **Slide 6 — RESULTS** | Accuracy on 30+ cases, time per pair, **one success + one honest failure**, visual |
| 8 — Technology & Feasibility | Slide 7 | Stack, hardware, generation time, inference time, model size |
| 9 — GitHub & Video Link | Slide 8 | **GitHub link (mandatory)**, video (optional) |
| 10 — Research and References | Slide 9 | All citations backing augmentation/noise choices |

⚠️ The template's own instruction slide says "keep the maximum slides limit up to six (6-7)". The
Applied Materials problem statement specifies a nine-slide mapping. **The problem statement governs
for this track** — it is the track-specific document — but this conflict is recorded here rather
than silently resolved.

---

## 3. Component 2 — the GitHub repository (mandatory, must be PUBLIC)

| # | Required | Status |
|---|---|---|
| 1 | `README.md` — a reviewer clones, generates a pair, and runs localization **without contacting us** | ✅ present |
| 2 | Dataset generator, standalone `.py`, params: architecture (DRAM/FinFET), number of pairs, output dir; records true centre as ground truth | ✅ `generate_dataset.py` |
| 3 | Localization inference script, standalone `.py`, takes reference path + search path, outputs predicted centre (x, y), **runs without manual edits** | ✅ `localize.py` |
| 4 | DL model weights, auto-loaded | n/a — no DL in the shipped path |
| 5 | Training script/notebook | n/a |
| 6 | `requirements.txt` — complete pip freeze | ✅ present |
| 7 | Citation documents corresponding to the deck's citations | ✅ `docs/REFERENCES.md` |

> **CRITICAL, quoted from the problem statement:** *"The localization inference script is the most
> important file in your repository. Applied Materials will run it directly on their test image
> pairs to compute your Phase 2 score. It must run without manual edits… Test it on a fresh machine
> before submitting. An unrunnable script cannot be scored."*

### Organiser instruction on `.npy`

> *"Keep .npy → .png conversion as a separate script/module, and document how it is invoked from the
> main workflow. PNGs are useful for visualization. Evaluators can quickly inspect results
> visually."*

This implies **the test data may arrive as `.npy`**. Nothing in the repo reads `.npy` today. See the
pending list.

---

## 4. Dataset expectations

* **At least 30** representative evaluation cases — we report **100** across three splits, plus 750
  stress pairs and 200 tuning pairs.
* No fixed maximum. **Diversity over quantity**, and explain *why* each test case is meaningful.
* Must include scale variation, noise, rotation, repetitive patterns, challenging localization.
* From the transcript: the test set will have **1–2° rotation**, scale variation around the 10×
  ratio, astigmatism/blur, gamma falloff at corners, and charging artifacts. The search image
  **will be noisier than the reference**.
* From the transcript: the test data will **not** contain the large easy pattern shown in the demo —
  *"it will have something different"*.

---

## 5. Claims discipline for the deck

Every number on a slide must exist in `results/`; `scripts/verify_submission.py` enforces this and
fails the build otherwise. Two specific things must not be overstated:

1. **Runtime is not certified.** The dispersion gate reads 1.186 against a 1.18 threshold. Say
   *"stable measured runtime on a healthy machine, marginal dispersion gate failure"* — never
   "certified". The threshold was deliberately not widened.
2. **The centre-rule branch exists but is not the default.** The problem statement asks for
   "whichever is closest to the search image's centre" when several regions match. We implement it
   (`select_by_centre_rule`) and it is reachable by config, but it is **off by default because it is
   measurably harmful on our data** — 32.5% / 20.0% / 16.7% mis-lock against 0.0% / 13.3% / 3.3%
   (ADR-0021, and the ablation row "centre rule on the default"). This is a deliberate, measured
   deviation and must be **stated on the slide**, not hidden.

---

## 6. Status

### ✅ Finished

* Localization pipeline at **5.0% aggregate mis-lock** (0.0 / 13.3 / 3.3), 55 fixes and 0
  regressions against the sponsor's own baseline, independently re-derived by `scripts/audit_results.py`
* Own generator with physics the starter omits (SE edge brightening, rotation, scale, fractional
  origins, charging, barrel, astigmatism)
* 25-point robustness sweep; failure decomposition; paired significance testing
* RGB optical bonus modality (§41, ADR-0033)
* 69 tests, ruff clean, `scripts/verify_submission.py --strict` 21/21
* Determinism test (PROGRESS 3.8)
* `docs/REFERENCES.md` with the five-column verification rule (R1)

### 🔄 In progress

* This document

### ⬜ Pending — ordered by what blocks submission

| P | Item | Owner |
|---|---|---|
| **P0** | **Create the public GitHub repo and push** — mandatory; nothing else matters if the evaluator cannot clone it | **user** |
| **P0** | Team details for deck slide 2 — names, roles, academic years, college, leader phone + email | **user** |
| **P0** | Rebuild the deck on the i4C template, 9 slides, delete the instructions slide | assistant |
| **P0** | Export the deck to PDF (the portal wants the PDF) | assistant |
| **P0** | `.npy` → `.png` converter as a separate documented script, invoked from the main workflow | assistant |
| **P1** | Make `localize.py` accept `.npy` inputs directly, so an unconverted test pair still scores | assistant |
| **P1** | Fresh-clone dry run: clone to an empty dir, `pip install -r requirements.txt`, run both scripts | assistant + user |
| **P2** | Clean-machine runtime re-measure (CPU currently down-clocked to 1400/3800 MHz) | user (idle machine) |
| **P2** | Demo video (optional but recommended by the template) | user |

