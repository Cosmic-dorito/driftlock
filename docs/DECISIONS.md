# Decision log (ADRs)

One short record per non-obvious choice: what we decided, why, and what would change our mind.
Written **as we go** — this is the raw material for the PPT's method slides and the failure-analysis
section. Reconstructing it on Day 4 costs hours; writing it now costs minutes.

Format: `ADR-NNNN · date · status · decision · why · what would change our mind`.

---

## ADR-0001 · 2026-08-11 · accepted · Clean repo at root, submission tree emitted on demand

**Decision.** The git repo root is the working project (with `docs/`, `tests/`, `scripts/`).
`scripts/package_submission.py` emits `dist/drift-lock-submission.zip` containing exactly the folder
tree the sponsor recommends (`submission/` with `solution_presentation.pptx`, `README.md`,
`requirements.txt`, `generate_dataset.py`, `localize.py`, `configs/`, `src/`, `model/`, `results/`,
`references/`).

**Why.** The sponsor's layout is *recommended*, not mandatory, and it has no room for a decision log,
tests or tooling. Judges who browse the GitHub repo should see a professional project; the graded
artifact should have exactly the required shape. This gets both without duplicating code.

**What would change our mind.** If the organizers publish a hard requirement that the repository root
itself must be `submission/`, we restructure — the packaging script already proves we can produce it.

---

## ADR-0002 · 2026-08-11 · accepted · Standardize on Python 3.14, not 3.11

**Decision.** The team targets **Python 3.14** with pinned dependencies.

**Why.** The original plan recommended 3.11 out of caution about wheel availability on 3.14. That
caution was **wrong and was corrected by testing rather than assumption** (rule R7). On this machine
Python 3.14.3 resolves the entire stack from `cp314` wheels: `scikit-image` 0.26.0,
`opencv-python-headless`, `numpy` 2.4.4, `scipy` 1.18.0, and `torch` 2.12.1+cpu is already installed.
Standardizing on the interpreter that is actually present removes a setup step for three people and
an install risk on Day 0.

**What would change our mind.** Any dependency we later need that lacks a `cp314` wheel. The
`requires-python` floor stays at `>=3.11` so the code remains runnable on an evaluator's older
interpreter — we target 3.14 but do not *require* it.

**Follow-up.** The exact OpenCV major version is settled separately in ADR-0003.

---

## ADR-0003 · 2026-08-11 · accepted · Pin OpenCV 5.0.0.93 — verified, no downgrade needed

**Decision.** Pin `opencv-python-headless==5.0.0.93`. No need to fall back to the 4.x line.

**Why it mattered.** `pip` resolves OpenCV to **5.x** on Python 3.14, a major version bump, and we
depend on `matchTemplate`, `TM_CCOEFF_NORMED`, `findTransformECC` + `MOTION_AFFINE`, `INTER_AREA`
and `remap`. Rule R7 forbids trusting an API from memory, so we tested rather than assumed.

**Evidence (2026-08-11, OpenCV 5.0.0.93 / Python 3.14.3).**
- All 22 required symbols present.
- `minMaxLoc` still returns **`(x, y)`**, not `(row, col)` — verified with an asymmetric template
  origin `(x=60, y=40)`, since a symmetric case cannot detect a swap.
- `findTransformECC` recovers a known sub-pixel translation to **0.055 px** (`MOTION_TRANSLATION`)
  and **0.037 px** (`MOTION_AFFINE`) on band-limited data. Step A9 is sound.

All of the above is now locked in `tests/test_deps_api.py`, so environment drift fails a test
instead of surfacing as a mysterious accuracy regression.

**Note on benchmarking sub-pixel methods.** Our first measurement used white noise as the test image
and made ECC look 7× worse (0.26 px). Bilinear/bicubic warping of white noise aliases badly. Real
SEM frames are band-limited by the beam PSF, so **all sub-pixel benchmarks must use band-limited
test signals** or they will understate accuracy.

---

## ADR-0009 · 2026-08-11 · accepted · `phase_cross_correlation` must use `normalization=None`

**Decision.** Every call to `skimage.registration.phase_cross_correlation` in this codebase passes
**`normalization=None`**. The library default is `'phase'` and it is wrong for our data.

**Why.** Phase normalization whitens the spectrum by dividing by magnitude. On a strongly
band-limited image the high-frequency magnitudes are ≈0, so that division amplifies pure numerical
noise and swamps the true correlation peak — it silently returns approximately **zero shift**.

**Evidence (2026-08-11), true displacement 2.86 px, `upsample_factor=100`:**

| blur σ | `normalization='phase'` | `normalization=None` |
|---|---|---|
| 0.0 | 0.18 px | 0.16 px |
| 1.0 | 0.09 px | **0.02 px** |
| 3.0 | **2.80 px — fails** | 0.12 px |
| 6.0 | **2.84 px — fails** | 0.61 px |

**Why this is not hypothetical.** Our search images are blurred by the beam PSF and then
area-downsampled; the reference downscaled to a 100×100 template is smoother still. Left
undiscovered, this would have surfaced on Day 2 as "sub-pixel refinement makes results worse" and
cost hours to trace.

**What would change our mind.** If scikit-image changes the phase-normalization implementation.
`tests/test_deps_api.py` asserts the failure mode still exists, so an upstream fix will fail that
test loudly rather than silently — at which point re-benchmark both settings before touching this.

**Caveat to carry forward.** At blur σ=6 even `normalization=None` degrades to 0.61 px. Sub-pixel
accuracy is blur-dependent, so B should measure it on real generated pairs (Gate 2) rather than
assuming the 0.02 px best case generalises.

---

## ADR-0004 · 2026-08-11 · accepted · Write our own generator; cross-validate on the sponsor's

**Decision.** Build our generator from scratch (own code, own physics), **and** additionally evaluate
our matcher on data produced by the sponsor's published generator. Do not vendor their code; fetch it
into gitignored `third_party/` and attribute it.

**Why.** Synthetic augmentation is **30%** of the score, judged on realism, diversity, reproducibility
and literature-based justification — a fork reads as derivative in exactly the bucket where
originality is graded. Meanwhile, evaluating on *their* generator is the only honest evidence that we
have not overfit to our own data distribution. Their generator also cannot produce rotation or scale
variation, both of which the spec says will be tested, so ours must cover what theirs cannot.

**What would change our mind.** If the organizers state that the evaluation set comes verbatim from
the published generator, matching its distribution becomes more valuable than originality — but we
would still keep our own for the rotation/scale envelope.

---

## ADR-0005 · 2026-08-11 · accepted · DRAM primary, FinFET secondary

**Decision.** Lead with DRAM; also generate and report FinFET.

**Why.** Both are judged equally, but a DRAM cell array is periodic in **two** directions, which
maximises the periodic ambiguity the problem statement is actually about. FinFET top-down is largely
periodic in one direction and partly disambiguates itself. Solving the harder case implies the
easier. FinFET costs little extra because the rendering path is shared, and it buys diversity points
in the 30% bucket.

---

## ADR-0006 · 2026-08-11 · accepted · Deterministic coordinate, learning in the decision layer

**Decision.** The coordinate itself is produced by a deterministic estimator. Learned components are
confined to (a) confidence calibration and (b) re-ranking ambiguous candidates, and both are optional
at runtime. `torch` is lazily imported; `pip uninstall torch` must leave everything working.

**Why.** The 50% bucket rewards accuracy *and* runtime, and a deterministic CPU estimator wins both
without a GPU, a download, or a weights-loading failure mode on the evaluator's machine. An
inspection tool also cannot accept a stochastic answer to "where am I?". Learning genuinely adds
value in the decision layer, where a wrong answer is recoverable.

**What would change our mind.** If the deterministic path plateaus above the 1 px threshold on hard
ambiguous cases, the re-ranker moves from optional to core — but it stays behind a flag.

---

## ADR-0007 · 2026-08-11 · accepted · Coordinate conversion happens in exactly one place

**Decision.** All `(row, col) ↔ (x, y)` conversion lives in `src/driftlock/io.py`. No other module
converts. Geometry tests use a deliberately asymmetric ground truth.

**Why.** `cv2`/numpy index `[y, x]`; the spec wants `(x, y)`. An x/y swap is the single most likely
bug to silently produce plausible wrong answers, and a symmetric test case cannot detect it. One
conversion site means one place to test and one place to be wrong.

---

## ADR-0008 · 2026-08-11 · accepted · Commit the bench set, regenerate everything else from seeds

**Decision.** `data/bench/` (the ≥30-pair validation set the spec requires) is committed. All larger
splits are regenerated from recorded seeds via `make data` and are gitignored.

**Why.** The bench set *is* the required evidence and must travel with the submission. Committing
hundreds of megabytes of PNGs would make the repo hostile to clone and adds nothing — the generator
is deterministic, so seeds reproduce the data exactly. "Reproducible from seeds rather than shipped
as opaque blobs" is a reproducibility strength worth stating in the deck.

**Depends on.** `.gitattributes` marking `*.png binary`; without it Windows CRLF conversion corrupts
committed PNGs and silently breaks the byte-identical reproducibility claim.

---

# Hypothesis verification log (rule R3)

The facts in `CLAUDE.md` about the sponsor's generator were derived by **reading its source code**,
not by running it. Each is a hypothesis until confirmed on real generated pairs. **B owns this, Day 1,
before any algorithm work.** If one is refuted, say so immediately — the plan changes.

| ID | Hypothesis | Status | Verified by / date | Evidence |
|---|---|---|---|---|
| H1 | Reference footprint in search image is exactly 100×100 px | unverified | | |
| H2 | `gt = (x0/10 + 50, y0/10 + 50)`, GT on a 0.1 px grid | unverified | | |
| H3 | Noise is Poisson (shot) then Gaussian (detector), in that order | unverified | | |
| H4 | Same PSF on both images before ↓10, so `INTER_AREA` is the exact forward operator | unverified | | |
| H5 | Search additionally gets gamma, vignette, shear+jitter, barrel, speckle, S&P, streaks | unverified | | |
| H6 | Mats 2600 nm separated by 320 nm strips, independently randomised, `boundary_bias=0.35` | unverified | | |
| H7 | Line positions are a random walk → every cell has a unique fingerprint | unverified | | |
| H8 | Contacts on `(i+j)%2` checkerboard → dangerous confusion is the parity-preserving diagonal shift | unverified | | |
| H9 | Their generator has no rotation and no scale variation | unverified | | |
