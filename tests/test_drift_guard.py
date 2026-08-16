"""The drift guard: reject an implausible shear rather than apply it.

Expected values here are hand-derived from the correction formula, not copied from a run
(rule R4). The correction is::

    x_corrected = x + shear * (y / (H - 1))

so with ``H = 1000`` and ``y = 999`` the factor is exactly ``999/999 = 1``, and the corrected
x is ``x + shear``. That choice of y makes the arithmetic checkable by eye, and y != H/2 keeps
the case asymmetric so a y/x transposition cannot pass.
"""

import numpy as np
import pytest

import src.driftlock.drift as drift


@pytest.fixture
def image():
    """Content is irrelevant - the shear estimator is stubbed in every test below."""
    return np.zeros((1000, 1000), dtype=np.float32)


def test_correct_for_drift_is_the_documented_formula():
    # 100 + 3.0 * (999/999) = 103.0, by hand.
    assert drift.correct_for_drift(100.0, 999.0, 3.0, 1000) == pytest.approx(103.0)
    # Half height: 100 + 3.0 * (499.5/999) = 100 + 1.5 = 101.5, by hand.
    assert drift.correct_for_drift(100.0, 499.5, 3.0, 1000) == pytest.approx(101.5)


def test_guard_disabled_by_default_applies_a_large_shear(monkeypatch, image):
    """max_shear_px=0 must reproduce the pre-guard behaviour exactly."""
    monkeypatch.setattr(drift, "estimate_drift_shear", lambda *a, **k: 24.0)
    x, shear = drift.estimate_and_correct(image, 100.0, 999.0)
    assert x == pytest.approx(124.0)          # 100 + 24.0, by hand
    assert shear == pytest.approx(24.0)


def test_guard_rejects_an_implausible_shear(monkeypatch, image):
    monkeypatch.setattr(drift, "estimate_drift_shear", lambda *a, **k: 24.0)
    x, shear = drift.estimate_and_correct(image, 100.0, 999.0, max_shear_px=4.0)
    assert x == pytest.approx(100.0)          # unchanged
    assert shear is None                      # signals "abandoned", as when estimation fails


def test_guard_passes_a_plausible_shear_through_unchanged(monkeypatch, image):
    """A legitimate correction must be unaffected by the guard being on."""
    monkeypatch.setattr(drift, "estimate_drift_shear", lambda *a, **k: 1.5)
    x, shear = drift.estimate_and_correct(image, 100.0, 999.0, max_shear_px=4.0)
    assert x == pytest.approx(101.5)          # 100 + 1.5, by hand
    assert shear == pytest.approx(1.5)


def test_guard_is_two_sided(monkeypatch, image):
    """Drift can run either way; the bound is on magnitude."""
    monkeypatch.setattr(drift, "estimate_drift_shear", lambda *a, **k: -24.0)
    x, shear = drift.estimate_and_correct(image, 100.0, 999.0, max_shear_px=4.0)
    assert x == pytest.approx(100.0)
    assert shear is None


def test_guard_boundary_is_inclusive(monkeypatch, image):
    """Exactly at the threshold is still applied - the rejection is strictly greater-than."""
    monkeypatch.setattr(drift, "estimate_drift_shear", lambda *a, **k: 4.0)
    x, shear = drift.estimate_and_correct(image, 100.0, 999.0, max_shear_px=4.0)
    assert x == pytest.approx(104.0)          # 100 + 4.0, by hand
    assert shear == pytest.approx(4.0)
