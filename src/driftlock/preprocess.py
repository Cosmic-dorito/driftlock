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
