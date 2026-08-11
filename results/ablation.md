# Ablation

Cumulative ladder over **12 pairs** from the sponsor's published generator.
Each row enables one more stage than the row above it.

| Stage | Mis-lock rate | Median err (px) | Median, located only | Worst (px) | pass@5px | pass@2px | pass@1px | pass@0.5px | Median runtime (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 1. baseline (sponsor: INTER_AREA + ZNCC argmax) | 8.3% | 0.999 | 0.894 | 14.4 | 92% | 92% | 50% | 17% | 16 |
| 2. + median + row destripe | 25.0% | 1.383 | 1.105 | 601.4 | 75% | 75% | 33% | 17% | 30 |
| 3. + Anscombe (A1) | 25.0% | 1.383 | 1.105 | 601.4 | 75% | 75% | 33% | 17% | 60 |
| 4. + top-K candidates (A6) | 25.0% | 1.383 | 1.105 | 601.4 | 75% | 75% | 33% | 17% | 63 |
| 5. + PADM residual re-score (A7) | 16.7% | 1.219 | 0.999 | 57.6 | 83% | 83% | 42% | 17% | 242 |
| 6. + centre rule (A8) | 33.3% | 1.492 | 1.219 | 76.1 | 67% | 67% | 25% | 8% | 244 |
| 7. + sub-pixel DFT (A9) | 33.3% | 1.752 | 1.388 | 75.9 | 67% | 58% | 17% | 8% | 256 |
| 8. + ECC affine (A9) | 33.3% | 1.752 | 1.388 | 75.9 | 67% | 58% | 17% | 8% | 256 |

## Reading this table

Two independent failure modes, and they need separate columns:

* **Mis-lock rate** - landing on the wrong repeat of the lattice. Catastrophic and invisible to any averaged error metric, because a mis-lock is off by tens or hundreds of pixels while a good match is off by about one.
* **pass@1px / pass@0.5px** - precision once the right repeat is found.

A stage that improves one may leave the other untouched; that is expected, and it is why a single headline number would be misleading here.