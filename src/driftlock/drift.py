"""Blind estimation of raster-scan drift, and correction of the reported coordinate.

Why this module exists
----------------------
After correlation finds the correct lattice repeat, the largest remaining error is **not** a
matching error. The SEM's raster scan drifts during acquisition, so the search image's content is
physically displaced - row *r* is shifted horizontally by ``shear*(r/(H-1))`` plus per-row vibration
jitter. Ground truth, however, is defined in the **undrifted** frame. The matcher therefore reports
correctly where the pattern *is*, while ground truth records where it *would have been*.

No improvement to the similarity measure can close that gap; only modelling the distortion and
inverting it can. Measured on 40 sponsor pairs, removing it takes the median error among
correctly-located pairs from 0.866 px to 0.062 px - a 14x reduction (docs/FINDINGS.md section 12).

This is the project's thesis in miniature: the win comes from inverting a known acquisition
physics, not from a better matcher.

How it works
------------
The estimator exploits a fact that is easy to state and easy to get wrong: **rows close together
contain the same content**. Vertical bit-lines run continuously down the image, so two rows a
modest distance apart show the same structure displaced only by the drift accumulated between them.
Correlating them recovers that displacement directly.

Two earlier approaches failed, and their failures shaped this one:

1. *Correlating distant horizontal bands.* The canvas is zoned in both directions and each mat's
   line positions are drawn independently, so distant bands are not the same pattern displaced -
   they are different patterns. No common signal to correlate.
2. *Correlating adjacent rows and integrating.* Adjacent rows do share content, but summing noisy
   per-row differentials random-walks: sqrt(1000) x 0.05 px is about 1.6 px of accumulated
   integration noise, which swamps the 1.5 px signal being measured.

The working method avoids both traps: correlate rows separated by a fixed **gap** (still well
inside one mat, which spans ~260 search px), and fit the displacement directly. Nothing is
integrated, so no random walk accumulates.

Validated against data generated at known shear values:

===========  ==========================
true shear    estimated (gap=40, the shipped default)
===========  ==========================
0.0           0.009 +/- 0.202
1.5           1.445 +/- 0.344
3.0           2.804 +/- 0.321
5.0           5.184 +/- 0.245
===========  ==========================

Essentially unbiased across the range, with a scatter well below the ~0.84 px bias being removed.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d

# Row separation for the displacement measurement. It is NOT free: it is pinned between two hard
# constraints, and the value it used to have (100) satisfied neither.
#
#   gap * tan(rho_max) + |drift|   <   max_lag   <   lattice_pitch / 2
#   \_________________________/                      \______________/
#    the displacement we must be           beyond this the correlation locks onto the
#    able to SEE without clipping          NEXT lattice line instead of the right one
#
# The DRAM word-line pitch is ~6.4 search px, so the upper bound is ~3.2 px. At gap=100 a 2-degree
# rotation alone displaces content by 100*tan(2) = 3.49 px, so the lower bound already exceeds the
# upper one - there is NO valid max_lag at that gap, and the measurement saturated at the edge of
# its own search window. That is what produced estimates with a standard deviation of 13-20 px on
# rotated data, and it is why the "exact" two-axis cancellation was not exact: its inputs were
# clipped before it ever ran.
#
# At gap=40 the constraint is satisfiable: 40*tan(2) + 1.5 = 2.9 < 3 < 3.2. Measured standard
# deviation of the estimate drops from 13.3 to 0.6 px on bench, 16.5 to 0.6 on dev, with medians
# unchanged - the fix removes catastrophic outliers rather than shifting the average.
#
# The cost is leverage: the estimate is scaled by (H-1)/gap, so a shorter gap amplifies per-pair
# noise. The median over ~24 row pairs absorbs that, and a noisy-but-unbiased estimate is worth far
# more than an occasionally-saturated one.
DEFAULT_GAP = 40

# Expected drift is a few pixels, so a narrow lag window suffices - and it must stay well below the
# lattice pitch (~6.4-9.6 search px) or the periodicity aliases the correlation onto the wrong
# repeat. That is precisely how the first version of this estimator failed.
DEFAULT_MAX_LAG = 3

# Row pairs whose correlation falls below this are assumed to straddle a mat/strip boundary, where
# the content genuinely differs, and are discarded rather than allowed to bias the fit.
MIN_ROW_CORRELATION = 0.3


def _parabolic_subpixel(values: np.ndarray, index: int) -> float:
    """Sub-sample peak offset by a 3-point parabolic fit."""
    if index <= 0 or index >= len(values) - 1:
        return 0.0
    a, b, c = values[index - 1], values[index], values[index + 1]
    denominator = a - 2.0 * b + c
    if abs(denominator) < 1e-12:
        return 0.0
    return float(np.clip(0.5 * (a - c) / denominator, -1.0, 1.0))


def estimate_shear(
    search: np.ndarray, gap: int = DEFAULT_GAP, band: int = 7,
    max_lag: int = DEFAULT_MAX_LAG, step: int = 5, rotation_deg: float = 0.0,
) -> float | None:
    """Estimate total horizontal drift across the full image height, in pixels.

    Returns ``None`` when too few usable row pairs survive - a featureless or heavily zoned image
    where the estimate would be unreliable. The caller then skips the correction rather than
    applying a guess, so an uncertain estimate can never make results worse.

    ``rotation_deg`` is essential whenever the field of view is rotated, and leaving it at zero on
    rotated data is actively harmful. **A rotation is indistinguishable from drift by this
    measurement**: both make content move sideways as the scan goes down. A tilt of ``rho``
    displaces content by ``gap * tan(rho)`` over the same row separation, and the estimator
    happily reports that as drift and then "corrects" a distortion that was never there.

    Measured on 40 rotated dev pairs (12 Aug, another machine): with the true pose supplied but no
    rotation compensation, the residual error was ``dx = -9.5 * rotation_deg`` - a clean straight
    line through the failures, up to 19 px on a 2 degree pair. It never appeared on the sponsor's
    data for the simple reason that their generator produces no rotation (H9), which is exactly the
    kind of blind spot cross-validating on one generator cannot reveal.
    """
    work = search.astype(np.float64)
    height, width = work.shape
    if height < gap + 2 or width < 4 * max_lag + 8:
        return None

    # Average a few rows together: raises per-row SNR at dose 200 without mixing distant content.
    work = uniform_filter1d(work, band, axis=0, mode="nearest")
    work = work - work.mean(axis=1, keepdims=True)
    work = work / (np.linalg.norm(work, axis=1, keepdims=True) + 1e-9)

    lags = np.arange(-max_lag, max_lag + 1)
    lo, hi = max_lag, width - max_lag

    # Vectorised over row-pairs. The obvious loop - one Python iteration per row-pair, and a list
    # comprehension over lags inside it - runs ~2700 tiny dot products through the interpreter, and
    # profiling put the whole drift stage at ~337 ms of a 736 ms pipeline. The arithmetic is
    # trivial; the overhead was the cost. Doing all row-pairs at once for each lag turns it into
    # 2*max_lag+1 array operations. Numerically identical: same dot products, same order.
    top = work[0:height - gap:step, lo:hi]                      # (n_pairs, W')
    scores = np.empty((top.shape[0], lags.size), dtype=np.float64)
    for i, lag in enumerate(lags):
        bottom = work[gap:height:step, lo + lag:hi + lag][:top.shape[0]]
        scores[:, i] = np.einsum("ij,ij->i", top, bottom)

    peaks = np.argmax(scores, axis=1)
    best = scores[np.arange(scores.shape[0]), peaks]
    keep = best >= MIN_ROW_CORRELATION       # rows straddling a zone boundary genuinely differ

    shifts: list[float] = []
    for index in np.flatnonzero(keep):
        peak = int(peaks[index])
        shifts.append(float(lags[peak]) + _parabolic_subpixel(scores[index], peak))

    if len(shifts) < 20:
        return None

    # Median rather than mean: robust to the row pairs that cross a mat boundary despite the
    # correlation gate.
    per_gap_shift = float(np.median(shifts))

    # Remove the part of the row-to-row displacement that a tilted field of view explains, leaving
    # only genuine scan drift. Without this the correction fights the rotation instead of the
    # drift; see the docstring.
    per_gap_shift -= gap * float(np.tan(np.deg2rad(rotation_deg)))

    return -per_gap_shift * (height - 1) / gap


def correct_for_drift(x: float, y: float, shear: float, height: int) -> float:
    """Map a coordinate from the drifted (as-imaged) frame back to the undrifted frame.

    The scan displaces content at row *y* by ``-shear*(y/(H-1))``, so recovering the ground-truth
    frame means adding that displacement back.
    """
    return float(x + shear * (y / max(height - 1, 1)))


def estimate_drift_shear(search: np.ndarray, gap: int = DEFAULT_GAP) -> float | None:
    """Separate genuine scan drift from field-of-view rotation, using only the search image.

    The problem this solves
    -----------------------
    A tilted field of view and a drifting raster produce the *same* row-to-row displacement, so
    :func:`estimate_shear` measures their sum and cannot split it. Handing it a rotation estimated
    elsewhere does not rescue it either: the leverage is brutal, because an error of ``delta``
    degrees becomes ``tan(delta) * (H-1)`` pixels of shear, so our 0.43 degree pose accuracy turned
    a 1.5 px correction into a 7 px error. Measured on 40 rotated pairs, every variant of that idea
    was worse than not correcting at all.

    The observation that fixes it
    -----------------------------
    **Drift is anisotropic and rotation is isotropic.** The raster scans line by line, so drift
    displaces x as a function of y and nothing else - a horizontal feature stays horizontal, it
    just slides. A rotation, by contrast, tilts *both* axes at once.

    So run the identical measurement on the transposed image. Along columns, drift contributes
    nothing and only the tilt survives::

        rows   :  S_row = -(drift_rate + tan(rho)) * (H-1)
        columns:  S_col = +tan(rho) * (W-1)

    and for a square frame the two simply add, leaving the drift term alone::

        S_drift = S_row + S_col * (H-1)/(W-1)

    No rotation estimate is needed, no parameter is introduced, and the rotation cancels
    *exactly* rather than approximately - which matters, because it was the approximation that
    made the previous version unusable.
    """
    along_rows = estimate_shear(search, gap=gap)
    if along_rows is None:
        return None

    # The same estimator along the other axis. np.ascontiguousarray because the correlations below
    # walk rows, and a transposed view would make every one of them a strided read.
    along_columns = estimate_shear(np.ascontiguousarray(search.T), gap=gap)
    if along_columns is None:
        return along_rows  # no tilt information: fall back to the raw estimate

    height, width = search.shape[:2]
    return float(along_rows + along_columns * (height - 1) / max(width - 1, 1))


def gap_for_rotation(rotation_deg: float | None, max_lag: int = DEFAULT_MAX_LAG,
                     drift_allowance_px: float = 1.5, cap: int = 100) -> int:
    """The largest row separation whose displacement still fits inside the lag search.

    Derived from the constraint in the DEFAULT_GAP comment rather than tuned::

        gap * tan(rho) + drift  <  max_lag        =>    gap < (max_lag - drift) / tan(rho)

    At 2 degrees this returns 43, which is where the empirical sweep put the optimum (40) - the
    formula and the measurement agree, which is the reason to trust either.

    As the rotation goes to zero the bound goes to infinity and the gap is capped at 100, recovering
    the long-baseline behaviour that is best on unrotated data: a longer gap divides the estimate by
    a bigger number, so it amplifies per-pair noise less. Using one fixed gap forces a choice
    between the two regimes; deriving it from the measured rotation serves both.
    """
    if rotation_deg is None:
        return DEFAULT_GAP
    tan_rho = abs(float(np.tan(np.deg2rad(rotation_deg))))
    headroom = max(max_lag - drift_allowance_px, 0.5)
    if tan_rho < 1e-6:
        return cap
    return int(np.clip(headroom / tan_rho, 12, cap))


def estimate_and_correct(
    search: np.ndarray, x: float, y: float, gap: int = DEFAULT_GAP,
    rotation_deg: float | None = None, max_shear_px: float = 0.0,
) -> tuple[float, float | None]:
    """Convenience wrapper: estimate the drift and apply it to one coordinate.

    Returns ``(corrected_x, estimated_shear)``; the shear is ``None`` when estimation was
    abandoned, in which case the coordinate is returned unchanged.

    With ``rotation_deg=None`` (the default) the rotation is cancelled geometrically by
    :func:`estimate_drift_shear`, which is both parameter-free and exact. Passing an explicit
    rotation uses the weaker subtract-an-estimate route and is kept only for the ablation.
    """
    shear = (estimate_drift_shear(search, gap=gap) if rotation_deg is None
             else estimate_shear(search, gap=gap, rotation_deg=rotation_deg))
    if shear is None:
        return float(x), None
    # Abandon an implausible estimate rather than apply it. This is the same posture as returning
    # None above - when the measurement is not identifiable, not correcting beats correcting badly.
    #
    # Measured (results/refine_forensics.csv, 300 pairs): the correction moves the answer a median
    # 0.65 px, but on two pairs it moved 7.5 and 24.3 px and turned a correctly SELECTED candidate
    # into a mis-lock. Those are the only two pairs in 300 where selection was right and the
    # reported answer was not, and both are this stage.
    if max_shear_px > 0.0 and abs(shear) > max_shear_px:
        return float(x), None
    return correct_for_drift(x, y, shear, search.shape[0]), shear
