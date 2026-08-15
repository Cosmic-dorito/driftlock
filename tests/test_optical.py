"""The RGB optical modality, checked against physics we can compute by hand.

Every expected value here is derived from a formula, not from running the code and pasting what it
printed (R4). Two of these tests would have caught real defects: the channel-order test catches an
RGB/BGR swap on save, which produces a perfectly self-consistent dataset whose every figure is
wrong, and the diffraction test pins the constant that decides whether the structure is visible at
all.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.driftlock.color import LUMA_RGB, contrast_projection, project, to_matcher_input
from src.synth import optical


def test_rayleigh_limit_matches_the_textbook_formula() -> None:
    """0.61 * 550 / 0.90 = 372.8 nm. This is the number that makes the modality different."""
    assert optical.rayleigh_resolution_nm(550.0, 0.90) == pytest.approx(372.78, abs=0.01)


def test_the_dram_pitch_is_below_the_optical_resolution_limit() -> None:
    """A 64 nm word-line pitch against a 373 nm limit - the lattice is absent, not blurred.

    This is the fact the whole optical design rests on, so it is asserted rather than assumed: if
    someone later raises NA far enough to resolve the cell array, the modality's rationale changes
    and this test should fail and make them say so.
    """
    dram_word_line_pitch_nm = 64.0
    assert optical.rayleigh_resolution_nm(550.0, 0.90) > 5 * dram_word_line_pitch_nm


def test_thin_film_reflectance_is_periodic_in_optical_thickness() -> None:
    """Interference repeats when 4*pi*n*d/lambda advances by 2*pi, i.e. every d = lambda/(2n).

    Hand-derived: at lambda = 600 and n = 1.5 the period is 200 nm, so d and d+200 must match.
    """
    lam, index = 600.0, 1.5
    period = lam / (2 * index)
    a = optical.film_reflectance(150.0, lam, index)
    b = optical.film_reflectance(150.0 + period, lam, index)
    assert a == pytest.approx(b, abs=1e-6)


def test_channels_differ_for_the_same_material() -> None:
    """A single film thickness must produce three different reflectances, or colour is decoration.

    Chosen so the phase differs substantially across the band: at d = 200 nm and n = 1.46 the
    optical thickness is 292 nm, which is a different fraction of a wavelength for each channel.
    """
    values = [optical.film_reflectance(200.0, wl, 1.46) for wl in optical.CHANNEL_WAVELENGTHS_NM]
    assert max(values) - min(values) > 0.05, values


def test_blue_is_sharper_than_red() -> None:
    """PSF width scales with wavelength, so the 465 nm channel must resolve finer than 610 nm."""
    red = optical.airy_sigma_px(610.0, 0.9, 25.0)
    blue = optical.airy_sigma_px(465.0, 0.9, 25.0)
    assert blue < red
    assert blue / red == pytest.approx(465.0 / 610.0, rel=1e-6)


def test_optical_render_produces_three_distinct_channels() -> None:
    canvas = np.zeros((256, 256), dtype=np.float32)
    canvas[:, 64:128] = 85.0
    canvas[:, 128:192] = 170.0
    canvas[64:96, :] = 255.0
    rgb = optical.render_optical(canvas, optical.OpticalParams())
    assert rgb.shape == (256, 256, 3)
    stds = [float(rgb[..., c].std()) for c in range(3)]
    assert min(stds) > 0.5, stds
    # If two channels were identical the colour would be carrying no extra information.
    assert not np.allclose(rgb[..., 0], rgb[..., 2], atol=1.0)


def test_channel_zero_is_the_red_band() -> None:
    """Index 0 must be the LONGEST wavelength. Getting this backwards is silent.

    An RGB/BGR mix-up produces a dataset that is entirely self-consistent - the localizer would not
    care - while every rendered figure shows the wrong colours. The ordering is therefore pinned to
    the wavelength table rather than left as a convention.
    """
    assert optical.CHANNEL_WAVELENGTHS_NM[0] > optical.CHANNEL_WAVELENGTHS_NM[2]


def test_contrast_projection_finds_the_axis_the_materials_differ_along() -> None:
    """Build an image whose materials differ ONLY in blue, and the measured axis must be blue.

    Luminance weights blue at 0.114, so a fixed conversion would keep 11% of this contrast. That
    gap is the entire argument for measuring the projection instead of assuming it.
    """
    rng = np.random.default_rng(20260815)
    image = np.zeros((200, 200, 3), dtype=np.float32)
    image[..., 0] = 120.0
    image[..., 1] = 120.0
    image[..., 2] = 60.0
    image[:, 100:, 2] = 200.0                      # asymmetric: the split is not at the centre
    image += rng.normal(0.0, 1.0, image.shape).astype(np.float32)

    direction = contrast_projection(image)
    assert abs(direction[2]) > 0.9, direction
    assert float(np.linalg.norm(direction)) == pytest.approx(1.0, abs=1e-6)


def test_measured_projection_beats_luminance_on_contrast_to_noise() -> None:
    """The gain is in contrast-to-NOISE, not in contrast, and the distinction is not pedantic.

    ``project`` rescales its output to 0-255, so on a noiseless two-material image both projections
    span the full range and look identical - the first version of this test asserted the wrong thing
    and failed with ``255.0 > 255.0``. What the measured axis actually buys is alignment: it puts
    the signal where the materials differ, while luminance weights blue at 0.114 and so keeps a
    ninth of a blue-only contrast while admitting all three channels' noise.
    """
    rng = np.random.default_rng(7)
    image = np.zeros((160, 160, 3), dtype=np.float32)
    image[..., :] = (120.0, 120.0, 60.0)
    image[:, 90:, 2] = 200.0                       # asymmetric split, blue-only contrast
    image += rng.normal(0.0, 6.0, image.shape).astype(np.float32)

    def cnr(plane: np.ndarray) -> float:
        left, right = plane[:, :80], plane[:, 100:]
        noise = 0.5 * (left.std() + right.std())
        return abs(float(right.mean() - left.mean())) / max(float(noise), 1e-9)

    measured = cnr(project(image, contrast_projection(image)))
    luma = cnr(project(image, LUMA_RGB / np.linalg.norm(LUMA_RGB)))
    assert measured > 1.5 * luma, f"measured CNR {measured:.1f} vs luma {luma:.1f}"


def test_grayscale_input_passes_through_unchanged() -> None:
    """The colour path must be a no-op on the SEM task, which is the graded one."""
    gray = np.arange(64, dtype=np.float32).reshape(8, 8)
    ref, search = to_matcher_input(gray, gray * 2.0)
    assert np.array_equal(ref, gray)
    assert np.array_equal(search, gray * 2.0)
