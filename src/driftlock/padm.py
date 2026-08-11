"""A7: periodic-aperiodic decomposition, and candidate re-scoring on the residual.

The idea in one line: **the lattice tells you where you are within a cell; the residual tells you
which cell.**

A DRAM array is a dense 2D lattice, so a 100x100 template matches almost equally well at many
positions - measured on real data, the winning peak beats its best rival by a median ZNCC margin of
only 0.016 while sitting 45 px away (H8). Correlating the raw images spends almost all of the score
on the periodic part, which by definition carries no information about WHICH repeat you are on.

But the pattern is not perfectly periodic. Line positions are laid down as a random walk
(``pos += pitch + N(0, 1.5nm)``), so every cell has a slightly unique geometry, and the array is
broken up by mat/strip boundaries. That aperiodic content is faint but it is the only thing that
identifies location. Verified as H7: the self-correlation margin between the true alignment and its
best lattice-equivalent impostor is strictly positive on every reference tested (median 0.057,
minimum 0.0086), so disambiguation is possible in principle - it just needs the periodic part out
of the way first.

Removing the lattice raises the residual from a rounding error to the dominant signal.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class LatticeEstimate:
    """Dominant reciprocal-lattice peaks of an image, in cycles/pixel."""

    peaks: tuple[tuple[float, float], ...]  # (fy, fx)
    strength: float                          # fraction of AC energy in the lattice peaks

    @property
    def dominant_pitch_px(self) -> float | None:
        """Real-space pitch of the strongest lattice peak, in pixels."""
        if not self.peaks:
            return None
        fy, fx = self.peaks[0]
        r = float(np.hypot(fy, fx))
        return 1.0 / r if r > 1e-9 else None


def estimate_lattice(img: np.ndarray, n_peaks: int = 12, min_period_px: float = 3.0,
                     max_period_px: float = 100.0) -> LatticeEstimate:
    """Locate the dominant reciprocal-lattice peaks in the power spectrum.

    Windowed with a 2D Hann to stop the frame edges from producing a cross artefact that would
    swamp the genuine lattice peaks.
    """
    work = img.astype(np.float64)
    work = work - work.mean()
    rows, cols = work.shape
    work = work * np.hanning(rows).reshape(-1, 1) * np.hanning(cols).reshape(1, -1)

    spectrum = np.abs(np.fft.fft2(work))
    fy = np.fft.fftfreq(rows).reshape(-1, 1)
    fx = np.fft.fftfreq(cols).reshape(1, -1)
    radius = np.sqrt(fy ** 2 + fx ** 2)

    # Keep only the band where a real lattice could live.
    valid = (radius >= 1.0 / max_period_px) & (radius <= 1.0 / min_period_px)
    masked = np.where(valid, spectrum, 0.0)
    total = float(masked.sum()) + 1e-12

    peaks: list[tuple[float, float]] = []
    captured = 0.0
    work_spec = masked.copy()
    # Suppression radius in frequency bins, so nearby bins of one peak are not counted twice.
    rr = max(int(round(0.01 * max(rows, cols))), 2)

    for _ in range(n_peaks):
        idx = int(np.argmax(work_spec))
        iy, ix = np.unravel_index(idx, work_spec.shape)
        value = float(work_spec[iy, ix])
        if value <= 0:
            break
        peaks.append((float(fy[iy, 0]), float(fx[0, ix])))
        captured += value
        y0, y1 = max(iy - rr, 0), min(iy + rr + 1, rows)
        x0, x1 = max(ix - rr, 0), min(ix + rr + 1, cols)
        work_spec[y0:y1, x0:x1] = 0.0

    return LatticeEstimate(tuple(peaks), float(captured / total))


def decompose(img: np.ndarray, lattice: LatticeEstimate | None = None,
              bandwidth: float = 0.006) -> tuple[np.ndarray, np.ndarray]:
    """Split an image into (periodic, aperiodic residual).

    The periodic component is reconstructed by keeping ONLY the neighbourhoods of the dominant
    reciprocal-lattice peaks (plus DC); the residual is whatever is left. ``bandwidth`` is in
    cycles/pixel and sets how much of each peak's skirt is treated as "lattice" - it must be wide
    enough to capture the peak broadened by the random-walk placement, but narrow enough to leave
    the aperiodic content behind.
    """
    work = img.astype(np.float64)
    if lattice is None:
        lattice = estimate_lattice(work)

    rows, cols = work.shape
    fy = np.fft.fftfreq(rows).reshape(-1, 1)
    fx = np.fft.fftfreq(cols).reshape(1, -1)

    fft = np.fft.fft2(work)
    mask = np.zeros((rows, cols), dtype=bool)
    mask[0, 0] = True  # keep DC so the periodic part carries the mean

    for py, px in lattice.peaks:
        for sy, sx in ((py, px), (-py, -px)):  # Hermitian pair
            mask |= ((fy - sy) ** 2 + (fx - sx) ** 2) <= bandwidth ** 2

    periodic = np.real(np.fft.ifft2(fft * mask))
    residual = work - periodic
    return periodic.astype(np.float32), residual.astype(np.float32)


def aperiodic_residual(img: np.ndarray, bandwidth: float = 0.006) -> np.ndarray:
    """Convenience wrapper returning only the residual channel."""
    return decompose(img, bandwidth=bandwidth)[1]


def rescore_on_residual(
    search_residual: np.ndarray, template_residual: np.ndarray,
    candidates, weight: float = 0.5,
) -> list:
    """Blend each candidate's original score with its score on the aperiodic residual.

    The residual is where cell identity lives, so a candidate that matches the lattice but sits on
    the wrong repeat scores well on the raw image and poorly here. Blending rather than replacing
    keeps the raw score's robustness: the residual has low SNR at dose 200, so trusting it alone
    would trade one failure mode for another.

    ``candidates`` are :class:`~src.driftlock.match.Candidate` instances; returned sorted by the
    combined score, with the components recorded in ``extra`` so the ablation can inspect them.
    """
    th, tw = template_residual.shape[:2]
    sh, sw = search_residual.shape[:2]
    rescored = []

    tpl = template_residual.astype(np.float32)
    tpl_zm = tpl - tpl.mean()
    tpl_norm = float(np.linalg.norm(tpl_zm)) + 1e-9

    for cand in candidates:
        x0 = int(round(cand.x - tw / 2.0))
        y0 = int(round(cand.y - th / 2.0))
        if x0 < 0 or y0 < 0 or x0 + tw > sw or y0 + th > sh:
            residual_score = -1.0
        else:
            patch = search_residual[y0:y0 + th, x0:x0 + tw].astype(np.float32)
            patch_zm = patch - patch.mean()
            denom = (float(np.linalg.norm(patch_zm)) + 1e-9) * tpl_norm
            residual_score = float((patch_zm * tpl_zm).sum() / denom)

        cand.extra["raw_score"] = cand.score
        cand.extra["residual_score"] = residual_score
        cand.score = (1.0 - weight) * cand.score + weight * residual_score
        rescored.append(cand)

    return sorted(rescored, key=lambda c: c.score, reverse=True)


def periodic_ambiguity_index(candidates, pitch_px: float | None) -> float:
    """How dangerous is the ambiguity for this pair? Higher is safer.

    Ratio of the best score to the best score among candidates that are NOT plausibly the same
    location. A value near 1 means a structurally different position scores just as well, which is
    precisely when the coordinate should not be trusted.

    Reported as a confidence signal rather than used to alter the coordinate: the spec asks for "a
    repeatable score or confidence where possible", and a tool that knows when it is unsure is worth
    more to a fab than one that is quietly wrong.
    """
    if len(candidates) < 2:
        return float("inf")

    ordered = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = ordered[0]
    separation = max(pitch_px or 6.0, 3.0)

    for cand in ordered[1:]:
        if np.hypot(cand.x - best.x, cand.y - best.y) > separation:
            denom = abs(cand.score) + 1e-9
            return float(abs(best.score) / denom)
    return float("inf")


def suppress_border(surface: np.ndarray, margin: int = 2) -> np.ndarray:
    """Zero a thin border of a correlation surface.

    Partial-overlap positions at the very edge can produce spuriously high normalised scores from
    very few pixels. Cheap insurance, applied before peak extraction.
    """
    out = surface.copy()
    if margin > 0:
        out[:margin, :] = -1.0
        out[-margin:, :] = -1.0
        out[:, :margin] = -1.0
        out[:, -margin:] = -1.0
    return out


def gaussian_peak_refine(surface: np.ndarray, x: int, y: int) -> tuple[float, float]:
    """Sub-pixel peak location by a 1D Gaussian fit on each axis of the 3x3 neighbourhood.

    A Gaussian fit rather than a parabolic one because a correlation peak between band-limited
    images is approximately Gaussian, and the parabolic fit carries a well-known bias toward
    integer positions ("peak locking") that would show up exactly at the 1 px threshold we care
    about.
    """
    h, w = surface.shape
    if not (1 <= x < w - 1 and 1 <= y < h - 1):
        return float(x), float(y)

    eps = 1e-12

    def offset(a: float, b: float, c: float) -> float:
        a, b, c = max(a, eps), max(b, eps), max(c, eps)
        la, lb, lc = np.log(a), np.log(b), np.log(c)
        denom = 2.0 * (la - 2.0 * lb + lc)
        if abs(denom) < eps:
            return 0.0
        return float(np.clip((la - lc) / denom, -1.0, 1.0))

    dx = offset(surface[y, x - 1], surface[y, x], surface[y, x + 1])
    dy = offset(surface[y - 1, x], surface[y, x], surface[y + 1, x])
    return float(x) + dx, float(y) + dy
