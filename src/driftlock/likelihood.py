"""Maximum-likelihood re-scoring under the measured Poisson-Gaussian noise model.

The thesis says localization is a **maximum-likelihood inverse problem**. Everything up to here has
nevertheless ranked candidates by ZNCC, which is the ML estimator only under *additive,
constant-variance Gaussian* noise. Our noise is not that, and we measured it: H3 confirmed
Poisson (shot) followed by Gaussian (detector), with variance affine in the mean,
``Var = 1.75*mean + 426`` on the sponsor's data.

Why that matters for the failure we actually have
-------------------------------------------------
Under shot noise a bright pixel is genuinely noisier than a dark one, so ZNCC - which weights every
pixel equally - **over-trusts the bright pixels**. On a DRAM array the bright pixels are the contacts
and line edges, and those are the most *periodic* part of the image: they look the same on every
repeat. The aperiodic evidence that says *which* repeat you are on lives in small displacements of
those edges, and it competes against noise that ZNCC has mis-weighted.

Weighting each residual by its own variance is not a tweak, it is the estimator the measured noise
model calls for. Measured on real pairs the discriminating margin is only ~0.016 of correlation
(H8), so a modest change in effective SNR is worth attempting on exactly this failure.

No free parameters
------------------
The gain and offset relating template to patch are solved in closed form per candidate, and the
noise model ``(alpha, beta)`` is estimated **from the search image itself**. Nothing here is tuned,
which is deliberate: PADM had two tuned constants and overfit to one lattice geometry (ADR-0012).

MEASURED RESULT: it does not beat ZNCC. Off by default.
-------------------------------------------------------
40 dev pairs, 12 Aug, another machine:

======================  ==========  ================
ranking                 truth at    mean rank of
                        rank 1      truth
======================  ==========  ================
ZNCC                    82.1%       2.62
log-likelihood          79.5%       3.77
======================  ==========  ================

It improved the rank on 2 pairs and worsened it on 4; end to end, mis-lock 20.0% -> 22.5%.

**The premise was right and the conclusion still wrong, which is the interesting part.** The noise
really is signal-dependent - fitting it here gives ``alpha = 0.80``, nowhere near the 0 a purely
additive sensor would give - so ZNCC really is the wrong estimator for the *noise*. But photon
noise is not what limits this comparison. The template is an imperfect prediction of the patch:
the PSF is not identical between acquisitions, the drift is only partly removed, and the alignment
is sub-pixel at best. Those **model-mismatch** residuals are larger than the shot noise and they
are structured, so weighting by photon variance sharpens the wrong term.

ZNCC survives precisely because it is agnostic about magnitudes: it asks only whether the shapes
agree, which is the robust question when your forward model is approximate. The lesson generalises
past this project - *the ML estimator for your noise model is not the ML estimator for your problem
unless the model mismatch is smaller than the noise.*

Kept in the tree and in the ablation as a measured negative (R9).
"""

from __future__ import annotations

import numpy as np


def estimate_noise_model(image: np.ndarray, n_bins: int = 24) -> tuple[float, float]:
    """Fit ``Var = alpha * mean + beta`` from a single image.

    Uses the horizontal difference image: neighbouring pixels see almost the same scene, so their
    difference is dominated by noise rather than by structure. Within each intensity bin the noise
    variance is estimated robustly by the median absolute deviation, which ignores the minority of
    differences that straddle a real edge. A plain per-block variance would measure the lattice.

    Returns ``(alpha, beta)``. ``alpha`` is the Poisson (signal-dependent) part and ``beta`` the
    constant detector part, so a purely additive sensor would give ``alpha = 0``.
    """
    work = image.astype(np.float64)
    # Difference of horizontal neighbours, scaled so its variance equals the per-pixel variance.
    diff = (work[:, 1:] - work[:, :-1]) / np.sqrt(2.0)
    level = 0.5 * (work[:, 1:] + work[:, :-1])

    lo, hi = float(level.min()), float(level.max())
    if hi - lo < 1e-6:
        return 0.0, float(np.var(diff))

    edges = np.linspace(lo, hi, n_bins + 1)
    index = np.clip(np.digitize(level.ravel(), edges) - 1, 0, n_bins - 1)
    flat_diff = diff.ravel()

    means, variances = [], []
    for b in range(n_bins):
        sample = flat_diff[index == b]
        if sample.size < 64:
            continue
        # 1.4826 * MAD is a robust standard-deviation estimate for Gaussian data.
        mad = float(np.median(np.abs(sample - np.median(sample))))
        means.append(0.5 * (edges[b] + edges[b + 1]))
        variances.append((1.4826 * mad) ** 2)

    if len(means) < 3:
        return 0.0, float(np.var(diff))

    alpha, beta = np.polyfit(np.asarray(means), np.asarray(variances), 1)
    # A negative slope or offset is physically meaningless and would produce negative variances.
    return max(float(alpha), 0.0), max(float(beta), 1e-6)


def log_likelihood(
    patch: np.ndarray, template: np.ndarray, alpha: float, beta: float,
) -> float:
    """Log-likelihood that ``patch`` is a noisy observation of ``template``.

    Gain and offset are nuisance parameters - the two acquisitions differ in dose and detector gain -
    so they are profiled out in closed form rather than assumed. That is what keeps this comparable
    to ZNCC, which is invariant to exactly those two degrees of freedom by construction.
    """
    obs = patch.astype(np.float64).ravel()
    model = template.astype(np.float64).ravel()

    # Least-squares gain/offset:  obs ~ a * model + b
    model_mean, obs_mean = model.mean(), obs.mean()
    centred_model = model - model_mean
    denominator = float((centred_model * centred_model).sum())
    if denominator < 1e-12:
        return -np.inf
    gain = float((centred_model * (obs - obs_mean)).sum() / denominator)
    offset = float(obs_mean - gain * model_mean)

    predicted = gain * model + offset
    variance = alpha * np.clip(predicted, 0.0, None) + beta

    residual = obs - predicted
    # Dropping the constant -0.5*N*log(2*pi): only differences between candidates matter.
    return float(-0.5 * np.sum(residual * residual / variance + np.log(variance)))


def rescore_by_likelihood(
    search: np.ndarray, reference: np.ndarray, candidates: list, config,
) -> list:
    """Rank candidates by likelihood under the measured noise model instead of by ZNCC.

    Each candidate keeps its original score in ``extra['zncc']`` so the ablation can compare the
    two rankings directly. Candidates whose footprint falls outside the frame are left where they
    are rather than being scored on a truncated patch.
    """
    from src.driftlock.match import build_template

    alpha, beta = estimate_noise_model(search)

    height, width = search.shape[:2]
    cache: dict[tuple[float, float], np.ndarray] = {}
    scored = []

    for cand in candidates:
        key = (round(cand.scale, 6), round(cand.rotation_deg, 6))
        if key not in cache:
            cache[key] = build_template(reference, cand.scale, cand.rotation_deg)
        template = cache[key]
        th, tw = template.shape[:2]

        x0 = int(round(cand.x - tw / 2.0))
        y0 = int(round(cand.y - th / 2.0))
        if x0 < 0 or y0 < 0 or x0 + tw > width or y0 + th > height:
            cand.extra["log_likelihood"] = -np.inf
            scored.append(cand)
            continue

        patch = search[y0:y0 + th, x0:x0 + tw]
        value = log_likelihood(patch, template, alpha, beta)
        cand.extra["zncc"] = cand.score
        cand.extra["log_likelihood"] = value
        scored.append(cand)

    finite = [c for c in scored if np.isfinite(c.extra.get("log_likelihood", -np.inf))]
    if not finite:
        return candidates

    # Rank by likelihood alone. Blending it with ZNCC would reintroduce a weight to tune, and a
    # tuned weight is exactly what made PADM fail to generalise.
    scored.sort(key=lambda c: c.extra.get("log_likelihood", -np.inf), reverse=True)
    return scored
