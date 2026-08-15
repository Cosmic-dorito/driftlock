"""The scan-field calibration must recover a jitter we chose ourselves.

Every expected value here is derived by hand from the generator's own formula, never by running the
estimator and pasting what it printed (R4). The sign convention gets its own test because getting it
backwards does not fail loudly - it doubles the distortion instead of removing it, and the pipeline
would simply score a little worse with no error anywhere.

The offsets used are deliberately asymmetric in y (a ramp plus a fixed pattern, not a symmetric
bump), because a field that is symmetric about the image centre cannot catch a flipped row index.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.driftlock.scanfield import (
    apply_scan_field,
    calibrate,
    estimate_period,
    estimate_scan_field,
)

PERIOD = 8.0
SIZE = 512


def periodic_canvas(period: float = PERIOD, size: int = SIZE) -> np.ndarray:
    """A doubly periodic lattice with an aperiodic thumbprint, like the real thing.

    Pure sinusoids would let the estimator succeed for the wrong reason - any lag that is a whole
    number of periods scores identically - so the canvas carries a slow aperiodic envelope as well.
    """
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    lattice = (110.0
               + 55.0 * np.cos(2 * np.pi * xs / period)
               + 40.0 * np.cos(2 * np.pi * ys / period)
               + 22.0 * np.cos(2 * np.pi * (xs + ys) / (period * 2.0)))
    envelope = 18.0 * np.sin(2 * np.pi * xs / (size / 1.7)) * np.cos(2 * np.pi * ys / (size / 2.3))
    return np.clip(lattice + envelope, 0, 255).astype(np.float32)


def shear_rows(image: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """The generator's raster stage, verbatim: ``out[y, x] = clean[y, x + offset_y]``."""
    height, width = image.shape
    map_x = np.arange(width, dtype=np.float32)[None, :] + offsets.astype(np.float32)[:, None]
    map_y = np.tile(np.arange(height, dtype=np.float32)[:, None], (1, width))
    return cv2.remap(image, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def test_period_is_recovered_from_a_canvas_we_built() -> None:
    """The canvas is built at period 8.0, so nothing else is an acceptable answer."""
    assert estimate_period(periodic_canvas()) == pytest.approx(PERIOD, abs=0.15)


def test_apply_undoes_the_generator_and_the_opposite_sign_does_not() -> None:
    """``apply_scan_field(shear_rows(I, s), s)`` must return I - and ``-s`` must not.

    Asserting only "the restored image is close to the original" cannot be made both correct and
    tight here: a +-1.5 px bilinear round trip is genuinely lossy on a lattice with amplitude 55 and
    a period of 8, so the residual is a few grey levels even when the sign is right. The
    discriminating comparison is against the FLIPPED field, which leaves a 2s displacement and an
    error an order of magnitude larger. A sign error is otherwise silent: the pipeline would score
    slightly worse with no exception anywhere.
    """
    clean = periodic_canvas()
    offsets = np.zeros(SIZE)
    offsets[100] = 1.5           # asymmetric on purpose: one row, well away from centre
    offsets[400] = -2.0
    distorted = shear_rows(clean, offsets)

    # Only the two rows we displaced can differ, so score on those rather than diluting the
    # comparison with 510 identical ones.
    rows = [100, 400]
    inner = slice(8, SIZE - 8)
    right = np.abs(apply_scan_field(distorted, offsets)[rows, inner] - clean[rows, inner]).mean()
    wrong = np.abs(apply_scan_field(distorted, -offsets)[rows, inner] - clean[rows, inner]).mean()

    assert right < 0.25 * wrong, f"correct sign {right:.2f}, flipped sign {wrong:.2f}"
    assert right < 5.0, f"round-trip residual {right:.2f} grey levels is larger than interpolation"


def test_estimator_recovers_a_jitter_we_chose() -> None:
    """A known zero-mean per-row jitter must come back with most of its energy removed."""
    rng = np.random.default_rng(20260815)
    clean = periodic_canvas()
    truth = rng.normal(0.0, 0.5, size=SIZE)
    truth -= np.median(truth)                       # the estimator can only see the residual

    measured = estimate_scan_field(shear_rows(clean, truth))
    assert measured.applied, measured.reason

    before = float(np.sqrt(np.mean(truth ** 2)))
    after = float(np.sqrt(np.mean((truth - measured.offsets) ** 2)))
    assert after < 0.5 * before, f"residual {after:.3f} px vs input {before:.3f} px"


def test_a_featureless_image_is_declined_rather_than_warped() -> None:
    """No periodicity means no ruler, and the correct output is the image untouched.

    Declining has to be a real branch: a calibration that always fires would, on the one operating
    point where it has nothing to measure, inject noise into an image that was fine.
    """
    flat = np.full((SIZE, SIZE), 128.0, dtype=np.float32)
    out, measured = calibrate(flat)
    assert not measured.applied
    assert out is flat


def test_estimating_twice_gives_the_same_field() -> None:
    """Determinism: the calibration runs before any candidate exists, so it must not wander."""
    image = shear_rows(periodic_canvas(), np.linspace(-0.6, 0.6, SIZE))
    first = estimate_scan_field(image)
    second = estimate_scan_field(image)
    assert np.array_equal(first.offsets, second.offsets)
