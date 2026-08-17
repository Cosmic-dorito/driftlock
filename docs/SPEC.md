# SPEC — requirements extracted from the Applied Materials problem statement

Source: `reference/AMAT_DriftSense_ProblemStatement.pdf` (participant help document, 7 pages).
This file is a faithful extraction, not an interpretation. Where we interpret, it is marked
**[our reading]**. The PDF wins in any conflict.

> The PDF states: *"The final evaluation utility, exact sub-pixel cutoff, test dataset instructions
> and runtime environment will take precedence when released."* Re-read this file if anything new
> is published.

---

## 1. Task

Locate a high-resolution 100× reference pattern inside a larger-field 10× search image and return the
centre coordinates of the matching region.

## 2. Input / output

| Item | Requirement |
|---|---|
| Reference image | 1000 × 1000 grayscale, 100× close-up |
| Search image | 1000 × 1000 grayscale, wider 10× view containing the target |
| Scale relationship | Nominal **10:1**. Robustness testing may include approximately **9:1 to 11:1** |
| Rotation | Small variations of about **1–2 degrees** may occur |
| Output | Predicted target-centre `(x, y)` in **search-image pixels** |
| Coordinates | Origin `(0,0)` **top-left**; `x` increases right, `y` increases **down** |
| Multiple matches | If several valid matches exist, **select the one whose centre is closest to the search-image centre** |

**[our reading]** Both images are 1000×1000 but cover different physical fields of view, so the
reference's content occupies roughly a **100×100 px** footprint inside the search image. Confirmed
against the sponsor's published generator; tracked as hypothesis **H1** in `docs/SPEC.md`.

## 3. Synthetic dataset creation

- Choose **either DRAM-style or FinFET-style**; both judged equally.
- Use **only public structural knowledge and participant-created synthetic data**. No confidential fab data.
- Generate paired reference image, search image, true target-centre coordinates, and **per-pair metadata**.
- Store **random seed, architecture, transformations, noise settings, scale, rotation and ground truth for every pair**.
- **Justify structures, noise and augmentations using at least 2–3 credible public sources**; cite in
  the PPT and documentation.

Degradations discussed in the sessions (none mandatory, choices must be technically justified):
blur/astigmatism, shot noise, drift or jitter, contrast/gamma change, charging streaks,
salt-and-pepper noise, spot-size blur, and **feature loss during downsampling**.

## 4. Localization solution

- Implement in **Python**.
- **Account explicitly for the scale difference** instead of relying on an accidental match.
- Process **a pair or an evaluator-provided batch without manual source-code changes**.
- Return the selected centre coordinates and **provide a repeatable score or confidence where possible**.
- **Measure computation time** and **explain at least one genuine failure case**.
- Deep learning is **not** mandatory. Pretrained models allowed **if all weights and dependencies are
  disclosed and available**.
- A web application is **not** required. **A single notebook is not sufficient** as the only runnable submission.

## 5. Validation requirements

Validate on **at least 30 varied, independently generated pairs** and report:

- Euclidean localization error `sqrt((x_pred - x_true)^2 + (y_pred - y_true)^2)`
- **Pass rate at 5, 4, 2 and 1 pixel thresholds**, plus sub-pixel performance where supported
- **Mean, median and worst-case** error
- **Runtime per image pair, with hardware, Python version and timing method**
- Results across multiple noise levels, target positions, scales and rotations
- **At least one visualized failure case with root-cause explanation**

## 6. Evaluation weights (provisional, from the sponsor presentation)

| Parameter | Weight | What evaluators examine |
|---|---|---|
| Localization / inference | **50%** | Coordinate accuracy on sponsor test data, and computation time |
| Synthetic augmentation code | **30%** | Realism, diversity, reproducibility, literature-based justification |
| Failure analysis / explainability | **10%** | Understanding of failure causes, **especially repeated-pattern ambiguity** |
| RGB optical-image extension | **Bonus** | Optional generalization after the grayscale SEM task |
| Remaining core weight | **10% pending** | Not defined in the supplied presentation |

## 7. Phase-1 deliverables

1. **Solution PPT/PPTX (mandatory)** — problem understanding, approach, architecture choice,
   synthetic-data method, degradations, localization method, experiments, threshold-wise results,
   runtime, failure analysis, citations, limitations, next steps.
2. **Source code** — separate, documented Python code for dataset generation and localization/inference.
3. **README** — environment setup, folder structure, exact commands, input/output examples,
   coordinate convention, assumptions.
4. **Dependencies** — `requirements.txt` or pip-freeze equivalent; include weights if used.
5. **Results** — metrics, plots/overlays, runtime, robustness analysis, at least one failure case.
6. **CSV/manifest** — reference path, search path, ground-truth x/y, predicted x/y, per-pair metadata.
7. **References** — public sources for structures, image formation, noise, transformations.

Recommended submission folder:
```
submission/
  solution_presentation.pptx
  README.md
  requirements.txt
  generate_dataset.py
  localize.py
  configs/  src/  model/  results/  references/
```
**[our reading]** We keep a clean working repo at root and emit exactly this tree via
`scripts/package_submission.py`. See ADR-0001.

## 8. Recommended PPT structure (12 slides)

Template: <https://i4c.in/wp-content/uploads/2026/07/Idea-Submission-Template_Hackathon-2026-1.pptx>

1. Title, team, one-line solution summary
2. Problem understanding and navigation-error context
3. Proposed end-to-end workflow
4. DRAM/FinFET synthetic-data design
5. Noise, blur, scale and rotation modelling **with citations**
6. Localization method and decision rule
7. Implementation and execution commands
8. Experiment setup and test diversity
9. Threshold-wise accuracy, error statistics and runtime
10. Robustness comparison and baseline/ablation
11. Failure case, limitations and learnings
12. Conclusion, next steps, repository/submission reference

## 9. Final submission checklist — all 15 boxes

`scripts/verify_submission.py` automates every box it can.

- [ ] Mandatory solution PPT/PPTX included
- [ ] 1000 × 1000 reference and search images used
- [ ] 10:1 relationship implemented and documented
- [ ] Top-left coordinate convention and closest-to-centre rule implemented
- [ ] Python generator and Python localization code are separate and runnable
- [ ] README contains exact setup and execution commands
- [ ] Dependencies and all required weights are included
- [ ] At least 30 varied cases are evaluated
- [ ] 5-, 4-, 2- and 1-pixel pass rates are reported
- [ ] Runtime, hardware and timing method are stated
- [ ] At least one failure case is shown and explained
- [ ] CSV/manifest contains paths, true coordinates, predictions and metadata
- [ ] At least 2–3 credible public sources are cited
- [ ] **No proprietary data or hard-coded local paths are present**
- [ ] Submission was dry-run in a clean environment

## 10. Session notes

**Webinar, 31 Jul 2026** — core problem is cross-magnification localization in repetitive
semiconductor patterns. Both inputs are 1000×1000 but represent different physical fields of view.
Teams may choose DRAM or FinFET, using public knowledge. Accuracy, synthetic augmentation, runtime
and explainable failure analysis are the central evaluation themes.

**Q&A, 6 Aug 2026** — coordinate origin is top-left; output is the target centre in search-image
pixels. Slight scale variation, 1–2° rotation and **a noisier search image** may be tested. Report
performance at 5, 4, 2 and 1 pixels and sub-pixel where supported. DL and a web app are not
mandatory; pretrained models allowed. CSV/manifest and per-pair metadata expected for reproducibility.

## 11. Resources

- Starter synthetic-data Space: <https://huggingface.co/spaces/aayushraina21/drift-sense-synthetic-data>
- Problem statement explanation: <https://www.youtube.com/watch?v=I_mYBGeoiXA>
- Q&A session: <https://www.youtube.com/watch?v=AA5Wb9FUACc>
- Registration / submission: <https://i4c.in/hackathon-2026/>

## 12. Dates

| Date | Event |
|---|---|
| 31 Jul 2026 | Problem statement webinar |
| 6 Aug 2026 | Key concepts & Q&A session |
| **16 Aug 2026** | **Registration & Phase-1 submission deadline** |
