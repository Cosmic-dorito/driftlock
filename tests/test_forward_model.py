"""Geometry of the forward operator and of pose measurement.

Same discipline as ``test_geometry.py`` (rule R4): every case is **asymmetric** so an x/y swap
cannot pass, and every expected value is **derived by hand from the model**, never copied from what
the code printed. A test written by running the code and pasting its output tests nothing.

What is at stake here. ``build_template`` maps the reference into the search image's domain, and a
half-pixel error in that mapping is half of the entire sub-pixel budget - it would show up as a
mysterious accuracy ceiling rather than as a failure, which is the worst way to find a bug.
"""

from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from src.driftlock.match import area_kernel, build_template  # noqa: E402
from src.driftlock.pose import estimate_pose_fourier_mellin  # noqa: E402


class TestAreaKernel:
    """The detector integrates over its own footprint. The kernel must be exact and centred."""

    def test_sums_to_one(self):
        for width in (1.0, 2.0, 9.3, 10.0, 11.7):
            assert area_kernel(width).sum() == pytest.approx(1.0, abs=1e-6)

    def test_is_symmetric_so_it_introduces_no_shift(self):
        # An asymmetric kernel would translate the template, i.e. bias every reported coordinate.
        # This is precisely what cv2.blur's integer anchor does at even sizes.
        for width in (9.3, 10.0, 11.7):
            k = area_kernel(width)
            assert k == pytest.approx(k[::-1], abs=1e-7)

    def test_integer_width_ten_has_half_weights_at_the_ends(self):
        # Hand-derived: a box of width 10 centred on a pixel covers [-5, 5]. Pixel d spans
        # [d-0.5, d+0.5], so d = -5 contributes the overlap [-5, -4.5] = 0.5 of a pixel, and
        # d = 0..±4 contribute a full pixel each. Total 0.5+9+0.5 = 10 -> normalise by 10.
        k = area_kernel(10.0)
        assert len(k) == 11
        assert k[0] == pytest.approx(0.05, abs=1e-6)   # 0.5 / 10
        assert k[5] == pytest.approx(0.10, abs=1e-6)   # 1.0 / 10  (centre)
        assert k[-1] == pytest.approx(0.05, abs=1e-6)


class TestBuildTemplateGeometry:
    def test_template_centre_maps_to_reference_centre(self):
        """A bright block at an ASYMMETRIC reference position lands where the model says.

        Hand-derived. With ``scale = 10`` and ``out_size = 100`` the affine is
        ``x_ref = (1000-1)/2 + 10 * (u - (100-1)/2)``, i.e. ``x_ref = 499.5 + 10*(u - 49.5)``.
        Inverting for a feature at ``x_ref = 700``:  ``u = (700 - 499.5)/10 + 49.5 = 69.55``.
        For ``y_ref = 300``:                        ``v = (300 - 499.5)/10 + 49.5 = 29.55``.

        x and y are deliberately different, so a swap gives (29.55, 69.55) and fails.
        """
        reference = np.zeros((1000, 1000), dtype=np.float32)
        reference[295:306, 695:706] = 255.0  # centred on (x=700, y=300)

        template = build_template(reference, scale=10.0, rotation_deg=0.0, out_size=100)

        total = template.sum()
        ys, xs = np.mgrid[0:template.shape[0], 0:template.shape[1]]
        cx = float((template * xs).sum() / total)
        cy = float((template * ys).sum() / total)

        assert cx == pytest.approx(69.55, abs=0.05)
        assert cy == pytest.approx(29.55, abs=0.05)

    def test_non_integer_scale_is_actually_honoured(self):
        """The bug this replaced: INTER_AREA quantised scale to 1000/n, about 1% steps.

        9.30 and 9.35 differ by 0.5%, which is inside one of those steps - the old builder returned
        an identical template for both. Correlation loses its peak at ~1.3% scale error, so a
        builder that cannot represent 0.5% cannot be steered by any pose search.
        """
        rng = np.random.default_rng(20260812)
        reference = rng.random((1000, 1000)).astype(np.float32)

        a = build_template(reference, scale=9.30, out_size=100)
        b = build_template(reference, scale=9.35, out_size=100)

        assert a.shape == b.shape == (100, 100)
        assert not np.allclose(a, b), "template must change when scale changes by 0.5%"

    def test_out_size_is_honoured_so_the_score_stays_smooth(self):
        rng = np.random.default_rng(7)
        reference = rng.random((1000, 1000)).astype(np.float32)
        for scale in (9.0, 9.7, 10.4, 11.0):
            assert build_template(reference, scale, out_size=100).shape == (100, 100)

    def test_rotation_turns_the_content_the_expected_way(self):
        """A feature on the +x axis of the reference must move to -y under a positive rotation.

        Hand-derived from the inverse map ``x_ref = cx + s*(cos*du - sin*dv)``,
        ``y_ref = cy + s*(sin*du + cos*dv)``. Solving for the template offset ``(du, dv)`` that
        reaches a reference feature at ``(+d, 0)`` gives ``du = +d*cos/s``, ``dv = -d*sin/s``.
        So with a positive rotation the feature appears ABOVE the template centre (dv < 0, y down).
        """
        reference = np.zeros((1000, 1000), dtype=np.float32)
        # Asymmetric: purely on the +x axis, 300 px right of centre (499.5, 499.5).
        reference[494:506, 794:806] = 255.0

        template = build_template(reference, scale=10.0, rotation_deg=10.0, out_size=100)
        ys, xs = np.mgrid[0:100, 0:100]
        total = template.sum()
        cx = float((template * xs).sum() / total)
        cy = float((template * ys).sum() / total)

        # du = 300*cos(10)/10 = 29.54 -> u = 49.5 + 29.54 = 79.04
        # dv = -300*sin(10)/10 = -5.21 -> v = 49.5 - 5.21 = 44.29
        assert cx == pytest.approx(79.04, abs=0.3)
        assert cy == pytest.approx(44.29, abs=0.3)


class TestPoseMeasurement:
    """The pose estimator must recover a magnification and rotation we imposed ourselves."""

    def _lattice(self, size: int, pitch_x: float, pitch_y: float) -> np.ndarray:
        """A 2D grid with deliberately DIFFERENT pitches per axis, so an axis swap is visible."""
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        img = (np.cos(2 * np.pi * xx / pitch_x) + np.cos(2 * np.pi * yy / pitch_y))
        return ((img + 2.0) * 60.0).astype(np.float32)

    def test_recovers_a_known_scale_and_rotation(self):
        # Reference lattice at 1 nm/px with unequal pitches (asymmetric on purpose).
        reference = self._lattice(1000, pitch_x=64.0, pitch_y=96.0)

        scale, rotation = 9.7, 1.3
        # Build the "search" image by the same affine the generator uses, so the truth is exact.
        theta = np.deg2rad(rotation)
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        big = self._lattice(10000, pitch_x=64.0, pitch_y=96.0)
        half, centre = 500.0, 5000.0
        m = np.array([
            [scale * cos_t, -scale * sin_t, centre - scale * (cos_t * half - sin_t * half)],
            [scale * sin_t, scale * cos_t, centre - scale * (sin_t * half + cos_t * half)],
        ], dtype=np.float32)
        search = cv2.warpAffine(big, m, (1000, 1000),
                                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                borderMode=cv2.BORDER_REFLECT)

        estimate = estimate_pose_fourier_mellin(reference, search)
        assert estimate is not None
        assert estimate.scale == pytest.approx(scale, rel=0.01)
        # Sign matters: getting it backwards returns -1.3 and doubles the error instead of
        # removing it. Measured on real pairs as r = -0.899 before the sign was corrected.
        assert estimate.rotation_deg == pytest.approx(rotation, abs=0.3)


class TestDriftVersusRotation:
    """A rotation and a drifting scan produce the SAME row-to-row displacement.

    This is the interaction that made every rotated pair wrong while the sponsor's data stayed
    clean, because the sponsor's generator produces no rotation at all (H9). The expected values
    below are derived from the geometry, not read off the implementation.
    """

    def _striped_view(self, rotation_deg: float) -> np.ndarray:
        """A field of vertical lines, sampled through a rotation and with NO scan drift."""
        from src.synth import imaging

        canvas = np.zeros((4000, 4000), dtype=np.float32)
        canvas[:, ::40] = 255.0          # vertical lines: pure du/dv signal
        canvas[::400, :] = 120.0         # a little horizontal content so rows are not degenerate
        return imaging.resample_field_of_view(
            canvas, out_size=1000, nm_per_px=2.0,
            rotation_deg=rotation_deg, centre_nm=(2000.0, 2000.0),
        )

    # These two pin the estimator's MATHEMATICS, which is independent of the row separation, so
    # they name the gap explicitly rather than inheriting the default. The default gap is an
    # operating point chosen for robustness on real data (ADR-0022) and it moved once already;
    # a test of the maths must not fail when that happens, and must not be silently loosened to
    # accommodate it either. `test_gap_respects_the_saturation_bound` covers the operating point.
    DERIVATION_GAP = 100

    def test_uncompensated_rotation_is_reported_as_drift(self):
        """Hand-derived: a vertical canvas line satisfies cos*(u-h) - sin*(v-h) = const,
        so du/dv = tan(rho). Over ``gap`` rows the content moves ``gap*tan(rho)`` sideways, and
        ``estimate_shear`` scales that to the full height as ``-tan(rho)*(H-1)``.
        For rho = 1 deg and H = 1000 that is -0.017455 * 999 = **-17.44 px** of pure artefact.
        """
        from src.driftlock.drift import estimate_shear

        spurious = estimate_shear(self._striped_view(1.0), gap=self.DERIVATION_GAP,
                                  rotation_deg=0.0)
        assert spurious is not None
        assert spurious == pytest.approx(-17.44, abs=3.0)

    def test_compensated_rotation_reports_no_drift(self):
        """The same image, told the rotation: the artefact must cancel to about zero."""
        from src.driftlock.drift import estimate_shear

        corrected = estimate_shear(self._striped_view(1.0), gap=self.DERIVATION_GAP,
                                   rotation_deg=1.0)
        assert corrected is not None
        # There is no drift in this image, so anything much above a pixel is a failure.
        assert abs(corrected) < 2.0

    def test_gap_respects_the_saturation_bound(self):
        """The row separation must keep the rotation-induced displacement inside the lag search.

        This is the constraint that the old default violated (ADR-0022). A tilt of rho moves
        content ``gap*tan(rho)`` sideways per row-pair; if that exceeds ``max_lag`` the correlation
        peak clips at the edge of its own search window and the estimate saturates. At the old
        gap=100 a 2 degree tilt gives 3.49 px against max_lag=3 - infeasible, and the measured
        standard deviation of the estimate was 13-20 px on rotated data.

        Hand-derived expectations, not copied from the implementation:
            gap_for_rotation(2.0) = (3 - 1.5) / tan(2 deg) = 1.5 / 0.034921 = 42.9 -> 42
        """
        from src.driftlock.drift import DEFAULT_MAX_LAG, gap_for_rotation

        assert gap_for_rotation(2.0) == pytest.approx(42, abs=1)

        # Whatever the rotation, the chosen gap must satisfy the bound it was derived from.
        for rotation in (0.25, 0.5, 1.0, 1.5, 2.0):
            gap = gap_for_rotation(rotation)
            displacement = gap * np.tan(np.deg2rad(rotation))
            assert displacement + 1.5 <= DEFAULT_MAX_LAG + 1e-6, (
                f"rotation {rotation} deg with gap {gap} displaces {displacement:.2f} px, "
                f"which does not fit inside max_lag {DEFAULT_MAX_LAG}"
            )

        # With no tilt there is nothing to saturate, so the long, low-noise baseline is used.
        assert gap_for_rotation(0.0) == 100
        assert gap_for_rotation(None) > 0

    def test_sign_is_not_symmetric(self):
        """Asymmetric on purpose: +1 deg and -1 deg must give OPPOSITE spurious shears.

        A sign error that squared or absolute-valued the term would pass a single-sign test.
        """
        from src.driftlock.drift import estimate_shear

        plus = estimate_shear(self._striped_view(1.0), rotation_deg=0.0)
        minus = estimate_shear(self._striped_view(-1.0), rotation_deg=0.0)
        assert plus is not None and minus is not None
        assert plus * minus < 0, "spurious shear must flip sign with the rotation"
