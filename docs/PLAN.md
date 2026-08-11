# DriftLock — Applied Materials "Drift-Sense" Hackathon 2026

**Deadline: 16 Aug 2026. Today: 11 Aug 2026. Team of 3, all with Claude Code.**

---

## Context

Drift-Sense asks for cross-magnification localization: given a 1000×1000 reference at 100× (1 nm/px) and a 1000×1000 search image at 10× (10 nm/px), return the centre `(x, y)` of the reference pattern inside the search image. The structures are highly periodic, so a wrong location can look correct.

I read the sponsor's participant PDF and their published starter resource — the HF Space `aayushraina21/drift-sense-synthetic-data`, which ships a **complete generator and a baseline solution in full source**. That reading gives us an exact model of what the evaluation data almost certainly looks like, and it reshapes the architecture.

### Hard facts established from the sponsor's own source

| Fact | Consequence |
|---|---|
| Fine canvas 10000×10000 @ 1 nm/px; reference = 1000×1000 crop; search = **whole canvas** blurred + `INTER_AREA` ↓10 | Reference footprint in the search image is exactly **100×100 px**. This is a *downscale-the-reference* problem, not a small-template problem. |
| `gt = (x0/10 + 50, y0/10 + 50)`, `x0,y0` integer | GT on a 0.1 px grid. Sub-pixel accuracy is measurable and worth real points. |
| Noise is `add_shot_noise` (**Poisson**, dose 200) **then** `add_detector_noise` (**Gaussian**, σ=5) | The noise is exactly **Poisson–Gaussian**. This is the single most exploitable fact in the entire problem — see the thesis below. |
| Search also gets **gamma**, vignette, per-row shear+jitter, barrel distortion, speckle, salt-and-pepper, charging streaks | All are monotone or low-frequency photometric nuisances. ZNCC on raw intensity is **not** gamma-invariant. |
| Beam PSF applied to **both** images at 1 nm/px *before* the ↓10 | `INTER_AREA` downscaling of the reference is the **physically exact** forward operator, not an approximation. We can prove it, not just assert it. |
| Mats (2600 nm) separated by strips (320 nm); each mat independently randomised; `boundary_bias=0.35` | Mis-locks are **within-mat lattice shifts**. ~65% of crops sit deep inside a uniform mat. |
| Line positions are a random walk `pos += pitch + N(0,1.5nm)`; widths jitter ±10% | Every cell carries a **unique fingerprint**; accumulated deviation over a 1000 nm template ≈ 5.8 nm ≈ 0.58 search px. Disambiguation is *provably* possible. |
| Contacts on an `(i+j)%2` checkerboard | The genuinely dangerous confusion is the **parity-preserving diagonal shift** (+1 word-line *and* +1 bit-line). Single-axis shifts break the checkerboard and are detectable. |
| DRAM pitches: word 64 nm = 6.4 search px, bit 96 nm = 9.6 search px | A mis-lock is ≥6.4 px off — outside the 5 px threshold. Mis-lock = hard binary failure. |
| Their generator has **no rotation and no scale variation**, but the PDF says 9:1–11:1 and 1–2° *will* be tested | Our generator must cover what theirs cannot. Decisive. |

### The bar

The official baseline is `INTER_AREA` resize over 5 fixed scales → `matchTemplate` argmax → `max_loc + tw/2`. No sub-pixel, no centre rule, no rotation, no ambiguity handling. Output is always `integer + 50.0`, so it carries a **~0.5 px quantization floor and structurally cannot score on the sub-pixel metric.**

### Scoring reality

| Bucket | Weight | Play |
|---|---|---|
| Localization / inference (accuracy + runtime) | **50%** | ML-optimal estimator, CPU, sub-pixel, provably near the information limit |
| Synthetic augmentation (realism, diversity, reproducibility, **literature-justified**) | **30%** | Our own generator; physics the starter omits, each cited |
| Failure analysis / explainability (esp. repeated-pattern ambiguity) | **10%** | Parity-shift analysis + conformal confidence + abstention |
| RGB optical extension | Bonus | Day 4 |
| Undefined | 10% | Polish, README, clean dry-run |

---

# The thesis

> ## We don't match images. We invert the microscope.

Template matching treats this as *find the most similar patch*. That is the wrong frame, and it is why the baseline plateaus. We know the **forward model** — a beam PSF, an area-average decimation, a known geometric warp, and a known Poisson–Gaussian noise process. Localization is therefore not a similarity search but a **maximum-likelihood inverse problem** with a handful of nuisance parameters.

Every design decision below follows from that single commitment. Nothing here is bolted on for novelty; each piece is what the ML framing *forces*.

| The forward model says… | …so the estimator must |
|---|---|
| Noise is Poisson then Gaussian, not additive iid | Apply the **Generalized Anscombe Transform** first. Only then is correlation the ML estimator. |
| Gamma, vignette and streaks are monotone / low-frequency photometric maps | Match on **phase congruency**, which is *provably* invariant to contrast and illumination. Eliminate the nuisance by construction, not by tuning. |
| The blur-then-decimate operator is known analytically | Apply it exactly, and **self-calibrate its residual per pair** at test time from radial power spectra. Zero-training test-time adaptation. |
| The lattice is identical in both images | Read **scale and rotation in closed form** from reciprocal-lattice geometry. Use periodicity as a *ruler*, not a nuisance. |
| The residual ambiguity is discrete and lattice-structured | Solve it as a **joint assignment** over candidates, not independent scoring. |
| The likelihood surface is smooth and differentiable near the optimum | Finish with **differentiable analysis-by-synthesis** — render the reference through the estimated acquisition operator and descend the Poisson–Gaussian NLL. |
| The estimator has a theoretical variance floor | Compute the **Cramér–Rao lower bound** and show we approach it. |
| Confidence should be a guarantee, not a vibe | Use **conformal prediction** for a distribution-free, finite-sample coverage guarantee. |

The one-line pitch:

> Everyone else treats the repeating pattern as the enemy. We use it as a ruler — the lattice gives us pose in closed form, and the *aperiodic* residual gives us identity. Then we stop matching and start inverting: because we know the physics of the acquisition, we recover the location by maximum likelihood, and we prove we are within a small factor of the information-theoretic limit.

---

## Deliverable 2 — `localize.py` (50%)

Tiered so that ambition can never sink the submission. **Tier A alone should beat every other team.**

### Tier A — the ML-optimal core (Days 1–2, must ship)

**A1. Generalized Anscombe Transform.** The sponsor's pipeline is literally `Poisson(dose·I)` followed by `+N(0,σ)`. The GAT (Mäkitalo & Foi, IEEE TIP 2013) is *designed* for exactly Poisson–Gaussian and maps it to approximately unit-variance additive Gaussian. After GAT, sum-of-squared-differences and ZNCC become the maximum-likelihood estimator; before it, they are not. At dose 200 the difference is real, not cosmetic.
*Intuition to say out loud: bright pixels are noisier than dark ones under shot noise, so plain correlation over-trusts the bright contacts. GAT equalises that. Five lines of numpy, measurable accuracy gain.*

**A2. Phase-congruency feature channel.** Kovesi's phase congruency from quadrature log-Gabor pairs is an illumination- and contrast-invariant measure of feature significance — invariant because it depends on local Fourier *phase* alignment, not amplitude. That kills the search image's gamma, vignette and dose mismatch **by construction**. Also run 3×3 median (salt-and-pepper) and per-row robust median subtraction (charging streaks are constant-per-row additive — exactly targeted).

**A3. Exact forward operator.** `cv2.resize(ref, INTER_AREA)`. Justify it: search = (canvas ⊛ PSF)↓10 area-average and reference = (crop ⊛ PSF) with the *same* PSF, so area-averaging is the exact operator. This is how we answer "account explicitly for the scale difference instead of relying on an accidental match" — with physics, not a resize call.

**A4. Per-pair blind self-calibration.** Estimate the residual PSF, effective gamma and noise floor *from the pair itself* by matching 1D radial power spectra of the downscaled reference against the search image. Test-time adaptation with **zero training and no data assumptions** — it self-corrects if the evaluator's generator differs from ours. This is our main insurance against distribution shift.

**A5. Lattice-as-a-ruler pose estimation.** Hann-window both images, take the 2D power spectrum, RANSAC-fit the dominant reciprocal-lattice peaks in each. Scale = |k_ref|/|k_search|; rotation = angle difference. **Closed form, no sweep**, covering the full 9:1–11:1 and ±2° envelope. Fallback chain for strip-dominated crops where lattice peaks are weak: log-polar Fourier–Mellin → coarse grid sweep. Never a single point of failure.

**A6. Top-K candidates, never argmax.** `matchTemplate(TM_CCOEFF_NORMED)` on the GAT+phase-congruency channels at the estimated pose. Keep K≈20 with NMS radius = 0.6 × lattice pitch (derived, not magic).

**A7. Periodic–aperiodic decomposition (PADM).** Build the periodic component by keeping only lattice harmonics in Fourier; residual `R = I − P` carries the random-walk fingerprint and the mat/strip boundaries. Re-score every candidate on `R`. **The lattice tells you where *within* a cell; the residual tells you *which* cell.**

**A8. Ambiguity index + the literal centre rule.**
```python
pai    = best / best_among_non_lattice_congruent
tied   = [c for c in cands if c.score >= best - tau]   # tau from spread of lattice-congruent scores
answer = min(tied, key=lambda c: dist(c.xy, search_centre))
```
Implement the spec's closest-to-centre rule literally and visibly — judges may test that branch. Never hard-code `tau`.

**A9. Sub-pixel.** `skimage.registration.phase_cross_correlation(upsample_factor=100)` (Guizar-Sicairos upsampled DFT — already in scikit-image), then `cv2.findTransformECC(MOTION_AFFINE)` on the 100×100 region. **Affine, not Euclidean**: the per-row shear and barrel distortion are affine to first order over 100 px.

### Tier B — the parts that make it provably good (Day 3)

**B1. Differentiable analysis-by-synthesis.** The endgame. Parameterise `(x, y, s, θ, shear, gain, gamma)`, render the reference through the estimated acquisition operator, and minimise the **Poisson–Gaussian negative log-likelihood** against the search patch by gradient descent (torch autograd, or `scipy.optimize` on 7 parameters — both are fast on a 100×100 patch). This is the Bayesian-optimal refinement and it drives error to the noise floor.
*Why it's honest: we can do this precisely because we built the generator and understand the physics. It is the natural conclusion of the thesis, not a trick.*

**B2. Cramér–Rao lower bound.** For a known template under Poisson noise, the CRLB on translation variance is `≈ σ²/Σ|∇I|²`. Compute it per pair and plot our achieved error against it.
**This is the highest-value slide in the deck.** It converts "our median error is 0.08 px" into "**our error is within 1.3× of the information-theoretic limit — no method can do substantially better on this data.**" No student team will do this, and a KLA/AMAT panel will recognise immediately what it means.

**B3. Conformal prediction confidence.** Instead of an uncalibrated score, output a **distribution-free radius `r` with finite-sample coverage guarantee**: `P(‖error‖ ≤ r) ≥ 1−α`. Split-conformal on a held-out calibration set, with the nonconformity score built from PAI, peak sharpness, residual score, ECC correlation and lattice-fit quality. ~50 lines, no training, rigorous.
*This directly satisfies "provide a repeatable score or confidence" — and does so with a guarantee rather than a heuristic. It is also what makes graceful abstention defensible.*

### Tier C — Day 4, all behind flags, each independently shippable

**C1. Lattice-aware transformer re-ranker.** SuperGlue's insight applies exactly: matching is a *joint assignment* problem, not independent scoring. A small attention model over the top-K candidates lets them compare against each other. The modern touch that fits this problem: **positional encoding in lattice coordinates** — encode each candidate's offset as integer `(m, n)` lattice steps plus a sub-cell residual, so the model sees the ambiguity structure directly instead of having to learn it from raw pixels. Hard negatives = **parity-preserving diagonal shifts**. `--no-rerank` must always work; `import torch` lazy inside try/except.

**C2. SOTA foundation-matcher comparison.** Run **RoMa v2 (2026)**, EfficientLoFTR and XFeat on our pairs and publish the numbers. They are trained on natural images and periodic texture is their known worst case — we expect them to fail badly, and quantifying that **preempts "why didn't you use a foundation model?" with data instead of assertion.** Cheap (a few hours) and one of the strongest slides available.

**C3–C5.** Robustness sweep beyond spec (8:1–12:1, ±5°, 2× noise); interactive drift demo (crosshair re-locks, confidence radius grows and the system says *"low confidence"* instead of lying); RGB optical extension (the scored bonus).

### CLI and engineering rules

```bash
python localize.py --reference ref.png --search search.png          # prints exactly: 312.42,489.07
python localize.py --manifest data/test/manifest.csv --out results/predictions.csv
python localize.py --input-dir data/test/ --out results/predictions.csv
```
Satisfies "process a pair **or** evaluator-provided batch without manual source-code changes". Optional `--json`, `--visualize`, `--no-rerank`, `--verbose`.

- Core deps: `numpy`, `opencv-python-headless`, `scipy`, `scikit-image`. `torch` lazy and **optional**.
- No network, no runtime download; weights committed, small, no Git LFS.
- Deterministic; nothing but the coordinate on stdout; all logs to stderr.
- Bad input → clear stderr error, nonzero exit. Target <300 ms/pair CPU.

---

## Deliverable 1 — `generate_dataset.py` + `src/synth/` (30%)

Our own generator, not a fork. Same physical skeleton as the sponsor's (so distributions overlap) plus what they omit.

**Physically ordered image formation** — say the order out loud; process engineers notice if noise precedes blur:

```
1. Vector layout       → DRAM 6F² folded-bitline / FinFET, at 1 nm/px
2. SE edge brightening → yield rises with local tilt   ← THE STARTER OMITS THIS
3. Charging shading    → low-order 2D polynomial field
4. Beam PSF            → Gaussian, σ = spot size, optional astigmatism
5. Geometry            → rotation 0–2°, scale 9:1–11:1  ← THE STARTER OMITS BOTH
6. Raster drift        → per-row shear + jitter
7. Barrel distortion
8. Shot noise          → Poisson(dose·I)
9. Detector noise      → Gaussian(0, σ_read)
10. Speckle / S&P / charging streaks / vignette / gamma
11. Quantise           → uint8
```
Steps 6–11 use **independent RNG streams** per acquisition — same clean scene, two separate captures.

### Five things ours does that the starter's cannot

1. **SE edge brightening.** The starter paints flat gray levels (`BACKGROUND=40, WORD_LINE=150, BIT_LINE=170, CONTACT=225`) and max-composites. Real SEM contrast is edge-driven — SE yield rises with local surface tilt. Model `I_edge = A·exp(−d²/2σ_e²)` on the signed distance field plus a directional detector-shadow term `B·max(0, ∇S·L̂)`. **The most defensible realism gain, and it is cited physics.**
2. **True rotation and scale.** The spec says both will be tested; the starter cannot produce either. We can validate against the stated robustness envelope; teams relying on the starter cannot.
3. **Fractional crop origins** via sub-pixel warp → **continuous GT**, not the starter's 0.1 px grid. This is what lets us claim sub-pixel accuracy honestly.
4. **Richer aperiodic content** — dummy rows, redundancy columns, sub-array boundaries, anomalous cells (0.1–1.0%).
5. **RGB optical mode** (Day 4) — the explicit scored bonus.

DRAM primary (maximises the ambiguity the problem is about), FinFET secondary; both reported.

### Output contract — freeze in hour one; it unblocks all three people

```
data/<split>/{reference,search}/00000.png   1000×1000 uint8
data/<split>/manifest.csv
data/<split>/meta/00000.json
```
`manifest.csv` is a **superset of the sponsor's columns** so their manifests load unchanged: `id, reference_path, search_path, gt_x, gt_y, gt_box_*, architecture, preset, scale_ratio, rotation_deg, beam_spot_size_nm, dose_*, detector_noise_sigma_*, shear_amplitude_px, drift_jitter_px, astigmatism_ratio, vignette_strength, gamma, barrel_distortion_k, charging_streak_*, speckle_sigma, salt_pepper_prob, edge_brightness_A, edge_sigma_nm, linewidth_bias_nm, corner_rounding_px, mat_size_nm, strip_width_nm, boundary_bias, ambiguity_level, seed`.

`ambiguity_level` ∈ {low, med, high} from residual energy and whether a strip is in view. **Stratifying results by it is a table judges rarely see from students.**

---

## Deliverable 3 — `evaluate.py` + results (10% + all credibility)

Spec requires ≥30 varied independent pairs. We run ~200 on ours + ~100 on the sponsor's.

Report Euclidean error mean/median/p95/**worst**; **pass@5, 4, 2, 1 px** plus sub-pixel; runtime per pair **with hardware, Python version and timing method**; stratified across noise, scale, rotation, position, architecture and `ambiguity_level`.

Five tables that separate us:
1. **Ablation** — baseline ZNCC → +GAT → +phase congruency → +lattice pose → +PADM → +sub-pixel → +ECC affine → +analysis-by-synthesis → +re-ranker.
2. **Cross-generator validation** — our matcher on *our* data and on the *sponsor's published generator's* data, side by side. Proves we did not overfit our own generator. Almost nobody will do this.
3. **Achieved error vs. Cramér–Rao bound.** The headline.
4. **Conformal coverage check** — empirical coverage vs. nominal 1−α, showing the guarantee holds.
5. **Lattice-error rate** — of the failures, what fraction landed on a parity-preserving lattice-equivalent position. Reporting *which kind* of error we make shows we understand this is a data-integrity problem, not an accuracy problem.

Plus **≥1 visualized failure case with root cause** (mandatory). Best candidate: a crop deep inside a uniform mat where the fingerprint is buried by dose-200 shot noise — show the correlation surface with the parity-preserving diagonal peaks.

Do **not** vendor the sponsor's code. Ship `scripts/fetch_reference_generator.sh` that clones the HF Space into a gitignored folder; attribute in the README.

---

---

# Repository, tracking and portability

Everything lives in `D:\semicon`. The folder must be **zip-and-go**: clone or unzip it on any machine, run one command, and get identical results. This is not housekeeping — the spec's own checklist has *"No proprietary data or hard-coded local paths"* and *"Submission was dry-run in a clean environment"*, and a script that fails on the evaluator's machine scores zero regardless of how good the method is.

### Full layout

```
D:\semicon\                        ← git repo root (git init on Day 0)
├── CLAUDE.md                      ← auto-loaded by every Claude Code instance on any machine
├── README.md                      ← the graded README: setup, commands, I/O, coordinate convention
├── LICENSE                        ← MIT
├── .gitignore  .gitattributes     ← .gitattributes is what makes Windows↔Linux safe
├── .editorconfig
├── requirements.txt               ← exact pinned versions
├── requirements-dev.txt           ← pytest, ruff, matplotlib
├── pyproject.toml                 ← ruff + pytest config, package metadata
├── Makefile  +  make.ps1          ← same task names on both shells
│
├── docs/
│   ├── PLAN.md                    ← THIS PLAN, copied in as step one. Source of truth.
│   ├── SPEC.md                    ← requirements extracted from the AMAT PDF + the 15-item checklist
│   ├── DECISIONS.md               ← ADR log: every non-obvious choice, dated, with the reason
│   ├── PROGRESS.md                ← gate tracker, updated at every gate by whoever hits it
│   ├── HANDOFF.md                 ← how to resume cold on a new machine in <10 minutes
│   ├── METHOD.md                  ← the technical writeup the PPT is generated from
│   └── REFERENCES.md
│
├── reference/                     ← the original AMAT PDF + extracted text, kept verbatim
│
├── generate_dataset.py   localize.py   evaluate.py
├── configs/            default.yaml  robustness.yaml  paths.yaml
├── src/
│   ├── synth/          layout_dram.py  layout_finfet.py  sem_model.py  noise.py  zones.py
│   └── driftlock/      preprocess.py  anscombe.py  phasecong.py  lattice.py  padm.py
│                       match.py  subpixel.py  synthesis.py  crlb.py  conformal.py
│                       rerank.py  io.py
├── model/              conformal_calib.json   reranker.pt (optional, small, committed)
├── data/
│   ├── bench/          30 committed pairs + manifest — the required validation evidence
│   └── (large splits regenerated by seed, gitignored)
├── results/            metrics.csv  predictions.csv  ablation.md  crlb.md
│                       figures/  failure_case/
├── tests/              test_determinism.py  test_cli.py  test_forward_model.py  test_geometry.py
├── scripts/
│   ├── smoke_test.sh  +  smoke_test.ps1
│   ├── verify_submission.py       ← automates the spec's 15-item checklist
│   ├── package_submission.py      ← emits dist/ in the spec's exact recommended layout
│   ├── fetch_reference_generator.sh
│   └── make_figures.py
└── dist/                          ← generated zip, gitignored
```

The spec *recommends* a `submission/` folder. We keep a clean working repo at root and have `scripts/package_submission.py` emit `dist/drift-lock-submission.zip` containing exactly the recommended tree. Best of both: professional repo for browsing judges, exact required shape for the graded artifact.

### Portability rules — enforced, not aspirational

- **No absolute paths anywhere.** All paths derive from `Path(__file__).resolve().parents[n]` or come from CLI args / `configs/paths.yaml`. `scripts/verify_submission.py` greps for `C:\`, `D:\` and `/home/` and **fails the build** if it finds any. This is a literal spec checklist item.
- **`pathlib` only**, never string concatenation or `os.sep` assumptions.
- **`.gitattributes` with `* text=auto eol=lf` and `*.png *.pptx *.pdf binary`.** Without this, Windows CRLF conversion silently corrupts committed PNGs and breaks byte-identical reproducibility across machines.
- **Standardise on Python 3.11.** ⚠️ This machine has **3.14.3**, where wheel availability for `torch` and parts of the scientific stack is still patchy. Do not discover this on Day 4. Every member creates `.venv` on 3.11, and the README states the version.
- **`opencv-python-headless`**, never `opencv-python` — the evaluator's box may have no display libraries.
- **Determinism**: single seeded `np.random.Generator` threaded through, `PYTHONHASHSEED=0`, `cv2.setNumThreads(1)` for reproducible timing. `tests/test_determinism.py` asserts same seed → byte-identical images and identical predictions.
- **Data policy**: the 30-pair bench set is committed (it *is* the required validation evidence). Larger splits are **regenerated from seeds** and gitignored. Say this out loud in the deck — *"our dataset is reproducible from seeds rather than shipped as opaque blobs"* is a reproducibility strength, not a shortcut.

### Tracking — how 3 people and 3 Claude Code instances stay in sync

- **`CLAUDE.md` at root** is the highest-leverage file in the repo. Every Claude Code instance on every machine loads it automatically, so all three get the same context without anyone re-explaining. It holds: the thesis, the sponsor-generator facts table, the manifest schema, CLI contracts, ownership boundaries, coding conventions, and the current gate. **Written on Day 0, before any code.**
- **`docs/PROGRESS.md`** — gate checklist with owner and timestamp. Updated by whoever clears a gate, not retroactively.
- **`docs/DECISIONS.md`** — one short ADR per non-obvious call (why GAT, why affine ECC not Euclidean, why we rejected foundation matchers). This *is* the raw material for the PPT's method slides and the failure-analysis section. Writing it as you go costs minutes; reconstructing it on Day 4 costs hours.
- **Git**: `main` + one short-lived branch per person, merged daily. **Ownership maps to disjoint directories by design** — A owns `src/synth/` + `generate_dataset.py`, B owns `src/driftlock/` + `localize.py`, C owns `evaluate.py` + `results/` + `docs/` + the deck — so merge conflicts are structurally rare. That directory split is the reason the parallel schedule works.
- **Commit discipline**: conventional-commit prefixes, and every commit that changes results also updates `results/`. Never a claim in the deck without a commit behind it.

### One-command bootstrap on any machine

```bash
git clone <repo> && cd semicon
make setup        # venv + pinned deps          (make.ps1 setup on Windows)
make data         # regenerate datasets by seed
make bench        # full evaluation → results/
make verify       # spec checklist + no-abs-paths + determinism
make package      # dist/drift-lock-submission.zip
```

---

---

# Correctness rules — no hallucinations, no unverified claims

Three people and three Claude Code instances producing code, prose and citations under time pressure is exactly the setup that generates confident, plausible, wrong output. In front of a KLA/AMAT panel, one fabricated citation or one number that doesn't match the CSV destroys credibility for the whole submission — far more damage than the missing content would have caused. These rules are enforced by tooling wherever possible, because rules that depend on discipline at 3 a.m. on Day 4 are not rules.

### R1 — No citation nobody opened
`docs/REFERENCES.md` is a table with mandatory columns: **Claim it supports · Full citation · DOI/URL · Verified by (initials) · Date verified**. A row without all five is not a citation and must not appear in the PPT.
- Never cite from memory. Open the DOI, confirm the title/authors/venue/year, note in one line what the paper actually says.
- If a source cannot be verified, **delete the claim or restate it as our own reasoning.** "We chose X because Y" is honest; a fake citation is not.
- `scripts/verify_submission.py` extracts every bracketed citation from the deck and `METHOD.md` and **fails** if it is not a complete row in `REFERENCES.md`.

### R2 — No number typed by hand, ever
Every metric, table and figure is emitted by `evaluate.py` / `make_figures.py` into `results/`. The deck reads from there.
- `verify_submission.py` parses the `.pptx` text, pulls every numeric literal, and checks it appears in `results/*.csv` or `results/*.md`. Unmatched numbers **fail the build**.
- A stale number from an earlier run is the most likely failure here — regenerate `results/` and re-run the check as the last action before submitting.

### R3 — Verify the foundations empirically before building on them
This entire plan rests on **my reading of the sponsor's source code.** That reading could be wrong, and their evaluation data may differ from their published generator. Treat every fact in the table at the top as a **hypothesis until B confirms it on real generated pairs.**

**Day 1, before any algorithm work, B empirically confirms:** the 100×100 footprint; that `gt = (x0/10 + 50, y0/10 + 50)`; that the noise really is Poisson-then-Gaussian; that `INTER_AREA` downscaling actually aligns the two domains. Record each as confirmed/refuted in `docs/DECISIONS.md`. **If a fact is refuted, the plan changes — say so immediately rather than building on it.**

### R4 — The conventions that silently produce plausible wrong answers
The top-scoring failure mode in this problem is not a bad match; it is a **convention bug that passes every symmetric test.**
- **x/y swap.** `cv2` indexes `[row, col]` = `[y, x]`; the spec wants `(x, y)` with x rightward, y downward, top-left origin. `tests/test_geometry.py` must use a **deliberately asymmetric** case (e.g. GT at `(300, 700)`) — a symmetric test cannot catch a swap.
- **Centre vs. corner, and the half-pixel.** Fix the convention once in `io.py`, document it in `CLAUDE.md`, and test it against a hand-computed case.
- **Off-by-one in the 100×100 box.** Assert `gt_centre == gt_box_origin + 50` on real manifests.
- Every one of these gets a unit test with a hand-derived expected value — not a value copied from what the code currently outputs. **A test written by running the code and pasting the output tests nothing.**

### R5 — Held-out discipline
- Calibration seeds, training seeds and evaluation seeds are **disjoint and recorded in the manifest.** The conformal calibration set and the re-ranker training set never intersect the reported benchmark.
- Never tune a threshold on the numbers being reported. If a threshold gets tuned on the benchmark, that benchmark is dead — regenerate a fresh one with new seeds.

### R6 — Claims must be hedged to the evidence
Before any sentence goes in the deck, ask what would have to be true, and whether we ran it.
- "Sub-pixel accurate" requires continuous GT — we have it only because our generator uses fractional origins. On the sponsor's 0.1 px grid, say so.
- "Faster than X" / "outperforms X" requires having actually **run** X on **our** data. If RoMa v2 was not run, the comparison slide does not exist.
- "Near the information-theoretic limit" is licensed only by the computed CRLB, and only on the data where it was computed.
- Unmeasured runtime claims are banned. State hardware, Python version and timing method every time, as the spec requires.

### R7 — No API, function or parameter used from memory
Claude Code confidently invents plausible signatures. Anything imported must be exercised by a test or a real run before it reaches `main`.
- Check signatures against the **installed** version, not recollection — pinned versions exist for this reason.
- `make verify` runs the full test suite plus both smoke tests. Red build → nothing merges.

### R8 — Independent red-team pass, Day 3
**C re-derives B's headline numbers from raw outputs without looking at B's summary**, and re-runs one figure end-to-end. A owns the same check for the physics claims in the generator. Anything that does not reproduce gets pulled from the deck rather than explained away.

### R9 — Report what actually happened
If a component underperforms, it goes in the ablation table as a negative result with its number. A method that we tried and dropped is a **strength** in the failure-analysis bucket, which is explicitly worth 10%. Honest negative results read as research maturity; silently dropped experiments read as cherry-picking if a judge asks the obvious question.

---

## Schedule — 4 days, 3 people

**A = Data/Physics · B = Algorithm · C = Eval/Packaging/Deck.** Assign to taste; keep fixed.

### Day 0 — tonight, ~2h, all three together
This session is what makes the parallel schedule possible. Do not skip it to "start coding".
- `git init` in `D:\semicon`; scaffold the full layout above; `.gitignore`, `.gitattributes`, `LICENSE`, `pyproject.toml`, `Makefile` + `make.ps1`; push to a private GitHub repo.
- **Write `CLAUDE.md` first**, before any code. Every Claude Code instance on every machine inherits the same context from it.
- Copy this plan to `docs/PLAN.md`; write `docs/SPEC.md` from the AMAT PDF; move the PDF into `reference/`.
- Freeze the manifest schema and all three CLI signatures **in writing** in `CLAUDE.md`.
- All three create `.venv` **on Python 3.11** and confirm `make setup` works on their own machine. Catch environment drift now, not on Day 4.
- Everyone clones the HF Space and generates ~50 pairs. **B has data on day one and is never blocked on A.**
- Agree the freeze gate: **core complete end of Day 3, no exceptions.**

### Day 1
- **A** — DRAM layout at 1 nm/px, zoning, SE edge-brightening, PSF, Poisson + detector noise. First 50 pairs + manifest.
- **B** — **First: R3 empirical confirmation of the sponsor-generator facts** (100×100 footprint, GT convention, Poisson-then-Gaussian, `INTER_AREA` alignment), logged in `DECISIONS.md`. Then reproduce the baseline, then **A1–A3, A6, A8**, with `tests/test_geometry.py` (asymmetric case) written *before* the matcher. **Gate: ≥90% pass@5px on sponsor data by EOD.** If that gate fails, everything else is premature.
- **C** — `evaluate.py` with all required metrics, manifest loader, plots, `smoke_test.sh`, README skeleton, `requirements.txt`, deck skeleton on the sponsor's 12-slide structure.

### Day 2
- **A** — Rotation + scale, FinFET, fractional origins, aperiodic content, full metadata/seeding. Full 200-pair set.
- **B** — **A4, A5, A7, A9.** **Gate: median error < 0.5 px.**
- **C** — Ablation infrastructure, cross-generator run, stratified tables, figures. Slides written against numbers that already exist.

### Day 3 — **CORE FREEZE 18:00**
- **A** — Citations into `REFERENCES.md`, per-parameter physical justification, generator README.
- **B** — **B1 analysis-by-synthesis, B2 CRLB, B3 conformal**, failure-case visualization, runtime profiling, determinism check.
- **C** — Full 300-pair run, all tables/plots final, README with exact commands, `pip freeze`, **clean-VM dry run**, deck complete.
- **All three — R8 red-team pass.** C re-derives B's headline numbers from raw outputs without reading B's summary; A re-checks the generator's physics claims against their citations; everyone runs `make verify`. Anything that does not reproduce is **pulled from the deck**, not explained away.
- **18:00: the default code path is frozen.** A submittable package exists from this moment.

### Day 4 — stretch only, all flag-gated
Priority order, stop when time runs out: **C1** re-ranker → **C2** SOTA comparison → **C3** robustness sweep → **C4** demo + 60–90 s video → **C5** RGB bonus.

Final 2 hours: fresh-clone dry run, verify every PPT claim against `results/`. **Submit Day 5 morning with buffer intact — not at the deadline.**

---

## Risk register

| Risk | Mitigation |
|---|---|
| Ambition sinks the core | Tier A ships by Day 2; freeze at Day 3 18:00; Tiers B/C additive and flag-gated. |
| Phase congruency / GAT underperform plain ZNCC | Both are ablation rows, not commitments. Keep whichever wins on data. Decide by Day 2 EOD. |
| Analysis-by-synthesis fails to converge | It only ever *refines* an already-good A9 estimate; reject the update if NLL does not improve. Cannot make things worse. |
| Overfitting to our own generator | Cross-generator validation is a **Day 2** deliverable, not a Day 4 nice-to-have. Plus A4 self-calibration adapts per pair. |
| Eval data has rotation/scale we never tested | Our generator produces both from Day 2; theirs cannot. This is precisely why we build our own. |
| Script fails on the evaluator's machine | Four deps, CPU-only, lazy torch, weights in-repo, no network, `smoke_test.sh` on a clean VM. This is what eliminates teams and is the cheapest thing to fix. |
| PPT claims drift from results | C owns the numbers; every table generated by `evaluate.py`, never typed by hand. |

---

## References — verified real before writing this plan

- **Mäkitalo & Foi**, *Optimal Inversion of the Generalized Anscombe Transformation for Poisson-Gaussian Noise*, **IEEE TIP 22(1):91–103, 2013** — our noise model is literally Poisson-then-Gaussian; this is the matched tool.
- **Guizar-Sicairos, Thurman & Fienup**, *Efficient subpixel image registration algorithms*, **Optics Letters 33(2):156–158, 2008**, DOI `10.1364/OL.33.000156` — implemented as `skimage.registration.phase_cross_correlation`.
- **Kovesi**, *Phase congruency: A low-level image invariant* — illumination- and contrast-invariant feature measure; the principled answer to gamma and vignette.
- **Villarrubia, Ritchie & Lowney** (NIST), *Monte Carlo modeling of secondary electron imaging in three dimensions* — SE yield vs. surface tilt, the edge-brightening physics the starter omits.
- **RoMa v2**, *Harder Better Faster Denser Feature Matching*, arXiv 2511.15706 (2026) — current SOTA dense matcher, for the comparison-and-rejection slide.
- **US Patent 7,349,232**, *6F2 DRAM cell design with 3F-pitch folded digitline sense amplifier* — citing a patent shows we looked where the industry actually publishes.

To verify before citing (categories, not invented citations): Lewis, *Fast Normalized Cross-Correlation* (VI 1995); Evangelidis & Psarakis, TPAMI 2008 (= `cv2.findTransformECC`); Reddy & Chatterji, IEEE TIP 1996 (Fourier–Mellin fallback); Moisan, *Periodic Plus Smooth Image Decomposition*, JMIV 2011 (ancestor of PADM — cite it and state how ours differs); Reimer, *Scanning Electron Microscopy*, Springer; Sarnoff/Sarkar split-conformal regression (Vovk/Lei) for the conformal guarantee; Li et al., *Monte Carlo Simulation of CD-SEM Images*, Scanning 2013.

**Rule: nobody cites anything they have not opened.** The 30% bucket says "literature-based justification"; a fabricated citation in front of a KLA/AMAT panel is fatal.

---

## Verification

The real test is not "does it work on my laptop" — it is **unzip on a machine that has never seen this project and get identical numbers.** Run this on a different machine (or a fresh container) at the end of Day 3 and again on Day 4:

```bash
git clone <repo> && cd semicon
python -m venv .venv && source .venv/bin/activate     # Python 3.11
pip install -r requirements.txt
python generate_dataset.py --num-samples 30 --split test --seed 1234 --output-dir data
python localize.py --reference data/test/reference/00000.png --search data/test/search/00000.png
python localize.py --manifest data/test/manifest.csv --out results/predictions.csv
python evaluate.py --manifest data/test/manifest.csv --predictions results/predictions.csv --out results/
python scripts/verify_submission.py
```

Correctness and packaging:
1. Single-pair mode prints **exactly one line**, `x,y`, nothing else on stdout; all logs to stderr.
2. Batch mode runs a manifest end-to-end with **zero source edits**.
3. `pip uninstall torch` → everything above still passes.
4. Same seed twice, **on two different machines and OSes** → byte-identical images and identical predictions.
5. `scripts/verify_submission.py` finds **no absolute paths**, and walks all 15 boxes of the PDF §9 checklist.
6. `make package` → unzip `dist/` into an empty directory on a clean box → the commands above still run.

Results quality:
7. `results/metrics.csv` has pass@5/4/2/1 px, sub-pixel rate, mean/median/p95/worst, runtime p50/p95, with hardware and Python version recorded.
8. Empirical conformal coverage ≥ nominal on held-out data.
9. Achieved error plotted against the CRLB.
10. Cross-generator table populated (ours **and** the sponsor's generator).
11. At least one visualized failure case with root cause.
12. **Every number in the PPT is traceable to a file in `results/`** — C verifies this line by line before submission.
