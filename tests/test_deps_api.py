"""Pin down the third-party API surface we actually depend on.

Rule R7: no API is used from memory. Claude Code (and humans) confidently invent plausible
signatures, and a major-version bump can move or silently change behaviour. These tests fail loudly
if someone's environment drifts, instead of us discovering it as a mysterious accuracy regression.

Everything here was established empirically on 2026-08-11 against opencv-python-headless 5.0.0.93 /
scikit-image 0.26.0 / numpy 2.5.2 on Python 3.14.3. See ADR-0003 and ADR-0009.
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from skimage.registration import phase_cross_correlation  # noqa: E402


# Symbols the localization pipeline calls. If OpenCV moves one, fail here, not at 2 a.m. on Day 3.
REQUIRED_CV2_SYMBOLS = [
    "matchTemplate", "TM_CCOEFF_NORMED", "minMaxLoc",
    "findTransformECC", "MOTION_AFFINE", "MOTION_EUCLIDEAN", "MOTION_TRANSLATION",
    "resize", "INTER_AREA", "INTER_LINEAR", "INTER_CUBIC",
    "remap", "warpAffine", "GaussianBlur", "medianBlur",
    "Scharr", "Sobel", "circle", "getStructuringElement", "morphologyEx",
    "setNumThreads", "TERM_CRITERIA_EPS", "TERM_CRITERIA_COUNT",
]


def _band_limited_image(size=256, blur=3.0, seed=0):
    """A smooth, band-limited test image.

    Deliberately NOT white noise: bilinear/bicubic warping of white noise aliases badly, which
    makes any sub-pixel method look far worse than it is. Real SEM frames are band-limited by the
    beam PSF, so this is the honest test signal.
    """
    rng = np.random.default_rng(seed)
    img = rng.random((size, size)).astype(np.float32)
    if blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    return (img - img.min()) / (img.max() - img.min())


def test_required_cv2_symbols_exist():
    missing = [s for s in REQUIRED_CV2_SYMBOLS if not hasattr(cv2, s)]
    assert not missing, f"OpenCV {cv2.__version__} is missing: {missing}"


def test_match_template_peak_is_xy_not_rowcol():
    """cv2.minMaxLoc returns (x, y) — NOT (row, col).

    This is the convention that produces silently plausible wrong answers if you get it backwards.
    The template origin is deliberately ASYMMETRIC (x=60, y=40): a symmetric case cannot catch a swap.
    """
    img = _band_limited_image(blur=0.0)
    x0, y0, w, h = 60, 40, 50, 50
    tpl = img[y0:y0 + h, x0:x0 + w].copy()

    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, peak, _, loc = cv2.minMaxLoc(result)

    assert loc == (x0, y0), f"expected (x,y)=({x0},{y0}), got {loc} — x/y convention changed"
    assert peak > 0.99
    assert result.shape == (img.shape[0] - h + 1, img.shape[1] - w + 1)


def test_inter_area_downscale_shape():
    """INTER_AREA is our forward operator for the 10x magnification step (plan step A3)."""
    img = _band_limited_image(size=1000, blur=2.0)
    small = cv2.resize(img, (100, 100), interpolation=cv2.INTER_AREA)
    assert small.shape == (100, 100)


@pytest.mark.parametrize("mode,tol", [(cv2.MOTION_TRANSLATION, 0.10), (cv2.MOTION_AFFINE, 0.10)])
def test_ecc_recovers_subpixel_shift(mode, tol):
    """findTransformECC must recover a known sub-pixel translation (plan step A9).

    Measured 2026-08-11: TRANSLATION 0.055 px, AFFINE 0.037 px on band-limited data.
    The 0.10 px tolerance is a regression guard, not the achievable accuracy.
    """
    tx, ty = 1.70, -2.30
    img = _band_limited_image(blur=3.0)
    moved = cv2.warpAffine(
        img, np.array([[1, 0, tx], [0, 1, ty]], dtype=np.float32), img.shape[::-1],
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT,
    )
    c = 40  # crop the border, where the warp fabricated content
    a, b = img[c:-c, c:-c], moved[c:-c, c:-c]

    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-8)
    cc, out = cv2.findTransformECC(a, b, warp, mode, criteria, None, 5)

    err = np.hypot(out[0, 2] - tx, out[1, 2] - ty)
    assert cc > 0.9, f"ECC correlation too low: {cc}"
    assert err < tol, f"ECC translation error {err:.4f} px exceeds {tol} px"


def test_phase_cross_correlation_needs_normalization_none_on_blurred_images():
    """The default normalization='phase' FAILS on strongly band-limited images. Use None.

    Phase normalization whitens the spectrum by dividing by magnitude. When the image is blurred,
    the high-frequency magnitudes are ~0, so that division amplifies pure numerical noise and swamps
    the true correlation peak — it returns approximately zero shift.

    Measured 2026-08-11 for a true 2.86 px displacement:

        blur sigma   normalization='phase'    normalization=None
        0.0          0.18 px                  0.16 px
        1.0          0.09 px                  0.02 px
        3.0          2.80 px  <-- FAILS       0.12 px
        6.0          2.84 px  <-- FAILS       0.61 px

    Our search images are blurred by the beam PSF, so this is not hypothetical. Any call to
    phase_cross_correlation in this codebase MUST pass normalization=None. See ADR-0009.
    """
    tx, ty = 1.70, -2.30
    img = _band_limited_image(blur=3.0)
    moved = cv2.warpAffine(
        img, np.array([[1, 0, tx], [0, 1, ty]], dtype=np.float32), img.shape[::-1],
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT,
    )
    c = 40
    a, b = img[c:-c, c:-c], moved[c:-c, c:-c]
    expected = np.array([-ty, -tx])  # skimage returns (row, col) to register b onto a

    good, _, _ = phase_cross_correlation(a, b, upsample_factor=100, normalization=None)
    assert np.hypot(*(good - expected)) < 0.3, f"normalization=None regressed: {good}"

    bad, _, _ = phase_cross_correlation(a, b, upsample_factor=100, normalization="phase")
    assert np.hypot(*(bad - expected)) > 1.0, (
        "normalization='phase' unexpectedly worked on a blurred image. If scikit-image fixed this, "
        "re-benchmark both settings and update ADR-0009 before relying on the default."
    )


def test_phase_cross_correlation_accepts_upsample_factor():
    """Guizar-Sicairos upsampled-DFT refinement is exposed via upsample_factor (plan step A9)."""
    img = _band_limited_image(blur=2.0)
    shift, error, phasediff = phase_cross_correlation(img, img, upsample_factor=100, normalization=None)
    assert np.allclose(shift, 0.0, atol=1e-6)
    assert np.isfinite(error)


def test_torch_is_not_required():
    """The deterministic path must never import torch at module scope (ADR-0006).

    Guards the graded requirement that all dependencies are disclosed and available: if torch leaks
    into the default path, `pip uninstall torch` breaks the submission on the evaluator's machine.
    """
    import sys
    for mod in list(sys.modules):
        if mod == "torch" or mod.startswith("torch."):
            del sys.modules[mod]
    import src.driftlock  # noqa: F401  — importing the package must not pull in torch
    assert "torch" not in sys.modules, "torch was imported at module scope — it must be lazy"
