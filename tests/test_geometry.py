"""Coordinate-convention tests. The highest-value tests in the project.

The failure mode this guards against is not a bad match - it is a convention bug that produces
confident, plausible, wrong answers and passes every test whose ground truth happens to be
symmetric. So:

* Every case here is DELIBERATELY ASYMMETRIC (x != y, width != height where it matters). A test with
  ground truth at (500, 500) cannot detect an x/y swap.
* Every expected value is DERIVED BY HAND from the problem statement, never copied from what the
  code currently prints. A test written by running the code and pasting its output tests nothing.

Reference: the spec says origin (0,0) is top-left, x increases right, y increases down, and the
output is the centre of the matched region in search-image pixels (docs/SPEC.md section 2).
"""

import numpy as np
import pytest

from src.driftlock.io import (
    Match,
    centre_to_top_left,
    euclidean_error,
    match_template_peak_to_centre,
    rowcol_to_xy,
    top_left_to_centre,
    xy_to_rowcol,
)

cv2 = pytest.importorskip("cv2")


class TestAxisOrder:
    """x is horizontal, y is vertical. Asymmetric values throughout."""

    def test_rowcol_to_xy_swaps(self):
        # An element at row 300, column 700 is at x=700, y=300. If these were equal the test
        # would pass under a swap, which is exactly the bug we are hunting.
        assert rowcol_to_xy(row=300, col=700) == (700.0, 300.0)

    def test_xy_to_rowcol_swaps(self):
        assert xy_to_rowcol(x=700, y=300) == (300.0, 700.0)

    def test_round_trip(self):
        assert rowcol_to_xy(*xy_to_rowcol(123.5, 876.25)) == (123.5, 876.25)


class TestCentreConvention:
    """centre = origin + size/2, fixed empirically by H2 (results/hypotheses.md)."""

    def test_hundred_pixel_box_matches_ground_truth_formula(self):
        # H2, verified on 40 real pairs: gt_centre == gt_box_origin + 50 for a 100 px box.
        # Hand-derived: origin (240, 810) -> centre (290, 860).
        assert top_left_to_centre(240.0, 810.0, 100.0, 100.0) == (290.0, 860.0)

    def test_not_the_size_minus_one_convention(self):
        # The alternative convention would give origin + 49.5 and be half a pixel off - which
        # matters enormously when the pass threshold is 1 px. Pin the choice explicitly.
        cx, _ = top_left_to_centre(240.0, 810.0, 100.0, 100.0)
        assert cx == 290.0
        assert cx != 240.0 + (100.0 - 1.0) / 2.0

    def test_non_square_template_uses_the_right_axis(self):
        # width=80 -> x + 40 ; height=120 -> y + 60. Swapping width and height would give
        # (300, 870) instead of (280, 890), so this case distinguishes them.
        assert top_left_to_centre(240.0, 830.0, 80.0, 120.0) == (280.0, 890.0)

    def test_centre_to_top_left_inverts(self):
        assert centre_to_top_left(290.0, 860.0, 100.0, 100.0) == (240.0, 810.0)


class TestMatchTemplatePeakConversion:
    """cv2.minMaxLoc returns (x, y); array.shape is (height, width). Both easy to get backwards."""

    def test_peak_to_centre_hand_derived(self):
        # Peak at (x=240, y=810) with a 100x100 template -> centre (290, 860).
        assert match_template_peak_to_centre((240, 810), (100, 100)) == (290.0, 860.0)

    def test_peak_to_centre_non_square(self):
        # template_shape is numpy-ordered (height=120, width=80).
        # Correct: x = 240 + 80/2 = 280 ; y = 810 + 120/2 = 870.
        # Reading the shape backwards would give (300, 850).
        assert match_template_peak_to_centre((240, 810), (120, 80)) == (280.0, 870.0)

    def test_against_real_opencv_output(self):
        """End-to-end: plant a template at a known asymmetric position and recover its centre.

        This is the test that would actually catch a swap in real usage, because it runs the same
        OpenCV call the matcher uses rather than trusting our arithmetic in isolation.
        """
        rng = np.random.default_rng(20260811)
        search = rng.random((600, 900)).astype(np.float32)  # note: non-square image too

        x0, y0, w, h = 310, 120, 100, 100  # asymmetric origin
        template = search[y0:y0 + h, x0:x0 + w].copy()

        result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, _, _, loc = cv2.minMaxLoc(result)

        cx, cy = match_template_peak_to_centre(loc, template.shape)
        assert (cx, cy) == (x0 + 50.0, y0 + 50.0) == (360.0, 170.0)


class TestErrorMetric:
    def test_euclidean_error_is_a_3_4_5_triangle(self):
        # dx = 3, dy = 4 -> 5. Asymmetric so a swapped implementation still gives 5 here;
        # that is fine, this test is about the formula, and the swap is covered above.
        assert euclidean_error((103.0, 204.0), (100.0, 200.0)) == pytest.approx(5.0)

    def test_zero_error(self):
        assert euclidean_error((312.42, 489.07), (312.42, 489.07)) == pytest.approx(0.0)


class TestStdoutFormat:
    """Single-pair mode must print exactly 'x,y' - benchmark parsers break on anything else."""

    def test_format_is_x_comma_y(self):
        assert Match(x=312.4249, y=489.0651).as_stdout_line() == "312.42,489.07"

    def test_x_comes_first(self):
        # Asymmetric on purpose: a swapped implementation would print "489.00,312.00".
        assert Match(x=312.0, y=489.0).as_stdout_line() == "312.00,489.00"

    def test_no_whitespace_or_brackets(self):
        line = Match(x=1.0, y=2.0).as_stdout_line()
        assert line == "1.00,2.00"
        assert " " not in line and "(" not in line


class TestGroundTruthConsistency:
    """Cross-check the convention against the sponsor's real manifest, if it has been generated."""

    def test_manifest_centre_equals_origin_plus_half_box(self):
        from pathlib import Path

        from src.driftlock.io import read_manifest

        manifest = Path(__file__).resolve().parents[1] / "data" / "_sponsor" / "verify" / "manifest.csv"
        if not manifest.exists():
            pytest.skip("sponsor verification data not generated; see scripts/verify_hypotheses.py")

        rows = read_manifest(manifest)
        assert rows, "manifest is empty"
        for row in rows:
            cx, cy = top_left_to_centre(
                float(row["gt_box_x"]), float(row["gt_box_y"]),
                float(row["gt_box_w"]), float(row["gt_box_h"]),
            )
            assert cx == pytest.approx(float(row["gt_x"]), abs=1e-9)
            assert cy == pytest.approx(float(row["gt_y"]), abs=1e-9)


def test_barrel_map_point_is_the_inverse_of_the_remap():
    """The GT transform must undo exactly what cv2.remap does, not merely resemble it.

    Hand-derived, per R4. barrel_distortion tells remap: output pixel p samples source
    c + (p - c)(1 + k*rn_p^2). So a feature at source s appears at the p solving that equation.
    Pick p first, compute the s it implies by hand, then require barrel_map_point(s) == p.

    Asymmetric on purpose: a point on a diagonal with different x and y offsets cannot pass if the
    axes are swapped or if only one is normalised.
    """
    import numpy as np

    from src.synth.imaging import barrel_map_point

    size, k = 1000, 0.05
    c = (size - 1) / 2.0
    px, py = c + 300.0, c - 120.0          # deliberately not symmetric, not on an axis
    nx, ny = (px - c) / c, (py - c) / c
    factor = 1.0 + k * (nx * nx + ny * ny)
    sx, sy = c + (px - c) * factor, c + (py - c) * factor

    got_x, got_y = barrel_map_point(sx, sy, (size, size), k)
    assert np.isclose(got_x, px, atol=1e-6), f"x: {got_x} != {px}"
    assert np.isclose(got_y, py, atol=1e-6), f"y: {got_y} != {py}"

    # Content moves INWARD under barrel (k > 0): that sign was the whole bug.
    assert abs(got_x - c) < abs(sx - c)
    assert abs(got_y - c) < abs(sy - c)
    # k = 0 must be exactly the identity, including for the centre pixel.
    assert barrel_map_point(123.4, 567.8, (size, size), 0.0) == (123.4, 567.8)
