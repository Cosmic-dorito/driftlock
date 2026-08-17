"""Image loading, manifest handling, and THE coordinate convention.

This is the only module in the project permitted to convert between array indexing and problem
coordinates (ADR-0007). Everywhere else works in one space or the other and calls in here to cross
over. One conversion site means one place to test, and one place to be wrong.

Why that matters here specifically
----------------------------------
OpenCV and numpy index arrays as ``[row, col]`` = ``[y, x]``. The problem statement wants ``(x, y)``
with the origin at the top-left, x increasing right and y increasing down. An x/y swap produces
confident, plausible, completely wrong answers, and it passes any test whose ground truth happens to
be symmetric. ``tests/test_geometry.py`` therefore uses deliberately asymmetric cases.

The half-pixel question, settled empirically
--------------------------------------------
For a template of size ``(w, h)`` placed with its top-left corner at ``(x0, y0)``, is the centre
``x0 + w/2`` or ``x0 + (w-1)/2``? Both are defensible a priori and they differ by half a pixel -
which is enormous when the pass threshold is 1 px.

Hypothesis H2, verified against 40 real pairs (see ``results/hypotheses.md``), shows the ground
truth satisfies ``gt_centre == gt_box_origin + 50`` exactly for a 100 px box. So the convention is::

    centre = origin + size / 2

Not ``(size - 1) / 2``. This is measured, not assumed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# The reference is imaged at 1 nm/px and the search at 10 nm/px, so the reference's content occupies
# a 1/10-scale footprint in the search image. Confirmed as H1.
NOMINAL_MAGNIFICATION_RATIO = 10.0


@dataclass(frozen=True)
class Match:
    """A localization result, in problem coordinates.

    ``x`` and ``y`` are the centre of the matched region in SEARCH-IMAGE pixels, top-left origin,
    x rightward and y downward. They are floats: sub-pixel precision is the point.
    """

    x: float
    y: float
    score: float = 0.0
    #: Peak ambiguity index: best score divided by the best score among candidates
    #: that are NOT plausibly the same location. Unitless, and HIGHER IS SAFER -- a
    #: value near 1 means a structurally different position scores just as well.
    #: Previously named `confidence_radius_px`, which promised pixels and implied the
    #: opposite polarity; nothing consumed it under that name.
    ambiguity_index: float | None = None
    runtime_ms: float | None = None

    def as_stdout_line(self) -> str:
        """The single line printed in single-pair mode. Nothing else may go to stdout."""
        return f"{self.x:.2f},{self.y:.2f}"


# ---------------------------------------------------------------------------------------
# Coordinate conversion - the only place this is allowed to happen
# ---------------------------------------------------------------------------------------

def rowcol_to_xy(row: float, col: float) -> tuple[float, float]:
    """Array indexing ``[row, col]`` -> problem coordinates ``(x, y)``.

    Deliberately trivial and deliberately named: an explicit call reads as a conversion, whereas an
    inline ``(loc[1], loc[0])`` reads as a typo and hides the intent.
    """
    return float(col), float(row)


def xy_to_rowcol(x: float, y: float) -> tuple[float, float]:
    """Problem coordinates ``(x, y)`` -> array indexing ``[row, col]``."""
    return float(y), float(x)


def top_left_to_centre(x0: float, y0: float, width: float, height: float) -> tuple[float, float]:
    """Top-left corner of a matched region -> its centre, in problem coordinates.

    Uses ``origin + size/2`` — see the module docstring; this is fixed by H2, not chosen.
    """
    return x0 + width / 2.0, y0 + height / 2.0


def centre_to_top_left(cx: float, cy: float, width: float, height: float) -> tuple[float, float]:
    """Inverse of :func:`top_left_to_centre`."""
    return cx - width / 2.0, cy - height / 2.0


def match_template_peak_to_centre(
    peak_loc: tuple[int, int], template_shape: tuple[int, int]
) -> tuple[float, float]:
    """Convert a ``cv2.minMaxLoc`` result into the centre of the matched region.

    ``cv2.minMaxLoc`` returns ``(x, y)`` — already problem-ordered, NOT ``(row, col)``. That is
    counter-intuitive given how the rest of OpenCV indexes, and it is verified by
    ``tests/test_deps_api.py::test_match_template_peak_is_xy_not_rowcol``.

    ``template_shape`` is numpy-ordered ``(height, width)``, because it comes from ``array.shape``.
    """
    height, width = template_shape
    return top_left_to_centre(float(peak_loc[0]), float(peak_loc[1]), width, height)


def euclidean_error(pred: tuple[float, float], truth: tuple[float, float]) -> float:
    """The metric the problem statement specifies: sqrt((dx)^2 + (dy)^2) in search-image pixels."""
    return float(np.hypot(pred[0] - truth[0], pred[1] - truth[1]))


# ---------------------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------------------

def _load_npy(path: Path) -> np.ndarray:
    """Read a ``.npy`` array and put it on the same footing as a decoded image.

    Why this exists: the organiser's instruction to keep ``.npy -> .png`` conversion as a separate
    documented step implies the evaluation pairs may arrive as raw arrays. The problem statement is
    blunt about the consequence — *"an unrunnable script cannot be scored"* — so the inference path
    reads them directly rather than depending on a conversion having been run first. The standalone
    converter (``scripts/npy_to_png.py``) still exists, because the same instruction says PNGs are
    wanted for visual inspection.

    Float arrays are the ambiguous case and the only judgement call here. A float image may be
    stored in [0, 1] or in [0, 255], and guessing wrong changes every intensity by 255x. ZNCC is
    invariant to an affine intensity map, so the *matcher* would not care — but the median filter,
    the impulse-noise path and the drift estimator all assume 8-bit-like magnitudes. The rule is
    therefore: rescale only when the data cannot already be 8-bit-like (max <= 1.0), and otherwise
    leave the values alone. Constant images are passed through rather than divided by zero.
    """
    array = np.load(path, allow_pickle=False)
    if array.ndim not in (2, 3):
        raise ValueError(f"{path.name}: expected a 2-D or 3-D array, got shape {array.shape}")

    if np.issubdtype(array.dtype, np.floating):
        finite = array[np.isfinite(array)]
        peak = float(finite.max()) if finite.size else 0.0
        if peak <= 1.0 and peak > 0.0:
            array = array * 255.0
        array = np.clip(np.nan_to_num(array, nan=0.0), 0, 255).astype(np.uint8)
    elif array.dtype == np.uint16:
        array = (array.astype(np.float32) / 257.0).astype(np.uint8)
    elif array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return array


def load_grayscale(path: str | Path, as_float: bool = False) -> np.ndarray:
    """Load an image as single-channel grayscale.

    Accepts whatever the evaluator hands us - PNG/TIF/BMP/JPG, colour or grayscale, 8- or 16-bit -
    and normalises it to one internal representation, because the spec says the batch path must
    work without source edits.
    """
    path = Path(path)
    if path.suffix.lower() == ".npy":
        img = _load_npy(path)
    else:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"could not read image: {path}")

    if img.ndim == 3:
        channels = img.shape[2]
        if channels == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        elif channels == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            img = img[:, :, 0]

    if img.dtype == np.uint16:
        img = (img.astype(np.float32) / 257.0).astype(np.uint8)
    elif img.dtype not in (np.uint8, np.float32, np.float64):
        img = img.astype(np.float32)

    return img.astype(np.float32) if as_float else img


def validate_pair(reference: np.ndarray, search: np.ndarray) -> None:
    """Reject inputs that cannot be a valid Drift-Sense pair, with a message that says why."""
    if reference.ndim != 2 or search.ndim != 2:
        raise ValueError("reference and search must both be single-channel images")
    if reference.shape[0] > search.shape[0] * NOMINAL_MAGNIFICATION_RATIO or \
       reference.shape[1] > search.shape[1] * NOMINAL_MAGNIFICATION_RATIO:
        raise ValueError(
            f"reference {reference.shape} is too large relative to search {search.shape}: "
            f"the reference is a higher-magnification view and must fit inside the search field "
            f"once downscaled"
        )


# ---------------------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------------------

def read_manifest(path: str | Path) -> list[dict[str, str]]:
    """Read a manifest CSV.

    Our schema is a deliberate superset of the sponsor's, so their manifests load through this
    reader unchanged - which is what makes cross-generator validation possible (ADR-0004).
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def resolve_manifest_path(manifest_path: str | Path, recorded: str) -> Path:
    """Resolve an image path from a manifest row.

    Manifest paths may be relative to the repo root, relative to the manifest itself, or absolute
    (the sponsor's generator writes paths relative to its own working directory). Try each in turn
    rather than assuming, so a manifest written on another machine still loads.

    **Separator normalisation.** A manifest written on Windows records ``data\\verify\\ref\\0.png``.
    POSIX treats a backslash as an ordinary filename character, so that path does not resolve on
    macOS or Linux and the whole batch fails on the evaluator's machine - the failure mode this
    team hits every time, since one of us is on macOS and two are on Windows. The separator variant
    is therefore tried as a FALLBACK, never first: on POSIX a backslash can legitimately appear in
    a filename, and a real file must always win over a guess.
    """
    manifest_path = Path(manifest_path)

    variants = [recorded]
    if "\\" in recorded:
        variants.append(recorded.replace("\\", "/"))

    for text in variants:
        candidate = Path(text)
        if candidate.is_absolute() and candidate.exists():
            return candidate

        for base in (manifest_path.parent, manifest_path.parent.parent, Path.cwd()):
            trial = base / candidate
            if trial.exists():
                return trial
            # Sponsor manifests record e.g. "output/train/reference/00000.png"; fall back to the
            # filename inside the expected subdirectory.
            trial = base / candidate.parent.name / candidate.name
            if trial.exists():
                return trial

    raise FileNotFoundError(f"could not resolve '{recorded}' relative to {manifest_path}")


def write_predictions(path: str | Path, matches: list[tuple[str, Match]]) -> None:
    """Write predictions.csv - the format evaluate.py consumes and the spec asks for."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "pred_x", "pred_y", "score", "ambiguity_index", "runtime_ms"])
        for pair_id, m in matches:
            # A non-finite confidence is written as an empty cell rather than "inf". It means "no
            # rival candidate was close enough to compete", and an empty cell is what every CSV
            # reader already understands as missing - "inf" is a string that breaks strict numeric
            # parsers on the evaluator's side.
            confidence = m.ambiguity_index
            finite_confidence = (confidence is not None and np.isfinite(confidence))
            writer.writerow([
                pair_id, f"{m.x:.4f}", f"{m.y:.4f}", f"{m.score:.6f}",
                f"{confidence:.4f}" if finite_confidence else "",
                "" if m.runtime_ms is None else f"{m.runtime_ms:.2f}",
            ])
