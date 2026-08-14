"""Preprocessing stages A1-A2: put both images into a domain where correlation is the right tool.

Each function targets a SPECIFIC degradation identified in the verified hypotheses
(results/hypotheses.md), rather than being generic image cleanup. Every one is an ablation row and
has to earn its place by moving a measured number (R9).

The organising idea is the project's thesis: we know the forward model, so rather than tuning a
similarity measure until it copes, we undo the known corruptions and let the estimator be optimal.
"""

from __future__ import annotations

import cv2
import numpy as np


def median_denoise(img: np.ndarray, ksize: int = 3) -> np.ndarray:
    """Remove salt-and-pepper impulse noise.

    The generator can force a fraction of pixels to 0 or 255 (dead/hot detector pixels, discharge
    events). Those are unbounded outliers: a single saturated pixel shifts a local mean far more
    than the signal does, and correlation has no defence against it. A 3x3 median removes them
    essentially exactly while leaving edges intact, which a Gaussian would not.
    """
    work = img.astype(np.float32)
    return cv2.medianBlur(work, ksize)


def row_destripe(img: np.ndarray) -> np.ndarray:
    """Remove charging streaks.

    The generator adds bright horizontal bands: whole rows offset by a constant
    (``out[lo:hi, :] += intensity``). Because the corruption is constant along a row, subtracting
    each row's median removes it almost exactly while costing nothing where there is no streak.

    This is a good example of the thesis paying off: a generic high-pass filter would blur real
    structure to suppress the same artefact, whereas knowing the artefact is row-constant makes the
    correction both exact and free.
    """
    work = img.astype(np.float32)
    row_median = np.median(work, axis=1, keepdims=True)
    return work - row_median + float(np.median(row_median))


def destreak(img: np.ndarray, sigmas: float = 4.0, baseline_rows: int = 101,
             lattice_rows: int = 13) -> np.ndarray:
    """Remove charging streaks WITHOUT removing the horizontal structure they sit on.

    Why :func:`row_destripe` fails, and why this is not the same thing. That function subtracts every
    row's median unconditionally. On this layout the word lines ARE horizontal, so a legitimate row
    mean varies strongly and systematically down the image - subtracting it removes the signal along
    with the artefact. Measured, it costs 20.0% -> 36.7% mis-lock on clean data (FINDINGS 26).

    The artefact is narrower than that treatment. The generator adds ``out[lo:hi, :] += intensity``:
    a constant offset over a *contiguous band* of rows, leaving every other row untouched. So the
    corruption is not "each row has an offset", it is "a few rows have an offset", and the
    correction should be conditional rather than universal:

    1. take the row-mean profile;
    2. estimate a smooth baseline for it with a wide median filter, which follows the lattice's own
       slow variation but cannot follow a step;
    3. flag only rows whose deviation from that baseline exceeds ``sigmas`` robust deviations;
    4. subtract the deviation from *those rows only*.

    On an image with no streaks nothing is flagged and the input is returned unchanged - not
    approximately unchanged, but the same array values. That is the property row destriping lacked
    and the reason it could only ever trade one regime against another.

    Targeted here because the failure decomposition says so: under charging streaks 23.3% of pairs
    lose the true location before it is ever a candidate, against 3.3% lost at final ranking. The
    streak destroys the correlation peak upstream of top-K, so no re-ranking stage could reach it.

    **MEASURED AND NOT SHIPPED (14 Aug).** It does what it was built to do and still does not earn
    its place:

    ==========================  =========  ==========
    split                       without    with
    ==========================  =========  ==========
    charging streaks (n=30)        33.3%      26.7%
    nominal control (n=30)         20.0%      20.0%
    100 held-out pairs             16.0%      17.0%
    ==========================  =========  ==========

    Inert on the clean control, a 2-pair gain on the streaks it targets - and on the 100 reported
    pairs it **breaks one and fixes none**, for +56 ms. The median filter cleared this same bar with
    0 broken, 2 fixed and -3 ms, which is why that one ships and this one does not (ADR-0027). A
    2-pair gain inside the sampling floor does not buy a regression on the reported set.

    Kept, unwired, with its numbers, per R9. If the released data turns out to be streak-heavy this
    is one line from being enabled - but on the evidence available it is a net negative.
    """
    work = img.astype(np.float32)
    profile = work.mean(axis=1)

    # Attenuate the LATTICE before looking for outliers, or the lattice becomes the outlier.
    #
    # The first version of this skipped straight to a robust baseline and flagged deviations from
    # it. On a layout whose word lines run horizontally with a short pitch, the bright rows are a
    # low-duty-cycle spike train in the row-mean profile - so a median baseline sits near the dark
    # level and every word line reads as a 4-sigma anomaly. A hand-built test with lines every 8
    # rows caught it: the "correction" erased the lines and left a residual seven times larger than
    # the streak it was removing.
    #
    # The two are not separable by amplitude. They ARE separable by vertical frequency: the lattice
    # oscillates with a period of a few pixels, a charging band spans tens of rows. So average over
    # several lattice periods first, which cancels the oscillation and preserves the band, and only
    # then look for departures from a wide baseline.
    smooth_w = max(3, lattice_rows | 1)
    kernel = np.ones(smooth_w, dtype=np.float32) / smooth_w
    smoothed = np.convolve(np.pad(profile, smooth_w // 2, mode="edge"), kernel, mode="valid")

    width = max(3, baseline_rows | 1)
    pad = width // 2
    padded = np.pad(smoothed, pad, mode="edge")
    baseline = np.array([np.median(padded[i:i + width]) for i in range(smoothed.size)],
                        dtype=np.float32)

    deviation = smoothed - baseline
    # Median absolute deviation, scaled to be comparable with a standard deviation for Gaussian
    # data. Robust because the streaked rows are exactly the outliers we must not let set the scale.
    mad = float(np.median(np.abs(deviation - np.median(deviation))))
    scale = 1.4826 * mad
    if scale <= 1e-6:
        return work

    flagged = np.abs(deviation) > sigmas * scale
    if not flagged.any():
        return work
    correction = np.where(flagged, deviation, 0.0).astype(np.float32)
    return work - correction[:, None]


def generalized_anscombe(
    img: np.ndarray, gain: float = 1.0, sigma: float = 0.0, offset: float = 0.0
) -> np.ndarray:
    """A1: variance-stabilise Poisson-Gaussian noise.

    Verified as H3: the search image's noise is Poisson (shot) followed by Gaussian (detector), and
    the measured per-pixel variance is affine in the mean rather than constant. That matters because
    zero-mean normalised cross-correlation is the maximum-likelihood estimator only under additive
    noise of CONSTANT variance. Under shot noise, bright pixels are noisier than dark ones, so plain
    ZNCC systematically over-trusts the bright contacts - the very features it should weight least.

    The generalized Anscombe transform (Makitalo & Foi, IEEE TIP 22(1):91-103, 2013) maps
    Poisson-Gaussian data to approximately unit-variance Gaussian:

        f(x) = 2/gain * sqrt(gain*x + 3/8*gain^2 + sigma^2 - gain*offset)

    After it, correlation is (approximately) the ML estimator. Before it, it is not.

    ``gain`` and ``sigma`` may be estimated per pair rather than assumed - see
    :func:`estimate_noise_params`, which is the zero-training test-time calibration of step A4.
    """
    work = img.astype(np.float64)
    inner = gain * work + (3.0 / 8.0) * gain ** 2 + sigma ** 2 - gain * offset
    return (2.0 / gain * np.sqrt(np.maximum(inner, 0.0))).astype(np.float32)


def estimate_noise_params(img: np.ndarray, n_bins: int = 24) -> tuple[float, float]:
    """Estimate Poisson gain and Gaussian sigma from a single image (step A4).

    Under Poisson-Gaussian noise the local variance is affine in the local mean:

        Var = gain * mean + sigma^2

    so regressing one on the other over homogeneous windows recovers both parameters with no
    training and no assumption about which generator produced the image. That is the point: it
    self-calibrates on the evaluator's data even if their degradation settings differ from ours.

    Windows are restricted to low-gradient regions, because structure edges inflate the local
    variance and would otherwise be mistaken for noise.
    """
    work = img.astype(np.float64)
    k = 5
    mean = cv2.blur(work, (k, k))
    var = np.maximum(cv2.blur(work * work, (k, k)) - mean * mean, 0.0)

    gx = cv2.Sobel(mean, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(mean, cv2.CV_64F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    flat = grad < np.percentile(grad, 20)

    m, v = mean[flat], var[flat]
    if m.size < 100:
        return 1.0, float(np.sqrt(max(np.median(var), 1e-6)))

    edges = np.linspace(m.min(), m.max(), n_bins + 1)
    idx = np.digitize(m, edges)
    bm, bv = [], []
    for b in range(1, len(edges)):
        sel = idx == b
        if sel.sum() > 50:
            bm.append(float(m[sel].mean()))
            bv.append(float(np.median(v[sel])))

    if len(bm) < 4:
        return 1.0, float(np.sqrt(max(np.median(var), 1e-6)))

    gain, intercept = np.polyfit(bm, bv, 1)
    gain = float(np.clip(gain, 1e-3, 1e3))
    sigma = float(np.sqrt(max(intercept, 0.0)))
    return gain, sigma


def phase_congruency_channel(
    img: np.ndarray, n_scales: int = 4, min_wavelength: float = 3.0, mult: float = 2.1,
    sigma_onf: float = 0.55,
) -> np.ndarray:
    """A2: a contrast- and illumination-invariant feature channel.

    The search image can carry gamma, vignetting and a 10x dose difference relative to the
    reference. All three change pixel AMPLITUDES; none of them change where the image's Fourier
    components come into phase. Phase congruency (Kovesi) measures exactly that phase alignment, so
    it is invariant to those nuisances by construction rather than by tuning.

    This is a monogenic/log-Gabor approximation: an isotropic log-Gabor bank, with congruency taken
    as the ratio of the summed even-odd energy to the summed amplitude. It is not Kovesi's full
    oriented implementation - we do not need orientation selectivity here, only an amplitude-
    invariant edge-strength map - and it is far cheaper.
    """
    work = img.astype(np.float32)
    rows, cols = work.shape

    fy = np.fft.fftfreq(rows).reshape(-1, 1)
    fx = np.fft.fftfreq(cols).reshape(1, -1)
    radius = np.sqrt(fx ** 2 + fy ** 2)
    radius[0, 0] = 1.0  # avoid log(0); the DC term is removed below anyway

    fft = np.fft.fft2(work)
    sum_amplitude = np.zeros((rows, cols), dtype=np.float64)
    sum_energy = np.zeros((rows, cols), dtype=np.float64)

    wavelength = min_wavelength
    for _ in range(n_scales):
        f0 = 1.0 / wavelength
        log_gabor = np.exp(-((np.log(radius / f0)) ** 2) / (2 * np.log(sigma_onf) ** 2))
        log_gabor[0, 0] = 0.0

        response = np.fft.ifft2(fft * log_gabor)
        even, odd = response.real, response.imag
        amplitude = np.sqrt(even ** 2 + odd ** 2)

        sum_amplitude += amplitude
        sum_energy += even
        wavelength *= mult

    # Congruency in [0, 1]; the epsilon keeps flat, featureless regions from amplifying noise.
    congruency = np.abs(sum_energy) / (sum_amplitude + 1e-4)
    return (congruency * 255.0).astype(np.float32)


def local_contrast_normalize(img: np.ndarray, box: int = 21) -> np.ndarray:
    """Divide out slowly-varying gain: an alternative to phase congruency for the same nuisances.

    Cheaper and more predictable than :func:`phase_congruency_channel`, and it removes vignetting
    and linearises gamma to first order. Kept as a separate ablation row so the two can be compared
    on data instead of by argument.
    """
    work = img.astype(np.float32)
    mean = cv2.blur(work, (box, box))
    sq = cv2.blur(work * work, (box, box))
    std = np.sqrt(np.maximum(sq - mean * mean, 0.0))
    return (work - mean) / (std + 1.0)
