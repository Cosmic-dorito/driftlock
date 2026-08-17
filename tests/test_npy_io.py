"""`.npy` inputs must behave exactly like the `.png` equivalent.

The organiser's instruction to keep `.npy -> .png` conversion as a separate documented step implies
the evaluation pairs may arrive as raw arrays. The problem statement says an inference script that
needs manual preparation cannot be scored, so `localize.py` reads `.npy` directly and the converter
is for human inspection only.

The load-time assertions use hand-derived values, not values copied from a run (rule R4).
"""

import numpy as np
import pytest

from src.driftlock.io import _load_npy, load_grayscale


@pytest.fixture
def asymmetric():
    """A deliberately asymmetric ramp - a symmetric array cannot catch a transpose."""
    array = np.zeros((6, 4), dtype=np.uint8)
    array[1, 2] = 200
    array[4, 0] = 100
    return array


def test_uint8_array_is_passed_through_unchanged(tmp_path, asymmetric):
    path = tmp_path / "a.npy"
    np.save(path, asymmetric)
    loaded = load_grayscale(path)
    assert loaded.dtype == np.uint8
    assert loaded.shape == (6, 4)          # rows, cols - not transposed
    assert loaded[1, 2] == 200
    assert loaded[4, 0] == 100


def test_unit_range_float_is_rescaled_to_8bit(tmp_path):
    """A float image stored in [0, 1] must be scaled by 255, not clipped to 0/1."""
    path = tmp_path / "f.npy"
    np.save(path, np.array([[0.0, 0.5], [1.0, 0.25]], dtype=np.float32))
    loaded = load_grayscale(path)
    # 0.5 * 255 = 127.5 -> 127 after truncation; 0.25 * 255 = 63.75 -> 63. By hand.
    assert loaded[0, 0] == 0
    assert loaded[0, 1] == 127
    assert loaded[1, 0] == 255
    assert loaded[1, 1] == 63


def test_already_8bit_float_is_not_rescaled(tmp_path):
    """A float array already in [0, 255] must be left alone - rescaling would be 255x wrong."""
    path = tmp_path / "g.npy"
    np.save(path, np.array([[0.0, 128.0], [255.0, 64.0]], dtype=np.float32))
    loaded = load_grayscale(path)
    assert loaded[0, 1] == 128
    assert loaded[1, 1] == 64


def test_nan_and_inf_do_not_propagate(tmp_path):
    """A NaN reaching the matcher poisons the whole correlation surface silently."""
    path = tmp_path / "n.npy"
    np.save(path, np.array([[np.nan, 10.0], [np.inf, -np.inf]], dtype=np.float32))
    loaded = load_grayscale(path)
    assert np.isfinite(loaded).all()
    assert loaded[0, 0] == 0


def test_constant_image_is_not_divided_by_zero(tmp_path):
    path = tmp_path / "c.npy"
    np.save(path, np.zeros((4, 4), dtype=np.float32))
    loaded = load_grayscale(path)
    assert loaded.shape == (4, 4)
    assert (loaded == 0).all()


def test_rgb_npy_is_reduced_to_one_channel(tmp_path):
    path = tmp_path / "rgb.npy"
    np.save(path, np.zeros((5, 3, 3), dtype=np.uint8))
    assert load_grayscale(path).ndim == 2


def test_bad_dimensionality_is_rejected_with_a_useful_message(tmp_path):
    path = tmp_path / "bad.npy"
    np.save(path, np.zeros((2, 2, 2, 2), dtype=np.uint8))
    with pytest.raises(ValueError, match="2-D or 3-D"):
        _load_npy(path)


@pytest.mark.slow
def test_npy_and_png_inputs_give_identical_coordinates(tmp_path):
    """The end-to-end guarantee: converting first must not change the answer.

    This is the claim the submission actually rests on - that Applied Materials can hand the
    inference script either form. Compared with repr, not approx: "close" would leave open the
    possibility of a systematic half-pixel shift between the two paths.
    """
    import argparse
    from pathlib import Path

    import cv2

    import localize as L
    from src.driftlock.io import read_manifest, resolve_manifest_path
    from src.driftlock.match import localize as run

    manifest = Path(__file__).resolve().parents[1] / "data" / "bench" / "manifest.csv"
    if not manifest.exists():
        pytest.skip("bench split not generated")
    cfg = L.build_config(argparse.Namespace(config="driftlock"))

    for row in list(read_manifest(manifest))[:3]:
        ref_png = resolve_manifest_path(manifest, row["reference_path"])
        search_png = resolve_manifest_path(manifest, row["search_path"])

        ref_npy = tmp_path / f"{row['id']}_ref.npy"
        search_npy = tmp_path / f"{row['id']}_search.npy"
        np.save(ref_npy, cv2.imread(str(ref_png), cv2.IMREAD_UNCHANGED))
        np.save(search_npy, cv2.imread(str(search_png), cv2.IMREAD_UNCHANGED))

        from_png = run(load_grayscale(ref_png), load_grayscale(search_png), cfg)
        from_npy = run(load_grayscale(ref_npy), load_grayscale(search_npy), cfg)
        assert (repr(from_png.x), repr(from_png.y)) == (repr(from_npy.x), repr(from_npy.y)), (
            f"pair {row['id']}: png {from_png.x},{from_png.y} vs npy {from_npy.x},{from_npy.y}"
        )
