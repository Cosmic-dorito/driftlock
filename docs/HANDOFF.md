# HANDOFF — cold start on a new machine

## ⏩ RESUME HERE — state as of 12 Aug 2026, commit `02f780d`

**The submission is COMPLETE, VERIFIED and PACKAGED.** Everything below is optional improvement
work. If time runs out right now, ship what is in `dist/`.

* `scripts/verify_submission.py --strict` → **17 passed, 0 failed, 0 pending**
* 36 tests pass · ruff clean · `dist/drift-lock-submission.zip` builds and reproduces bit-identically
  from a clean extract
* Deadline **16 Aug 2026**

### Current measured results (generated into `docs/RESULTS.md` from `results/`)

| Split | mis-lock | median px | pass@1px | pass@0.5px | p50 |
|---|---|---|---|---|---|
| sponsor (40) | 25.0% | 0.297 | 72.5% | 67.5% | 316 ms |
| bench (30, ours) | 23.3% | 0.343 | 73.3% | 63.3% | 322 ms |
| holdout FinFET (30) | 16.7% | 0.313 | 80.0% | 63.3% | 328 ms |

Baselines: 25.0 / 76.7 / 90.0 % mis-lock. Aggregate **22/100 = 22.0%**.

### Shipped configuration (`localize.py::build_config`)

```python
PipelineConfig(label="driftlock", subpixel=True, drift_correction=True,
               pose_search=True, top_k=10, candidate_refit=True, refit_steps=2)
```

### 🎯 THE NEXT ACTION — make the known-better configuration affordable

This is where work stopped, mid-thought. It is the highest-value remaining item.

**The known accuracy/runtime frontier:**

| config | held-out mis-lock | p50 |
|---|---|---|
| shipped (narrow refit) | 22.0% | ~308 ms |
| dense wide refit | **20.0%** | ~850 ms |

where "dense wide" is `refit_steps=5, refit_scale_span=0.03, refit_rotation_span=1.5`.

**The idea not yet tried:** the dense config costs ~26 ms per extra template, and
`build_template()` does two things — *box-integrate* the 1000×1000 reference (depends on **scale
only**) and *warp* it (depends on scale **and** rotation). The refit currently calls
`build_template(reference, scale, rotation)` **without** passing `integrated=`, so it re-integrates
for every rotation.

`build_template` **already accepts an `integrated=` argument** — the pose bracket in
`match.py::localize` uses it (`integrated = integrate_reference(ref_proc, poses[0][0] * level)`).
The refit does not.

So: in `src/driftlock/refit.py::_refit_once`, group the pose grid **by scale**, call
`integrate_reference` once per scale, and pass it into `build_template` for every rotation at that
scale. For a 5×5 grid that is 5 integrations instead of 25.

**If this brings the dense config under ~400 ms, ship it** — that is 20.0% held-out at acceptable
runtime, strictly better than the current 22.0%. Validate on **all four** splits (dev, sponsor,
bench, finfet) before believing it; a stage checked on a convenient subset has already reversed a
conclusion twice in this project (ADR-0012, ADR-0021).

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
