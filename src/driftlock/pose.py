"""A5: pose from the lattice — magnification and rotation in closed form.

The problem statement says the evaluation set may contain **9:1 to 11:1** magnification and
**1–2 degrees** of rotation. Correlation cannot search for those blindly: measured on our own data,
a 1.3% scale error drops the ZNCC peak from 0.856 to 0.262, because over a 100 px template that is
1.3 px of misalignment against a ~7 px lattice pitch. A grid fine enough to stay inside that basin
across the whole envelope is hundreds of correlations per pair.

So we do not search for the pose. We **measure** it.

The idea, and why it is the project's thesis in miniature
---------------------------------------------------------
Every other approach treats the repeating lattice as the enemy — it is what makes a wrong location
look correct. But a lattice with a known pitch is also the most precise **ruler** in the image, and
it is present in both acquisitions:

* a physical pitch ``P`` nm appears in the reference (1 nm/px) at spatial frequency ``1/P``;
* the same pitch appears in the search image (``s`` nm/px) at frequency ``s/P``;
* a rotation ``rho`` of the field of view rotates the whole reciprocal lattice by ``rho``.

So for any pair of corresponding reciprocal-lattice peaks, the **ratio of their radii is the
magnification** and the **difference of their angles is the rotation**. No search, one FFT each.

The one real difficulty is correspondence: which reference peak matches which search peak? Harmonics
and the two lattice axes give several plausible pairings. Rather than guess, every pairing votes for
the ``(scale, rotation)`` it implies, weighted by spectral power, and the pose with the most
agreement wins. Wrong pairings disagree with each other and scatter; correct ones pile up. Pairings
implying a scale outside the stated 9:1–11:1 envelope — a first harmonic matched against a second,
say — are rejected before they can vote at all.

Measured on 30 held-out pairs from our own generator (rotation +/-2 deg, scale 9–11); see
``docs/FINDINGS.md`` section 14.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class PoseEstimate:
    """Magnification and rotation relating a reference to a search image."""

    scale: float
    rotation_deg: float
    confidence: float   # share of the total spectral vote weight backing this pose, in [0, 1]
    n_votes: int

    def __str__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"scale={self.scale:.4f} rot={self.rotation_deg:+.3f}deg "
                f"conf={self.confidence:.2f} votes={self.n_votes}")


def _parabolic_offset(a: float, b: float, c: float) -> float:
    """Sub-bin peak offset from three samples, fitted in the log domain.

    Log rather than linear because a spectral peak of a windowed periodic signal is approximately
    Gaussian, and a parabola through the raw values is biased toward the centre bin ("peak
    locking"). The sub-bin refinement is not cosmetic here: the reference lattice sits at only
    ~15 frequency bins, so a 0.5-bin error is a 3% scale error — far outside what correlation
    tolerates.
    """
    a, b, c = max(a, 1e-30), max(b, 1e-30), max(c, 1e-30)
    la, lb, lc = np.log(a), np.log(b), np.log(c)
    denominator = la - 2.0 * lb + lc
    if abs(denominator) < 1e-30:
        return 0.0
    return float(np.clip(0.5 * (la - lc) / denominator, -1.0, 1.0))


def spectral_peaks(
    img: np.ndarray, min_period_px: float, max_period_px: float, n_peaks: int = 14,
) -> np.ndarray:
    """Dominant reciprocal-lattice peaks, as ``(fx, fy, power)`` rows in cycles/pixel.

    Uses ``rfft2``: the spectrum of a real image is Hermitian, so the half-plane ``fx >= 0`` carries
    every distinct lattice direction exactly once. That halves the cost and, more usefully, removes
    the duplicate +/- peaks that would otherwise each cast their own vote.
    """
    work = img.astype(np.float64)
    work = work - work.mean()
    rows, cols = work.shape

    # Hann window in both axes. Without it the frame edges produce a bright cross through the
    # origin that buys enough spectral power to outrank the genuine lattice peaks.
    work *= np.hanning(rows).reshape(-1, 1) * np.hanning(cols).reshape(1, -1)

    spectrum = np.fft.rfft2(work)
    power = spectrum.real ** 2 + spectrum.imag ** 2

    fy = np.fft.fftfreq(rows).reshape(-1, 1)
    fx = np.fft.rfftfreq(cols).reshape(1, -1)
    radius = np.hypot(fy, fx)

    band = (radius >= 1.0 / max_period_px) & (radius <= 1.0 / min_period_px)
    work_power = np.where(band, power, 0.0)

    # Suppression radius in bins, so one broadened peak cannot be harvested several times. The
    # random-walk line placement genuinely broadens the true peaks, so this must not be too tight.
    suppress = max(int(round(0.004 * max(rows, cols))), 2)

    n_rows, n_cols = work_power.shape
    peaks: list[tuple[float, float, float]] = []

    for _ in range(n_peaks):
        flat = int(np.argmax(work_power))
        iy, ix = np.unravel_index(flat, work_power.shape)
        value = float(work_power[iy, ix])
        if value <= 0.0:
            break

        # Sub-bin refinement. y wraps (fftfreq is circular), x does not (rfft is a half spectrum).
        dy = _parabolic_offset(
            work_power[(iy - 1) % n_rows, ix], value, work_power[(iy + 1) % n_rows, ix],
        )
        dx = (0.0 if ix == 0 or ix >= n_cols - 1 else
              _parabolic_offset(work_power[iy, ix - 1], value, work_power[iy, ix + 1]))

        fy_ref = (((iy + dy) + rows / 2.0) % rows - rows / 2.0) / rows
        fx_ref = (ix + dx) / cols
        peaks.append((fx_ref, fy_ref, value))

        y0, y1 = iy - suppress, iy + suppress + 1
        work_power[max(y0, 0):min(y1, n_rows), max(ix - suppress, 0):min(ix + suppress + 1, n_cols)] = 0.0
        # Wrap the suppression in y, since the lattice peak may sit near the fftfreq seam.
        if y0 < 0:
            work_power[y0 % n_rows:, max(ix - suppress, 0):min(ix + suppress + 1, n_cols)] = 0.0
        if y1 > n_rows:
            work_power[:y1 % n_rows, max(ix - suppress, 0):min(ix + suppress + 1, n_cols)] = 0.0

    return np.asarray(peaks, dtype=np.float64).reshape(-1, 3)


def _log_magnitude_spectrum(img: np.ndarray) -> np.ndarray:
    """Centred log-magnitude spectrum, Hann-windowed.

    Log rather than linear magnitude so the whole spectral *pattern* contributes to the match
    instead of only the two or three brightest peaks - which is the entire advantage of this
    method over peak matching.
    """
    work = img.astype(np.float64)
    work = work - work.mean()
    rows, cols = work.shape
    work *= np.hanning(rows).reshape(-1, 1) * np.hanning(cols).reshape(1, -1)
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(work)))
    return np.log1p(spectrum).astype(np.float32)


def _log_polar(spectrum: np.ndarray, r_lo: float, r_hi: float,
               n_radius: int, n_angle: int) -> np.ndarray:
    """Resample a centred spectrum onto a (angle, log-radius) grid.

    This is the change of variables that makes the problem linear: a magnification scales every
    radius by ``s``, which is a **translation** by ``log s`` along the log-radius axis, and a
    rotation is a **translation** along the angle axis. Two unknowns that were multiplicative and
    coupled become an ordinary 2D shift, recoverable by one cross-correlation.

    Only half the angular range is sampled: a real image's spectrum is symmetric under a 180 degree
    rotation, so the upper half-plane already contains every distinct direction.
    """
    rows, cols = spectrum.shape
    centre_y, centre_x = rows / 2.0, cols / 2.0

    angles = np.linspace(0.0, np.pi, n_angle, endpoint=False).reshape(-1, 1)
    radii = np.exp(np.linspace(np.log(r_lo), np.log(r_hi), n_radius)).reshape(1, -1)

    map_x = (centre_x + radii * np.cos(angles)).astype(np.float32)
    map_y = (centre_y + radii * np.sin(angles)).astype(np.float32)
    polar = cv2.remap(spectrum, map_x, map_y, cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)

    # Taper the log-radius axis. That axis is NOT periodic, but the cross-correlation below treats
    # it as if it were; without the taper the annulus edges alias into a spurious shift.
    polar *= np.hanning(n_radius).reshape(1, -1)
    polar -= polar.mean()
    return polar


def estimate_pose_fourier_mellin(
    reference: np.ndarray, search: np.ndarray,
    scale_range: tuple[float, float] = (9.0, 11.0),
    rotation_range: tuple[float, float] = (-2.0, 2.0),
    n_radius: int = 512, n_angle: int = 720,
    ref_radius_bins: tuple[float, float] = (4.0, 46.0),
) -> PoseEstimate | None:
    """Magnification and rotation by log-polar spectral registration (Reddy & Chatterji, 1996).

    Peak matching (:func:`estimate_pose`) asks a dozen discrete peaks to agree. It recovers rotation
    well but was measured at a 1.2% median scale error on our own data - larger than the ~1%
    correlation basin - because the DRAM presets differ in pitch and a coarse fundamental is
    intrinsically imprecise no matter how bright it is.

    This uses the whole spectrum at once. Both spectra are resampled onto the same log-radius grid,
    the search image's annulus pre-divided by the NOMINAL 10:1 so that only the residual mismatch
    has to be found; the leftover shift is then recovered to a fraction of a bin by upsampled-DFT
    cross-correlation. Sub-bin interpolation over a 512-point log-radius axis puts the theoretical
    scale resolution near 0.05%.
    """
    try:
        from skimage.registration import phase_cross_correlation
    except ImportError:  # pragma: no cover - skimage is a hard dependency, but fail soft
        return None

    s_lo, s_hi = scale_range
    nominal = float(np.sqrt(s_lo * s_hi))  # geometric centre: the shift we solve for is log-scale
    r_lo, r_hi = ref_radius_bins

    ref_polar = _log_polar(_log_magnitude_spectrum(reference), r_lo, r_hi, n_radius, n_angle)
    # The SAME physical band, pre-scaled by the nominal magnification, so the residual shift is
    # small and stays well inside the (non-periodic) log-radius window.
    search_polar = _log_polar(_log_magnitude_spectrum(search),
                              r_lo * nominal, r_hi * nominal, n_radius, n_angle)

    # normalization=None for the reason recorded in ADR-0009: the 'phase' default whitens by
    # magnitude, and on smooth inputs that amplifies numerical noise into a ~zero shift.
    shift, _, _ = phase_cross_correlation(
        search_polar, ref_polar, upsample_factor=50, normalization=None,
    )
    d_angle_bins, d_log_radius_bins = float(shift[0]), float(shift[1])

    log_step = (np.log(r_hi) - np.log(r_lo)) / (n_radius - 1)
    scale = float(nominal * np.exp(d_log_radius_bins * log_step))

    # Angle bins run over 180 degrees, and the sign is the same inversion measured for peak
    # matching: the field of view is sampled THROUGH the rotation, so image content turns the
    # other way.
    rotation = -_wrap_deg(d_angle_bins * 180.0 / n_angle)

    if not (s_lo <= scale <= s_hi) or not (rotation_range[0] <= rotation <= rotation_range[1]):
        return None

    return PoseEstimate(scale=scale, rotation_deg=rotation, confidence=1.0, n_votes=n_radius)


def _wrap_deg(angle: float) -> float:
    """Fold an angle into (-90, 90]. A lattice direction and its opposite are the same direction."""
    wrapped = (angle + 90.0) % 180.0 - 90.0
    return 90.0 if wrapped == -90.0 else wrapped


def estimate_pose(
    reference: np.ndarray, search: np.ndarray,
    scale_range: tuple[float, float] = (9.0, 11.0),
    rotation_range: tuple[float, float] = (-2.0, 2.0),
    scale_tol: float = 0.02, rotation_tol_deg: float = 0.5,
    min_confidence: float = 0.15,
) -> PoseEstimate | None:
    """Recover magnification and rotation from the two reciprocal lattices.

    Returns ``None`` when the lattices do not agree on any pose — a featureless pair, or one whose
    periodicity falls outside the searched band. The caller then falls back to the nominal 10:1
    rather than acting on a guess, so a failed measurement can never be worse than not measuring.

    ``rotation_deg`` is returned in the convention taken by
    :func:`src.driftlock.match.build_template` — that is, the value to rotate the *template* by in
    order to align it with the search image.
    """
    s_lo, s_hi = scale_range
    r_lo, r_hi = rotation_range

    # Physical pitches of interest are ~40-250 nm. The reference is 1 nm/px, so that is 40-250 px;
    # the band is opened out generously because presets vary and harmonics are useful votes.
    ref_peaks = spectral_peaks(reference, min_period_px=12.0, max_period_px=320.0)
    # The same structure in the search image, compressed by the (unknown) magnification. Bounded by
    # the extremes of the allowed envelope rather than by an assumed 10x.
    search_peaks = spectral_peaks(search, min_period_px=max(12.0 / s_hi, 2.5),
                                  max_period_px=320.0 / s_lo)

    if len(ref_peaks) == 0 or len(search_peaks) == 0:
        return None

    ref_weight = ref_peaks[:, 2] / (ref_peaks[:, 2].sum() + 1e-30)
    search_weight = search_peaks[:, 2] / (search_peaks[:, 2].sum() + 1e-30)

    ref_radius = np.hypot(ref_peaks[:, 0], ref_peaks[:, 1])
    search_radius = np.hypot(search_peaks[:, 0], search_peaks[:, 1])
    ref_angle = np.degrees(np.arctan2(ref_peaks[:, 1], ref_peaks[:, 0]))
    search_angle = np.degrees(np.arctan2(search_peaks[:, 1], search_peaks[:, 0]))

    scales: list[float] = []
    rotations: list[float] = []
    weights: list[float] = []

    for i in range(len(ref_peaks)):
        if ref_radius[i] <= 1e-12:
            continue
        for j in range(len(search_peaks)):
            implied_scale = search_radius[j] / ref_radius[i]
            if not (s_lo <= implied_scale <= s_hi):
                continue  # e.g. a first harmonic paired against a second - rejected before voting
            # SIGN, determined by measurement rather than derivation (12 Aug, another machine):
            # correlating the estimate against the manifest's true rotation over 40 dev pairs gave
            # r = -0.899 with the naive difference, so the sense is inverted. It follows from the
            # generator: the field of view is sampled THROUGH a rotation of rho, so content in the
            # image appears rotated by -rho, and the value build_template needs is +rho.
            implied_rotation = _wrap_deg(float(ref_angle[i] - search_angle[j]))
            if not (r_lo <= implied_rotation <= r_hi):
                continue

            # Weight by power AND by attainable precision. A peak sitting at frequency bin k can be
            # located to about a tenth of a bin, so its RELATIVE precision is ~1/k: a coarse pitch
            # near the DC end is worth far less than a fine one, even when it is brighter. The DRAM
            # presets differ enough in pitch (64-160 nm) that ignoring this lets an inherently
            # imprecise fundamental outvote a well-resolved harmonic. Measured: this is what takes
            # the median scale error from 1.09% to inside the correlation basin.
            precision = ref_radius[i] * search_radius[j] / (ref_radius[i] + search_radius[j])
            scales.append(float(implied_scale))
            rotations.append(implied_rotation)
            weights.append(float(np.sqrt(ref_weight[i] * search_weight[j]) * precision))

    if not scales:
        return None

    scale_votes = np.asarray(scales)
    rotation_votes = np.asarray(rotations)
    vote_weight = np.asarray(weights)
    total = float(vote_weight.sum()) + 1e-30

    # Each vote is scored by how much weight agrees with it. This is a one-pass mode finder: no
    # binning, so the answer never depends on where a histogram's edges happened to fall.
    agree = (
        (np.abs(scale_votes[:, None] - scale_votes[None, :]) <= scale_tol * scale_votes[None, :])
        & (np.abs(rotation_votes[:, None] - rotation_votes[None, :]) <= rotation_tol_deg)
    )
    support = agree @ vote_weight

    best = int(np.argmax(support))
    members = agree[best]
    member_weight = vote_weight[members]
    confidence = float(support[best] / total)

    if confidence < min_confidence:
        return None

    # Refine to the weighted centroid of the agreeing votes rather than taking the single winner:
    # the mode picks the cluster, the centroid places it.
    scale = float((scale_votes[members] * member_weight).sum() / (member_weight.sum() + 1e-30))
    rotation = float((rotation_votes[members] * member_weight).sum() / (member_weight.sum() + 1e-30))

    return PoseEstimate(scale=scale, rotation_deg=rotation,
                        confidence=confidence, n_votes=int(members.sum()))
