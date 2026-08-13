# HANDOFF — cold start on a new machine

## ⏩ RESUME HERE — state as of 13 Aug 2026

**The submission is COMPLETE, VERIFIED and PACKAGED.** Everything below is optional improvement
work. If time runs out right now, ship what is in `dist/`.

* `scripts/verify_submission.py --strict` → **17 passed, 0 failed, 0 pending**
* 36 tests pass · ruff clean · `dist/drift-lock-submission.zip` builds and reproduces bit-identically
  from a clean extract
* Deadline **16 Aug 2026**

### Current measured results (generated into `docs/RESULTS.md` from `results/`)

| Split | mis-lock | median px | pass@1px | pass@0.5px | p50 |
|---|---|---|---|---|---|
| sponsor (40) | 22.5% | 0.275 | 75.0% | 70.0% | 431 ms |
| bench (30, ours) | 16.7% | 0.337 | 76.7% | 63.3% | 413 ms |
| holdout FinFET (30) | 13.3% | 0.201 | 83.3% | 66.7% | 423 ms |

Baselines: 25.0 / 76.7 / 90.0 % mis-lock. Aggregate **18/100 = 18.0%** (was 22.0%).

### Shipped configuration (`localize.py::build_config`)

```python
PipelineConfig(label="driftlock", subpixel=True, drift_correction=True,
               pose_search=True, top_k=10, candidate_refit=True,
               refit_steps=5, refit_scale_span=0.03, refit_rotation_span=1.5,
               refit_screen_steps=2, refit_screen_top_n=10)
```

Changed 13 Aug — the wide dense refit is now screened, which made it both **cheaper and more
accurate** than the unscreened version. See ADR-0025 and FINDINGS §23. The §21d accuracy/runtime
frontier no longer exists in the form it was written.

### 🎯 THE NEXT ACTION — nothing is queued; pick from below

The previously-recorded next action (hoist box-integration out of the refit's rotation loop) is
**done**: bit-identical, 850 → 616 ms, and it turned out to address only 6% of the cost. Profiling
then found the real one — 60 candidates × 25 poses = 1500 correlations/pair — and screening it
gave 18.0% held-out at 427 ms. Full story in FINDINGS §23.

**The submission is in a better state than it has ever been and is complete.**

**14 Aug: the two most promising remaining knobs were swept and both are flat.** `top_k` ∈
{10, 15, 20, 30} all give 18.0% held-out (5 gives 19.0%); `top_n` ∈ {6, 10, 15, 20} all give 18.0%.
This configuration sits at a local optimum in its own parameters — further accuracy will not come
from tuning them (FINDINGS §23g). Also settled: the screen's mechanism is *not* better
initialisation (that explanation was published, then measured and refuted — §23f).

Remaining ideas, in rough order of expected value:

1. **Recall is the cap, and it is now a reported metric.** The true candidate is absent from the
   pool entirely on 2.5 / 10.0 / 3.3% of pairs (sponsor / bench / FinFET) and is lost at the screen
   on 10.0 / 13.3 / 10.0%. bench is the outlier worth understanding: 16.7% mis-lock against 10%
   irrecoverable means most of its failures are *already lost before selection runs*, which is a
   different problem from the one six re-rankers failed at.
2. **Runtime, not accuracy.** ~390-430 ms depending on the run; nothing here risks accuracy: the refit window is already
   a local ROI (template + 2×7 px), but the ~1000 remaining per-pair `matchTemplate` calls are
   small and overhead-dominated, so batching them is the open lever. Do not reach for FFT without
   benchmarking — the windows are 114×114 and setup cost may exceed the arithmetic.
3. Determinism test (PROGRESS 3.8), still outstanding.
4. RGB optical extension — the explicit scored bonus, never started.

**Do not retry:** multi-basin pose refinement (§22, 26.0%), pose interpolation (§21c, 27.0%),
pose-regime routing (§21a), pose-excursion penalty (§20a), or any seventh scoring criterion
(ADR-0024). All have been proposed again by external review since being measured and refuted.

Whatever is next: validate on **all four** splits (dev, sponsor, bench, finfet). A stage checked on
a convenient subset has reversed a conclusion twice here (ADR-0012, ADR-0021).

### What NOT to try again (all measured, all recorded)

**Six re-ranking criteria, all failed** — PADM, coarse consensus, max-likelihood, refit-*gain*,
lattice-phase/gradient-orientation, residual tie-break. See ADR-0024. The rule:

> Every attempt to re-rank by a NEW criterion failed. The only stage that worked re-scores by the
> SAME criterion at a better geometry.

**Three shortcuts to get dense-grid accuracy from a coarse grid, all failed** — best-sample (26.0%),
parabola interpolation (27.0%), multi-basin retention (26.0%), against dense sampling's 20.0%. See
FINDINGS §22:

> You cannot reconstruct an optimum from samples that do not resolve it.

**Also refuted:** pose-regime routing (best-pose-only is 30.0% vs 20.0% merged), pose-excursion
penalty (no gain at any setting), centre rule as a default (the benchmark samples targets uniformly,
so the deployment prior it needs is absent — ADR-0021).

**Also measured and settled (13 Aug):** widening the refit span beyond ±3%/±1.5° does not help
(±5%/±2° is 19.0% against 18.0%); sampling it denser than 5 steps does not help (7 steps is 19.0%
and 603 ms); narrowing to ±2%/±1° does not help (19.0%). The screen's `top_n` is flat over
{6, 10, 15, 20} on accuracy — chosen at 10 on retained recall, not on the tie. See FINDINGS §23d.

### Housekeeping notes

* Runtime numbers must come from `scripts/benchmark_runtime.py` (interleaves splits, discards
  warm-up). Measured inside an accuracy run, this machine's thermal drift lands on whichever split
  runs last — it produced 1228/1190/354 ms for identical code in one batch.
* `docs/RESULTS.md` and `README.md` results blocks are **generated** by
  `scripts/make_results_doc.py`. Never hand-edit them; the verifier fails the build if they go stale.
* After any change: `make test`, `scripts/make_results_doc.py`, `scripts/make_deck.py`,
  `scripts/verify_submission.py --strict`, `scripts/package_submission.py`.
* Open user actions: no GitHub remote configured; git identity is repo-local "DriftLock Team".

---


Goal: someone who has never seen this project (or you, on a different laptop, at 2 a.m.) gets from
zero to a working environment and correct output in **under ten minutes**.

---

## 1. Get the code and environment

```bash
git clone <repo-url> semicon
cd semicon
make setup                 # Windows PowerShell: .\make.ps1 setup
```

`make setup` creates `.venv` at the repo root and installs the pinned dependencies from
`requirements.txt`. Python **3.14** is what the team targets (ADR-0002); the code declares
`requires-python = ">=3.11"` so an older interpreter also works.

Activate it:

```bash
source .venv/Scripts/activate     # Git Bash on Windows
source .venv/bin/activate         # Linux / macOS
.\.venv\Scripts\Activate.ps1      # PowerShell
```

## 2. Prove it works

```bash
make test        # unit tests, including the asymmetric geometry test
make verify      # spec checklist, no-absolute-paths scan, determinism check
```

Both green means the environment is sound. If `make verify` complains about absolute paths, someone
hard-coded a `C:\` or `/home/` path — that is a literal item on the sponsor's grading checklist, so
fix it rather than skipping the check.

## 3. Read yourself in — in this order

| Read | For |
|---|---|
| `CLAUDE.md` | The thesis, the frozen contracts, the correctness rules. **Start here.** |
| `docs/PROGRESS.md` | What is done, what is next, who owns it, what is blocked |
| `docs/DECISIONS.md` | Why things are the way they are, and the H1–H9 verification log |
| `docs/SPEC.md` | What the sponsor actually requires (extraction from the PDF) |
| `docs/PLAN.md` | The full approved plan, including the day-by-day schedule |
| `docs/METHOD.md` | The technical writeup the deck is generated from |

If you are a Claude Code instance: `CLAUDE.md` loads automatically. Read `docs/PROGRESS.md` next to
find the current gate before doing anything.

## 4. Get data

The committed `data/bench/` set (the ≥30 pairs the spec requires) ships with the repo. Everything
larger is regenerated from recorded seeds — the generator is deterministic, so this reproduces the
exact same images:

```bash
make data
```

To also pull the sponsor's published generator for cross-generator validation (fetched into
gitignored `third_party/`, never vendored):

```bash
bash scripts/fetch_reference_generator.sh
```

## 5. Run something end to end

```bash
# Single pair — prints exactly one line: "312.42,489.07"
python localize.py --reference data/bench/reference/00000.png --search data/bench/search/00000.png

# Batch over a manifest, then score it
python localize.py --manifest data/bench/manifest.csv --out results/predictions.csv
python evaluate.py --manifest data/bench/manifest.csv --predictions results/predictions.csv --out results/
```

## 6. Before you push

- `make test` and `make verify` are green.
- New non-obvious choice? Add an ADR to `docs/DECISIONS.md`.
- Cleared a gate? Tick it in `docs/PROGRESS.md` with your initials and the date.
- Changed results? Regenerate `results/` in the same commit. **Never a claim in the deck without a
  commit behind it** (R2).
- Stay inside your directory (`CLAUDE.md` → ownership table). If you must touch someone else's,
  tell them first — that separation is what keeps three people from colliding.

## 7. Package the submission

```bash
make package     # -> dist/drift-lock-submission.zip, in the sponsor's recommended layout
```

Then the real test: unzip it into an empty directory **on a machine that has never seen this
project**, and run the commands in section 5. Identical numbers, or it is not done.

---

## Gotchas that have already bitten us

- **`opencv-python-headless`, never `opencv-python`.** The evaluator's box may have no display libraries.
- **`torch` is optional and lazily imported.** `pip uninstall torch` must leave everything working.
  Never import it at module top level.
- **`.gitattributes` matters.** It marks `*.png binary`; without it Windows CRLF conversion silently
  corrupts committed PNGs and quietly breaks the byte-identical reproducibility claim.
- **stdout is sacred** in single-pair mode: the coordinate and nothing else. All logs to stderr.
- **The x/y swap.** `cv2` indexes `[y, x]`; the spec wants `(x, y)`. Conversion happens only in
  `src/driftlock/io.py` (ADR-0007), and the geometry test is asymmetric on purpose — a symmetric test
  cannot catch a swap.
