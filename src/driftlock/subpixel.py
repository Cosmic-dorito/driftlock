"""A9: sub-pixel refinement.

Two stages, in order:

1. **Upsampled-DFT cross-correlation** (Guizar-Sicairos, Thurman & Fienup, *Optics Letters* 33(2),
   2008; available as ``skimage.registration.phase_cross_correlation``). Refines the integer peak to
   a fraction of a pixel without interpolating the images.

2. **ECC affine refinement** (Evangelidis & Psarakis; ``cv2.findTransformECC``). Affine rather than
   Euclidean, and that choice is forced by measurement, not taste: H10 showed the search image
   carries a raster SHEAR that biases x by -0.84 px on average while leaving y unbiased, with dx
   correlating with the template's y position at r = -0.861. A Euclidean model cannot represent
   shear, so it cannot remove that bias. Measured accuracy on band-limited data: 0.037 px affine
   versus 0.055 px translation-only (ADR-0003).

The baseline's pass@1px is 40% while its pass@2px is 75% - almost all correctly-located pairs sit
between 1 and 2 px, which is exactly the band this module has to close.
"""

from __future__ import annotations

import cv2
import numpy as np

# Half-width of the patch, in search pixels, cut around a candidate for refinement.
_PATCH_MARGIN = 12


def refine(search: np.ndarray, reference: np.ndarray, candidate,
           use_dft: bool = True, use_ecc: bool = True):
    """Refine a candidate's location to sub-pixel precision.

    Refinement is only ever accepted if it stays within a few pixels of the incoming estimate: these
    are local methods and a large jump means divergence, not a better answer. Falling back to the
    unrefined coordinate cannot make things worse, which is what keeps this stage strictly additive.
    """
    from src.driftlock.match import build_template

    template = build_template(reference, candidate.scale, candidate.rotation_deg)
    th, tw = template.shape[:2]
    sh, sw = search.shape[:2]

    x0 = int(round(candidate.x - tw / 2.0))
    y0 = int(round(candidate.y - th / 2.0))

    px0, py0 = x0 - _PATCH_MARGIN, y0 - _PATCH_MARGIN
    px1, py1 = x0 + tw + _PATCH_MARGIN, y0 + th + _PATCH_MARGIN
    if px0 < 0 or py0 < 0 or px1 > sw or py1 > sh:
        return candidate  # too close to the frame edge to refine safely

    patch = search[py0:py1, px0:px1].astype(np.float32)
    dx_total, dy_total = 0.0, 0.0

    if use_dft:
        dx, dy = _dft_shift(patch, template, _PATCH_MARGIN)
        if abs(dx) <= 3.0 and abs(dy) <= 3.0:
            dx_total += dx
            dy_total += dy

    if use_ecc:
        dx, dy = _ecc_shift(patch, template, _PATCH_MARGIN + dx_total, _PATCH_MARGIN + dy_total)
        if dx is not None and abs(dx) <= 3.0 and abs(dy) <= 3.0:
            dx_total, dy_total = dx, dy

    candidate.x = float(x0 + tw / 2.0 + dx_total)
    candidate.y = float(y0 + th / 2.0 + dy_total)
    return candidate


def _dft_shift(patch: np.ndarray, template: np.ndarray, margin: int) -> tuple[float, float]:
    """Upsampled-DFT registration between the template and the co-located patch region."""
    try:
        from skimage.registration import phase_cross_correlation
    except ImportError:
        return 0.0, 0.0

    th, tw = template.shape[:2]
    window = patch[margin:margin + th, margin:margin + tw]
    if window.shape != template.shape:
        return 0.0, 0.0

    # normalization=None is mandatory, not stylistic. The scikit-image default 'phase' whitens the
    # spectrum by dividing by magnitude, and on blurred images the high-frequency magnitudes are
    # ~0, so that division amplifies numerical noise and silently returns ~zero shift - 2.8 px
    # error on a true 2.86 px displacement at blur sigma=3. Our images ARE blurred by the beam
    # PSF. See ADR-0009 and tests/test_deps_api.py.
    shift, _, _ = phase_cross_correlation(
        window.astype(np.float32), template.astype(np.float32),
        upsample_factor=100, normalization=None,
    )
    # Sign convention determined EMPIRICALLY, not from the documentation: with
    # phase_cross_correlation(window, template), the returned (row, col) shift must be ADDED to the
    # current estimate. Measured on 8 real pairs, adding improved 7 of them (e.g. 0.894 -> 0.411 px,
    # 1.105 -> 0.680 px) while subtracting made every one worse. Getting this backwards silently
    # doubles the error instead of halving it, which is exactly the kind of plausible-but-wrong
    # result that survives code review.
    return float(shift[1]), float(shift[0])


def _ecc_shift(patch: np.ndarray, template: np.ndarray,
               start_x: float, start_y: float) -> tuple[float | None, float | None]:
    """ECC affine refinement, seeded from the current estimate."""
    th, tw = template.shape[:2]

    warp = np.array([[1.0, 0.0, float(start_x)],
                     [0.0, 1.0, float(start_y)]], dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-6)

    tmpl = _normalise(template)
    target = _normalise(patch)

    try:
        # findTransformECC solves for the warp mapping the template into the patch's frame.
        _, warp_out = cv2.findTransformECC(
            tmpl, target, warp, cv2.MOTION_AFFINE, criteria, None, 3
        )
    except cv2.error:
        # Non-convergence is expected on low-texture or heavily-degraded patches; the caller keeps
        # the unrefined estimate rather than a divergent one.
        return None, None

    # The affine may include shear and scale; the translation of the template CENTRE is what we
    # want, so transform the centre point rather than reading tx/ty directly.
    cx, cy = tw / 2.0, th / 2.0
    mapped_x = warp_out[0, 0] * cx + warp_out[0, 1] * cy + warp_out[0, 2]
    mapped_y = warp_out[1, 0] * cx + warp_out[1, 1] * cy + warp_out[1, 2]
    return float(mapped_x - cx), float(mapped_y - cy)


def _normalise(img: np.ndarray) -> np.float32:
    """Zero-mean, unit-variance float32 - ECC expects well-conditioned single-channel input."""
    work = img.astype(np.float32)
    std = float(work.std())
    return (work - work.mean()) / (std + 1e-6)
