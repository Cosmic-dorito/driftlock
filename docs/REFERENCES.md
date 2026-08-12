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
| 6F² DRAM cell architecture with folded-digitline sense amplifier: public structural basis for our DRAM layout generator | *6F2 DRAM cell design with 3F-pitch folded digitline sense amplifier.* US Patent 7,349,232 B2 | [patents.google.com/patent/US7349232B2](https://patents.google.com/patent/US7349232B2/en) | VERIFIED | CC | 2026-08-11 |
| **The closest-to-origin tie-break is established industrial practice for periodic SEM patterns, not an arbitrary rule.** Hitachi's CD-SEM navigation selects, among equally-scoring candidates in a periodic structure, the one *closest to a predefined origin* rather than the highest-scoring one — precisely the rule the problem statement specifies and that `select_by_centre_rule` implements literally | Sugiyama, A., Shindo, H., Komuro, H., Sutani, T. & Morokuma, H. *Pattern matching method and computer program for executing pattern matching.* US Patent 7,925,095 B2, Hitachi High-Technologies Corp. Filed 2007, granted 2011 | [patents.google.com/patent/US7925095B2](https://patents.google.com/patent/US7925095B2/en) | VERIFIED | SS | 2026-08-12 |
| **Combining correlation score with a positional term is how industry disambiguates periodic matches** — a composite index of similarity *and* position mismatch, weighted by how periodic the image is. This is the family our ambiguity index and centre rule belong to, and it is why we emit a confidence alongside the coordinate rather than a bare argmax | Abe, Y., Ikeda, M., Sato, Y. & Toyoda, Y. *Image processing method for determining matching position between template and search image.* US Patent 8,139,868 B2, Hitachi High-Technologies Corp. Priority 2007, granted 2012 | [patents.google.com/patent/US8139868B2](https://patents.google.com/patent/US8139868B2/en) | VERIFIED | SS | 2026-08-12 |
| Log-polar registration of Fourier magnitude spectra recovers rotation and scale as a translation — the basis of `pose.estimate_pose_fourier_mellin`, which we implemented, measured and then **rejected** in favour of a pyramid search (ADR-0015) | Reddy, B. S. & Chatterji, B. N. *An FFT-Based Technique for Translation, Rotation and Scale-Invariant Image Registration.* IEEE Transactions on Image Processing **5**(8):1266–1271, 1996 | [10.1109/83.506761](https://doi.org/10.1109/83.506761) | VERIFIED | SS | 2026-08-12 |

| SE yield rises with local surface tilt — the physical basis for our **edge-brightening** term, which the sponsor's starter generator omits entirely (it paints flat grey levels per material) | Villarrubia, J. S., Ritchie, N. W. M. & Lowney, J. R. *Monte Carlo modeling of secondary electron imaging in three dimensions.* Proc. SPIE **6518**, Metrology, Inspection, and Process Control for Microlithography XXI, 65180K, 5 April 2007 | [10.1117/12.712353](https://doi.org/10.1117/12.712353) · [NIST copy](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=913838) | VERIFIED — full author list, venue, article number and year confirmed | SS | 2026-08-12 |
| Phase congruency is an **illumination- and contrast-invariant** feature measure. Cited for the *idea*; our implementation is **broken** and reported as such, not as an evaluated alternative | Kovesi, P. *Phase congruency: A low-level image invariant.* Psychological Research **64**(2):136–148, 2000 | [10.1007/s004260000024](https://doi.org/10.1007/s004260000024) | VERIFIED — venue, volume, issue, pages and year confirmed | SS | 2026-08-12 |

## Partial — upgrade or drop before the deck

## TODO — identified, not yet checked

Do not cite any of these until the row is complete.

| Claim it would support | Likely source |
|---|---|
| SOTA dense feature matching, as the learned alternative we would compare against. **Dropped from the verified table on 12 Aug**: we have not run it, and R6 says "beats X" requires having run X. It returns only if we actually benchmark it | Edstedt, J. et al. *RoMa v2: Harder Better Faster Denser Feature Matching*, arXiv:2511.15706 |
| Normalized cross-correlation as the matching baseline | Lewis, J. P. *Fast Normalized Cross-Correlation.* Vision Interface, 1995 |
| ECC affine refinement — the algorithm behind `cv2.findTransformECC` | Evangelidis, G. D. & Psarakis, E. Z. *Parametric Image Alignment Using Enhanced Correlation Coefficient Maximization.* IEEE TPAMI **30**(10), 2008 |
| Intellectual ancestor of our periodic–aperiodic decomposition — **cite it and state how ours differs** | Moisan, L. *Periodic Plus Smooth Image Decomposition.* Journal of Mathematical Imaging and Vision, 2011 |
| SEM image formation and SE yield vs. local tilt (textbook grounding) | Reimer, L. *Scanning Electron Microscopy: Physics of Image Formation and Microanalysis.* Springer |
| CD-SEM image simulation for metrology | Li, Y. et al. *Monte Carlo Simulation of CD-SEM Images for Linewidth and Critical Dimension Metrology.* Scanning, 2013 |
| Distribution-free finite-sample coverage guarantee for our confidence radius | Split-conformal regression — Vovk et al., *Algorithmic Learning in a Random World*; Lei et al., *Distribution-Free Predictive Inference for Regression*, JASA 2018 |
| Image registration survey — framing | Zitová, B. & Flusser, J. *Image Registration Methods: A Survey.* Image and Vision Computing **21**(11), 2003 |
| Joint assignment rather than independent scoring — the idea behind our lattice-aware re-ranker | Sarlin, P.-E. et al. *SuperGlue: Learning Feature Matching with Graph Neural Networks.* CVPR 2020 |

---

## Attribution

The sponsor's starter synthetic-data generator
(<https://huggingface.co/spaces/aayushraina21/drift-sense-synthetic-data>) is used **only** as an
independent cross-validation dataset and as the baseline we measure against. Its code is **not
vendored** into this repository; `scripts/fetch_reference_generator.sh` clones it into gitignored
`third_party/`. All generator code in `src/synth/` is our own.
