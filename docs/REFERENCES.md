# REFERENCES

**Rule R1: nobody cites anything they have not opened.** A row needs all five columns —
claim, full citation, DOI/URL, verified-by, date. A row missing any of them is **not a citation** and
must not appear in the PPT. If a source cannot be verified, delete the claim or restate it as our own
reasoning: *"we chose X because Y"* is honest; a fabricated citation in front of a KLA/AMAT panel is
fatal.

Synthetic augmentation is **30%** of the score and explicitly requires *"at least 2–3 credible public
sources"* with *"literature-based justification"*. This file is that deliverable.

**Status key.** `VERIFIED` = someone opened the source and confirmed title, authors, venue and year.
`PARTIAL` = title and existence confirmed from a search result, but the full record has not been
opened — **must be upgraded to VERIFIED or dropped before it goes in the deck.**
`TODO` = identified as relevant, not yet checked at all.

---

## Verified

| Claim it supports | Citation | DOI / URL | Status | Verified by | Date |
|---|---|---|---|---|---|
| Our noise model is Poisson-then-Gaussian, so the **Generalized Anscombe Transform** is the matched variance-stabilizing tool; only after it is correlation the ML estimator | Mäkitalo, M. & Foi, A. *Optimal Inversion of the Generalized Anscombe Transformation for Poisson-Gaussian Noise.* IEEE Transactions on Image Processing **22**(1):91–103, 2013 | [10.1109/TIP.2012.2202675](https://doi.org/10.1109/TIP.2012.2202675) | VERIFIED | CC | 2026-08-11 |
| Sub-pixel registration by upsampled-DFT cross-correlation; the method behind `skimage.registration.phase_cross_correlation` | Guizar-Sicairos, M., Thurman, S. T. & Fienup, J. R. *Efficient subpixel image registration algorithms.* Optics Letters **33**(2):156–158, 2008 | [10.1364/OL.33.000156](https://doi.org/10.1364/OL.33.000156) | VERIFIED | CC | 2026-08-11 |
| Current state of the art in dense feature matching — the modern learned alternative we benchmark against and explain why we did not adopt | Edstedt, J. et al. *RoMa v2: Harder Better Faster Denser Feature Matching.* arXiv:2511.15706, 2026 | [arXiv:2511.15706](https://arxiv.org/abs/2511.15706) | PARTIAL — author list not confirmed | CC | 2026-08-11 |
| 6F² DRAM cell architecture with folded-digitline sense amplifier: public structural basis for our DRAM layout generator | *6F2 DRAM cell design with 3F-pitch folded digitline sense amplifier.* US Patent 7,349,232 B2 | [patents.google.com/patent/US7349232B2](https://patents.google.com/patent/US7349232B2/en) | VERIFIED | CC | 2026-08-11 |

## Partial — upgrade or drop before the deck

| Claim it supports | Citation | DOI / URL | Status | Verified by | Date |
|---|---|---|---|---|---|
| SE yield rises with local surface tilt — the physical basis for our **edge-brightening** term, which the starter generator omits | Villarrubia, J. S. et al. *Monte Carlo modeling of secondary electron imaging in three dimensions.* NIST / SPIE | [tsapps.nist.gov pub_id 913838](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=913838) | PARTIAL — title and host confirmed; **author list, venue and year not yet confirmed** | CC | 2026-08-11 |
| Phase congruency is an **illumination- and contrast-invariant** feature measure — why we match on it rather than raw intensity, defeating the search image's gamma and vignette | Kovesi, P. *Phase congruency: A low-level image invariant.* Psychological Research, 2000 | [peterkovesi.github.io](https://peterkovesi.github.io/ImagePhaseCongruency.jl/dev/) | PARTIAL — concept and author confirmed; **venue, volume and year NOT confirmed** | CC | 2026-08-11 |

## TODO — identified, not yet checked

Do not cite any of these until the row is complete.

| Claim it would support | Likely source |
|---|---|
| Normalized cross-correlation as the matching baseline | Lewis, J. P. *Fast Normalized Cross-Correlation.* Vision Interface, 1995 |
| ECC affine refinement — the algorithm behind `cv2.findTransformECC` | Evangelidis, G. D. & Psarakis, E. Z. *Parametric Image Alignment Using Enhanced Correlation Coefficient Maximization.* IEEE TPAMI **30**(10), 2008 |
| Fourier–Mellin fallback for rotation/scale when lattice peaks are weak | Reddy, B. S. & Chatterji, B. N. *An FFT-Based Technique for Translation, Rotation and Scale-Invariant Image Registration.* IEEE TIP **5**(8), 1996 |
| Intellectual ancestor of our periodic–aperiodic decomposition — **cite it and state how ours differs** | Moisan, L. *Periodic Plus Smooth Image Decomposition.* Journal of Mathematical Imaging and Vision, 2011 |
| SEM image formation and SE yield vs. local tilt (textbook grounding) | Reimer, L. *Scanning Electron Microscopy: Physics of Image Formation and Microanalysis.* Springer |
| CD-SEM image simulation for metrology | Li, Y. et al. *Monte Carlo Simulation of CD-SEM Images for Linewidth and Critical Dimension Metrology.* Scanning, 2013 |
| Distribution-free finite-sample coverage guarantee for our confidence radius | Split-conformal regression — Vovk et al., *Algorithmic Learning in a Random World*; Lei et al., *Distribution-Free Predictive Inference for Regression*, JASA 2018 |
| Image registration survey — framing | Zitová, B. & Flusser, J. *Image Registration Methods: A Survey.* Image and Vision Computing **21**(11), 2003 |
| Joint assignment rather than independent scoring — the idea behind our lattice-aware re-ranker | Sarlin, P.-E. et al. *SuperGlue: Learning Feature Matching with Graph Neural Networks.* CVPR 2020 |
| Industry practice in wafer alignment / pattern-recognition navigation | Patents from KLA, Applied Materials, ASML, Hitachi High-Tech on "pattern recognition alignment", "die-to-die alignment", "coordinate correction for inspection tool" |

---

## Attribution

The sponsor's starter synthetic-data generator
(<https://huggingface.co/spaces/aayushraina21/drift-sense-synthetic-data>) is used **only** as an
independent cross-validation dataset and as the baseline we measure against. Its code is **not
vendored** into this repository; `scripts/fetch_reference_generator.sh` clones it into gitignored
`third_party/`. All generator code in `src/synth/` is our own.
