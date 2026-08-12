# WORKLOG — who changed what, on which machine, when

We are three people running Claude Code **sequentially** on our own laptops. Git history says *what*
changed; this file says *what was being attempted, on which machine, and what the measurement said*.
When something breaks two days later, this is the file that tells you which session to blame.

**Entry format.** Newest first. Every entry states the **date**, the **machine**, and the
**environment**, because we have already been bitten by a result that depended on the machine.

| Machine | Owner | OS | Python | OpenCV |
|---|---|---|---|---|
| `MacBook Air M2` | Sanjay | macOS 26.5.2 (Apple M2, 8 cores, 16 GB) | 3.12.7 | 5.0.0 |
| `win-2` | (teammate 2) | Windows 11 x86-64 | 3.14.3 | 5.0.0.93 |
| `win-3` | (teammate 3) | Windows 11 x86-64 | 3.14.3 | 5.0.0.93 |

> Fill in the two Windows rows with your actual names and `python -VV` output when you next run.

**Cross-platform rule.** Everything must run on macOS *and* Windows. `.venv/` is machine-local and
gitignored: on macOS `make setup` builds `.venv/bin`, on Windows `.\make.ps1 setup` builds
`.venv\Scripts`. Never commit a venv, never hard-code a path, `pathlib` only —
`scripts/verify_submission.py` fails the build on absolute paths.

---

## 2026-08-12 · MacBook Air M2 · Sanjay — rotation and scale made to work at all

**Where the session started.** The pipeline scored well on the sponsor's data (25% mis-lock,
0.24 px median) but had **never been run on our own generator's output**, which is the only data
with rotation and scale variation — the envelope the spec says will be tested.

**First measurement of the session, and it set the agenda:**

| Config | mis-lock | median | pass@1px |
|---|---|---|---|
| shipped default, on `data/bench` (rotation ±2°, scale 9–11) | **95%** | 326 px | 0% |

Total failure. Everything below follows from chasing that number down.

### 1. The forward operator could not express the pose — root cause

`build_template` used `cv2.resize(..., INTER_AREA)`, which only produces an **integer** output size.
So the achievable magnification was quantised to `1000/n`: 9.0090, 9.0909, 9.1743, … — steps of
about **1%**. Our own earlier measurement says a 1.3% scale error collapses the ZNCC peak from 0.856
to 0.262. **The quantisation step was as coarse as the entire tolerance**, so no pose search could
ever have worked, however fine its grid — the grid it was searching did not exist in the template
builder. `INTER_AREA` also cannot express rotation at all.

*Fix.* `build_template` is now one continuous affine: box-integrate over the true detector footprint
(`area_kernel`, an exact box of arbitrary real width), then sample with the same matrix the
generator uses. Scale and rotation are both exact, and `out_size` can be pinned so the correlation
score is a smooth function of scale.

*Regression check — this is the one that mattered.* The centre convention (H2) was calibrated
empirically against the sponsor's manifests, so a half-pixel shift here would silently destroy
every sub-pixel result. On the sponsor `verify` split the baseline reproduces **exactly**
(25.0% mis-lock, 1.102 px median, 40% pass@1px) and the default lands at 0.243 px against the
0.238 px committed by `win-2`. No shift.

### 2. Pose: three methods tried, the elegant one lost

| Method | scale median error | rotation median error | verdict |
|---|---|---|---|
| Reciprocal-lattice peak voting (`pose.estimate_pose`) | 1.21% | 0.24° | too imprecise |
| Log-polar Fourier–Mellin (`pose.estimate_pose_fourier_mellin`) | 3.49% (**+2.07% bias**) | **0.13°** | biased on our data |
| **Coarse pyramid search** (`match.pyramid_pose`) | **0.72%** (bias +0.09%) | 0.43° | **shipped** |

Both spectral methods are in the codebase and in the ablation as measured negative results (R9).

**Why the lattice-as-a-ruler idea lost, and it is worth understanding rather than hiding.** The
`dram_legacy` preset has a 240 nm bit-line pitch, so a 1000 nm reference contains **4.2 periods**.
A frequency estimated from four periods cannot be pinned to the 0.5% correlation demands. The
lattice is a *fine* ruler but a *short* one. Diagnosed by printing the radial spectra rather than by
tuning: the reference's content sits at frequency bins 3–8, where one bin is several percent.

The pyramid search sidesteps it: downsampling 4× shrinks the template from 100 px to 25 px, and
since a scale error costs misalignment *proportional to template size*, the basin widens from ~1% to
~4%. The whole 9:1–11:1 envelope is then covered by ~11 hypotheses at 1/16 the cost each.

*Rotation sign, settled by measurement not derivation:* correlating the estimate against the
manifest gave **r = −0.899**, i.e. inverted. The field of view is sampled *through* the rotation, so
image content turns the other way.

### 3. Two bugs the sponsor's data structurally could not reveal

With the **true pose supplied from the manifest**, mis-lock was still 67.5% — so pose was no longer
the problem. The residuals had obvious structure:

```
dy = +0.503 px  (std 0.035)      <- a constant: a convention error
dx = -9.5 x rotation_deg          <- a clean line through the failures
```

**(a) Our generator's ground truth was half a pixel off.** `warpAffine` samples at *pixel centres*,
so the analytic inverse lands in pixel-index space; the problem's convention (H2-verified) is
`origin + size/2`, which is half a pixel further. Our GT sat half a pixel from the sponsor's for the
same physical situation. Since the sub-pixel threshold **is** 0.5 px, this alone would have made
every sub-pixel claim on our own benchmark fail while the sponsor's data passed — and we would
have blamed the matcher. Fixed in `canvas_to_search_coords`.

**(b) The blind drift estimator was mistaking rotation for drift.** A tilt of ρ displaces content by
`gap·tan(ρ)` over the same row separation that drift does — the two are *indistinguishable* to that
measurement. The estimator reported the tilt as drift and then "corrected" a distortion that was
never there, up to 19 px on a 2° pair. It never showed on the sponsor's data because their generator
produces no rotation (H9). `estimate_shear` now takes `rotation_deg` and subtracts the geometric
term. Regression tests in `tests/test_forward_model.py` pin the hand-derived −17.44 px artefact.

### 4. Generator realism fix

`build_canvas(vary_preset_per_mat=True)` randomised each mat's **pitch** by ±6%. That is physically
wrong — a cell array's pitch is a design rule fixed by lithography, identical across every mat on a
die; mats differ in line-edge roughness and local CD, which we already model. It was added for
"diversity" and it also destroyed the only quantity that makes magnification measurable. Default is
now **off**; kept as a flag for the ablation. Diversity comes from drawing a different preset per
*sample*, which is where it belongs.

### 5. Cross-platform fix

`resolve_manifest_path` could not resolve **Windows-authored manifests on macOS**: POSIX treats `\`
as an ordinary filename character, so `data\verify\ref\0.png` simply did not exist and the entire
batch failed. Since two of us are on Windows and the evaluator's manifest may be Windows-authored,
this was a live submission risk. Backslash normalisation is now tried as a *fallback* (never first —
on POSIX a backslash can legitimately be part of a name, so a real file must always win).

### 6. Also fixed

* `localize.py --visualize` crashed — `src/driftlock/visualize.py` did not exist, though the flag is
  in the frozen CLI contract and the spec requires a visualized failure case. Written; it draws the
  runners-up as well as the winner, because on this problem a mis-lock is never a near miss.
* `.venv` in this checkout was a **Windows** venv (`Scripts/`, no `bin/`) and could not run on
  macOS. Rebuilt locally. The pinned `requirements.txt` installs cleanly on macOS/Python 3.12 —
  so the pin set is now verified on both platforms, not just Windows.

### 7. Two more ideas tried for mis-lock — both measured, both rejected

Recorded because they failed for the *same* reason, and that reason is now a design rule.

* **Coarse-level consensus re-ranking.** Idea: at 4× downsampling the cell pitch collapses toward
  Nyquist while mat/strip landmarks survive, so the coarse level should be able to vote on which
  repeat is right. *Measured: mis-lock 20.0% → 55.0% on dev, median 0.497 → 32.9 px.* The reasoning
  had a units error — downsampling does not widen the **field of view**, and the reference's
  1000 nm footprint is smaller than a 2600 nm mat, so there was never a landmark in frame to
  reveal. It only threw away samples.
* **Running the pose bracket at half resolution** (a pure speed optimisation). *Measured: 333 → 159
  ms, but mis-lock 27.5% → 45.0% on sponsor and 20.0% → 37.5% on dev.* Rejected.

**The rule both of them bought:** *downsampling is free for measuring pose and ruinous for deciding
identity.* Pose is a global, low-frequency property; identity lives entirely in the full-resolution
aperiodic fingerprint. That is why the pyramid is used for the former and never the latter.

### 8. Runtime, and the trade we chose

~370–406 ms per pair end to end (includes image loading), against our self-imposed 300 ms target.
The pose bracket is five full-resolution correlations and dominates. The trade was measured rather
than assumed:

| bracket | sponsor mis-lock | dev mis-lock | runtime |
|---|---|---|---|
| 5 steps (shipped) | 27.5% | 20.0% | ~340 ms |
| 3 steps | 30.0% | 22.5% | ~260 ms |

We took accuracy: mis-lock is the metric the problem is about, and 80 ms does not buy back 2.5–5
points of it. If the evaluator publishes a hard runtime limit, `pose_bracket_steps=3` is the dial.

### 9. A submission-breaker caught in the final smoke test

`localize.py --json` was emitting `"confidence_radius_px": Infinity`. **That is not valid JSON** —
Python's `json` module writes it happily, but a strict parser rejects the entire document, so an
evaluator consuming our JSON would have failed the batch on a field nobody asked for. `inf` was the
ambiguity index saying "no rival candidate was close enough to compete", i.e. maximum confidence.
Now emitted as `null` (and as an empty cell in `predictions.csv`), with `json.dumps(allow_nan=False)`
so the failure mode cannot come back silently.

Worth generalising: the correctness rules in `CLAUDE.md` are all about *numbers being right*, and
this was a case of the right number in a format that would have scored zero.

### Final state at end of session

| Split | mis-lock | median | pass@1px | pass@0.5px | runtime p50 |
|---|---|---|---|---|---|
| sponsor `verify` (40) | 27.5% | 0.297 px | 70.0% | 67.5% | 371 ms |
| bench (30, ours) | 33.3% | 0.556 px | 60.0% | 46.7% | 406 ms |
| holdout FinFET (30) | 33.3% | 0.706 px | 66.7% | 33.3% | 398 ms |

`scripts/verify_submission.py`: **15 passed, 0 failed, 1 pending** (the pending one is the
mandatory `.pptx`, which does not exist yet). 35 tests pass; `ruff` clean.

**Next session should start here:** the mis-lock rate is the only thing capping every pass rate,
the true location is in the top-20 candidates 92.5% of the time, and the worst failure on bench
lost by **0.0027 ZNCC at rank 4** (`results/failure_case/`). Two re-rankers have already failed —
read ADR-0012 and §7 above before building a third.

### Environment note for the other two

Results in this entry were produced on **Python 3.12.7 / OpenCV 5.0.0 (macOS, Apple M2)**, whereas
`win-2`'s committed numbers came from **3.14.3 / 5.0.0.93 (Windows)**. The sponsor-split baseline
reproduces to the digit across both, which is the cross-platform determinism evidence we wanted —
worth keeping true.

---

## 2026-08-11 · win-2 — baseline, hypotheses, drift correction

Recorded in `docs/FINDINGS.md` §1–§12h and `docs/DECISIONS.md` ADR-0001…0013. Summary: sponsor
generator hypotheses H1–H10 verified; baseline reproduced (25% mis-lock, 1.102 px); sub-pixel DFT
and blind drift correction shipped; PADM re-scoring withdrawn as overfit (ADR-0012).
