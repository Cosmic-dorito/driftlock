"""Measure the scanner from the periodic array, and correct the whole search image once.

This is a GLOBAL acquisition calibration, not a per-candidate refinement, and that distinction is
the whole point. Every candidate-local deformation experiment in this project has been negative or
untrustworthy for the same structural reason: a candidate allowed to choose its own correction is
being handed extra freedom, and freedom flows to whichever candidate has more mismatch to absorb
(FINDINGS 15d, 23f, 36b). A field estimated once from the entire search image, before any candidate
exists, cannot privilege one site over another - it is the same correction for all of them.

WHY THERE IS SOMETHING TO CORRECT
---------------------------------
The generator's raster stage is ``out[y, x] = clean[y, x + shear*y/(H-1) + jitter_y]`` with
``jitter_y ~ N(0, sigma)`` drawn independently per row. On every split here that is a **1.5 px**
end-to-end shear and a **0.5 px** per-row jitter. Those two are not equally important:

* across a 100 px footprint the shear contributes **0.15 px** of relative displacement, and the
  existing drift stage removes its linear part anyway;
* the jitter is **white in y**, so each of the ~100 rows of a footprint is displaced by an
  independent half pixel, and no smooth model can represent it.

The reference is drawn with its own independent jitter, but at 1 nm/px - after the 10x decimation
that is 0.05 px in search pixels. **The search image's per-row jitter is therefore the dominant
uncorrected geometric error in the whole pipeline**, and it is invisible to a rigid pose.

HOW THE ARRAY MEASURES THE SCANNER
----------------------------------
A row cannot be aligned against anything unless something says where it should have been. The
periodic array supplies exactly that: rows one lattice period apart image the same structure, so
``T[y] = mean_k I[y + k*p]`` is a high-SNR estimate of row ``y`` whose own jitter has been averaged
down by ``sqrt(2K)``. Correlating ``I[y]`` against ``T[y]`` measures ``jitter_y`` minus the local
mean jitter - that is, the residual after the smooth component, which is precisely the part the
existing drift stage cannot reach. Correcting it leaves the smooth shear untouched and in the frame
the drift stage already expects, so the two stages compose instead of fighting.

WHAT MAKES IT SAFE TO SHIP
--------------------------
Two independent estimators (spatial ZNCC and Fourier phase correlation) are run over the same
template and must agree, and the mean peak margin must clear a floor. If either gate fails the
image is returned untouched. The failure mode this guards against is the one already measured: a
well-aligned patch has nothing to gain from a correction and everything to lose from a noisy one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# The lag search must stay well inside half a lattice period or the correlation locks onto the
# neighbouring repeat. DRAM bit-line pitch is 96 nm = 9.6 search px at 10:1, so half a period is
# ~4.8 px; 3 px leaves margin and still covers 6 sigma of a 0.5 px jitter.
MAX_LAG_PX = 3

# Rows one period apart are averaged to build the template. More rows average the jitter down as
# 1/sqrt(2K) but reach further through the mat, where the structure eventually changes.
DEFAULT_HALF_TAPS = 6

# A period below this is smaller than the lag search and cannot be separated from it; above this it
# reaches out of the mat. Both ends are geometry, not tuning.
MIN_PERIOD_PX = 4.0
MAX_PERIOD_PX = 40.0


@dataclass
class ScanField:
    """The measured per-row horizontal offset, and everything needed to judge it."""

    offsets: np.ndarray                 # d[y], search pixels; positive means the row sampled right
    period_px: float
    confidence: float                   # mean peak margin over accepted rows
    agreement_px: float                 # median |estimator A - estimator B|
    accepted_rows: int
    applied: bool = False
    reason: str = ""
    diagnostics: dict = field(default_factory=dict)


def estimate_period(image: np.ndarray) -> float:
    """The dominant vertical period, read off the mean column-wise power spectrum.

    Averaging the per-column spectra rather than spectrally analysing a single profile is what makes
    this work when the lines run vertically: a row-mean profile is nearly flat in that case and
    carries no period at all, while every individual column still oscillates.
    """
    work = image.astype(np.float32)
    work = work - work.mean(axis=0, keepdims=True)
    spectrum = np.abs(np.fft.rfft(work, axis=0)) ** 2
    power = spectrum.mean(axis=1)

    height = work.shape[0]
    lo = max(int(np.ceil(height / MAX_PERIOD_PX)), 2)
    hi = min(int(np.floor(height / MIN_PERIOD_PX)), power.size - 1)
    if hi <= lo:
        return 0.0
    band = power[lo:hi + 1]
    peak = int(np.argmax(band)) + lo

    # Parabolic interpolation on the log spectrum: the period is used to resample the image, so a
    # whole-bin estimate at ~150 bins is a 0.7% period error and accumulates across taps.
    if 0 < peak < power.size - 1:
        a, b, c = (float(np.log(max(power[peak + off], 1e-30))) for off in (-1, 0, 1))
        denom = a - 2.0 * b + c
        shift = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
        peak_f = peak + float(np.clip(shift, -0.5, 0.5))
    else:
        peak_f = float(peak)
    return float(height / peak_f) if peak_f > 0 else 0.0


def _lattice_template(image: np.ndarray, period: float, half_taps: int) -> np.ndarray:
    """``T[y] = mean over k != 0 of I[y + k*period]``, at sub-pixel period.

    Vertical translation by a fractional number of rows is one warpAffine, so the whole template is
    ``2 * half_taps`` interpolations of the full image rather than a per-row gather. Excluding k = 0
    matters: a template containing the row it will be compared against would pull every estimate
    toward zero.
    """
    height, width = image.shape
    accum = np.zeros_like(image, dtype=np.float32)
    count = 0
    for tap in range(-half_taps, half_taps + 1):
        if tap == 0:
            continue
        shift = tap * period
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, -shift]], dtype=np.float32)
        accum += cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REFLECT)
        count += 1
    return accum / max(count, 1)


def _zncc_rows(rows: np.ndarray, template: np.ndarray, max_lag: int) -> np.ndarray:
    """Per-row ZNCC of every row against its template, at every integer lag. Shape (H, 2L+1).

    Written as whole-array operations over lags rather than a loop over rows: at 1000 rows and 7
    lags the arithmetic is trivial and the interpreter overhead is not.
    """
    height, width = rows.shape
    lo, hi = max_lag, width - max_lag
    centre = rows[:, lo:hi]
    centre = centre - centre.mean(axis=1, keepdims=True)
    centre_norm = np.sqrt((centre * centre).sum(axis=1))

    scores = np.empty((height, 2 * max_lag + 1), dtype=np.float64)
    for index, lag in enumerate(range(-max_lag, max_lag + 1)):
        window = template[:, lo + lag:hi + lag]
        window = window - window.mean(axis=1, keepdims=True)
        denom = centre_norm * np.sqrt((window * window).sum(axis=1))
        with np.errstate(invalid="ignore", divide="ignore"):
            scores[:, index] = np.where(denom > 1e-9, (centre * window).sum(axis=1) / denom, 0.0)
    return scores


def _parabolic(values: np.ndarray, index: int) -> float:
    if index <= 0 or index >= values.size - 1:
        return 0.0
    a, b, c = float(values[index - 1]), float(values[index]), float(values[index + 1])
    denom = a - 2.0 * b + c
    return 0.0 if abs(denom) < 1e-12 else float(np.clip(0.5 * (a - c) / denom, -1.0, 1.0))


def _offsets_spatial(scores: np.ndarray, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    """Estimator A: argmax of the ZNCC lag profile, with a parabolic vertex and a peak margin."""
    peaks = np.argmax(scores, axis=1)
    offsets = np.empty(scores.shape[0], dtype=np.float64)
    margins = np.empty(scores.shape[0], dtype=np.float64)
    for row in range(scores.shape[0]):
        peak = int(peaks[row])
        offsets[row] = (peak - max_lag) + _parabolic(scores[row], peak)
        profile = scores[row].copy()
        best = profile[peak]
        profile[max(peak - 1, 0):peak + 2] = -np.inf
        runner = float(np.max(profile)) if np.isfinite(profile).any() else 0.0
        margins[row] = float(best) - runner
    return offsets, margins


def _offsets_phase(rows: np.ndarray, template: np.ndarray, max_lag: int) -> np.ndarray:
    """Estimator B: per-row Fourier phase correlation.

    Deliberately shares nothing with estimator A but the template. The reason this project needs a
    second estimator at all is that two implementations of a per-row jitter estimate once disagreed
    about the SIGN of the effect (FINDINGS 36c vs 37d); a calibration that cannot check itself is
    not one we are willing to apply to the image every candidate is scored against.
    """
    height, width = rows.shape
    window = np.hanning(width).astype(np.float32)[None, :]
    a = np.fft.rfft((rows - rows.mean(axis=1, keepdims=True)) * window, axis=1)
    b = np.fft.rfft((template - template.mean(axis=1, keepdims=True)) * window, axis=1)
    cross = a * np.conj(b)
    magnitude = np.abs(cross)
    cross = np.where(magnitude > 1e-12, cross / np.maximum(magnitude, 1e-12), 0.0)
    correlation = np.fft.irfft(cross, n=width, axis=1)

    # Only lags within the search window are admissible; the rest are lattice repeats.
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(width - max_lag, width)])
    band = correlation[:, lags]
    peaks = np.argmax(band, axis=1)
    signed = np.where(peaks <= max_lag, peaks, peaks - band.shape[1])
    out = np.empty(height, dtype=np.float64)
    for row in range(height):
        out[row] = float(signed[row])
    return out


def estimate_scan_field(
    search: np.ndarray, *, half_taps: int = DEFAULT_HALF_TAPS, max_lag: int = MAX_LAG_PX,
    min_confidence: float = 0.02, max_disagreement_px: float = 0.75,
    min_accepted_fraction: float = 0.5,
) -> ScanField:
    """Measure the per-row horizontal offset field of a search image, or decline to.

    Returns a :class:`ScanField` whose ``applied`` flag says whether the gates passed. Declining is
    a first-class outcome: on an image whose periodicity is weak or whose two estimators disagree,
    leaving the image alone is strictly better than warping it by a noisy field.
    """
    work = search.astype(np.float32)
    period = estimate_period(work)
    if not (MIN_PERIOD_PX <= period <= MAX_PERIOD_PX):
        return ScanField(np.zeros(work.shape[0]), period, 0.0, 0.0, 0,
                         reason=f"no usable vertical period (got {period:.2f} px)")

    template = _lattice_template(work, period, half_taps)
    scores = _zncc_rows(work, template, max_lag)
    offsets_a, margins = _offsets_spatial(scores, max_lag)
    offsets_b = _offsets_phase(work, template, max_lag)

    accepted = margins > min_confidence
    n_accepted = int(accepted.sum())
    fraction = n_accepted / max(work.shape[0], 1)
    agreement = float(np.median(np.abs(offsets_a[accepted] - offsets_b[accepted]))) \
        if n_accepted else np.inf
    confidence = float(margins[accepted].mean()) if n_accepted else 0.0

    field_px = np.where(accepted, offsets_a, 0.0)
    # The truth is white noise in y, so this is deliberately NOT smoothed - a polynomial fit would
    # remove exactly the component being corrected. The only shaping is the median subtraction
    # below, which keeps the field zero-mean so the smooth shear is left for the drift stage.
    if n_accepted:
        field_px = field_px - float(np.median(field_px[accepted]))
    field_px = np.clip(field_px, -max_lag, max_lag)

    result = ScanField(field_px, period, confidence, agreement, n_accepted,
                       diagnostics={"accepted_fraction": fraction,
                                    "rms_px": float(np.sqrt(np.mean(field_px ** 2)))})
    if fraction < min_accepted_fraction:
        result.reason = f"only {100 * fraction:.0f}% of rows cleared the margin floor"
    elif agreement > max_disagreement_px:
        result.reason = f"estimators disagree by {agreement:.2f} px"
    else:
        result.applied = True
        result.reason = "applied"
    return result


def apply_scan_field(search: np.ndarray, field_px: np.ndarray) -> np.ndarray:
    """Undo the measured per-row offset.

    The generator forms ``out[y, x] = clean[y, x + s_y]``, so the inverse samples at ``x - d_y``.
    Getting this sign backwards doubles the distortion instead of removing it, which is why
    ``tests/test_scanfield.py`` builds an image with a hand-chosen offset and checks the recovered
    field against it rather than against whatever this function happens to produce.
    """
    height, width = search.shape
    map_x = np.arange(width, dtype=np.float32)[None, :] - field_px.astype(np.float32)[:, None]
    map_y = np.tile(np.arange(height, dtype=np.float32)[:, None], (1, width))
    return cv2.remap(search, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def calibrate(search: np.ndarray, **kwargs) -> tuple[np.ndarray, ScanField]:
    """Measure and, if the gates pass, correct. Returns the image to localize in."""
    measured = estimate_scan_field(search, **kwargs)
    if not measured.applied:
        return search, measured
    return apply_scan_field(search, measured.offsets), measured
