"""SEM image formation, applied in physically correct order.

The order matters and process engineers notice if it is wrong. Noise added before blur, or edge
contrast added after the beam PSF, produces images that look plausible to a computer-vision person
and obviously synthetic to a microscopist::

    1. layout                  device geometry, 1 nm/px
    2. SE edge brightening     secondary-electron yield rises at edges     <- the starter omits this
    3. charging shading        slow multiplicative field from local charging
    4. beam PSF                Gaussian spot, optionally astigmatic
    5. geometry                rotation and magnification, with pixel-area integration
    6. raster drift            per-row shear + vibration jitter
    7. barrel distortion       scan-linearity error
    8. shot noise              Poisson, set by dose
    9. detector noise          additive Gaussian read noise
    10. speckle / salt-pepper / charging streaks / vignette / gamma
    11. quantise               uint8

Two things here that the sponsor's published generator cannot do, and which the problem statement
says will be tested: **rotation (1-2 degrees)** and **scale variation (9:1 to 11:1)**.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass
class AcquisitionParams:
    """One acquisition's settings. Reference and search get separate instances."""

    pixel_size_nm: float = 1.0
    beam_spot_size_nm: float = 5.0
    dose: float = 2000.0
    detector_noise_sigma: float = 2.0

    astigmatism_ratio: float = 1.0
    shear_amplitude_px: float = 0.0
    drift_jitter_px: float = 0.0
    barrel_distortion_k: float = 0.0
    vignette_strength: float = 0.0
    gamma: float = 1.0
    speckle_sigma: float = 0.0
    salt_pepper_prob: float = 0.0
    charging_streak_prob: float = 0.0
    charging_streak_intensity: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------------------
# 2-3. Material and surface response
# ---------------------------------------------------------------------------------------

def secondary_electron_response(layout: np.ndarray, edge_gain: float = 0.55,
                                edge_sigma_nm: float = 2.0, pixel_size_nm: float = 1.0,
                                illumination_deg: float | None = None,
                                rng: np.random.Generator | None = None) -> np.ndarray:
    """Convert a layout into an SE intensity map, with edge brightening.

    **This is the main physical term the sponsor's generator omits.** Theirs paints flat grey levels
    per material and max-composites them, which renders as an outline drawing rather than an SEM
    image. Real SEM topographic contrast is dominated by the variation of secondary-electron yield
    with local surface tilt: near an edge the beam stays within the SE escape depth over a longer
    path length, so more secondaries escape and edges appear bright.

    Modelled as two terms:

    * an **isotropic edge halo**, from the gradient magnitude of the smoothed layout - equivalent to
      a signed-distance formulation but far cheaper on a 10000x10000 canvas;
    * a **directional term**, since the detector sits off-axis, so edges facing it are brighter than
      edges facing away. This is what stops the result looking like a symmetric outline.

    Physical basis: SE yield vs. surface tilt, e.g. Reimer, *Scanning Electron Microscopy*, and the
    Monte Carlo SE imaging literature (see docs/REFERENCES.md).
    """
    work = layout.astype(np.float32)
    sigma_px = max(edge_sigma_nm / max(pixel_size_nm, 1e-6), 0.6)
    smooth = cv2.GaussianBlur(work, (0, 0), sigma_px)

    gx = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3)

    halo = cv2.magnitude(gx, gy)
    peak = float(np.percentile(halo, 99.5)) + 1e-6
    halo = np.clip(halo / peak, 0.0, 1.0)

    if illumination_deg is None:
        illumination_deg = float(rng.uniform(0, 360)) if rng is not None else 45.0
    theta = np.deg2rad(illumination_deg)
    directional = (gx * np.cos(theta) + gy * np.sin(theta)) / peak
    directional = np.clip(directional, 0.0, 1.0)

    out = work + 255.0 * edge_gain * (0.7 * halo + 0.3 * directional)
    return np.clip(out, 0, 255)


def charging_field(shape: tuple[int, int], strength: float,
                   rng: np.random.Generator) -> np.ndarray:
    """Slow multiplicative shading from local charge accumulation.

    A low-order 2D polynomial, because charging varies over the field of view rather than pixel to
    pixel. Distinct from vignetting, which is radially symmetric and fixed by the optics.
    """
    if strength <= 0:
        return np.ones(shape, dtype=np.float32)
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xx = (xx / max(w - 1, 1)) * 2 - 1
    yy = (yy / max(h - 1, 1)) * 2 - 1
    c = rng.normal(0, 1, size=6)
    field = (c[0] + c[1] * xx + c[2] * yy + c[3] * xx * yy + c[4] * xx**2 + c[5] * yy**2)
    field = field / (np.abs(field).max() + 1e-6)
    return (1.0 + strength * field).astype(np.float32)


# ---------------------------------------------------------------------------------------
# 4-5. Optics and geometry
# ---------------------------------------------------------------------------------------

def beam_psf(img: np.ndarray, spot_size_nm: float, pixel_size_nm: float,
             astigmatism_ratio: float = 1.0) -> np.ndarray:
    """Gaussian beam-spot blur. ``astigmatism_ratio != 1`` makes the spot elliptical."""
    sigma_x = max(spot_size_nm / max(pixel_size_nm, 1e-6), 1e-3)
    sigma_y = max(sigma_x * astigmatism_ratio, 1e-3)
    return cv2.GaussianBlur(img, (0, 0), sigmaX=sigma_x, sigmaY=sigma_y)


def resample_field_of_view(canvas: np.ndarray, out_size: int, nm_per_px: float,
                           rotation_deg: float, centre_nm: tuple[float, float]) -> np.ndarray:
    """Sample a rotated, scaled field of view out of the fine canvas.

    Two-step, and the first step is the one people forget: a detector pixel **integrates over its
    own area**, so before point-sampling at ``nm_per_px`` the canvas must be box-filtered over that
    pixel footprint. Skipping it aliases the lattice badly - and a periodic structure is exactly the
    signal that aliases worst.

    Doing area integration *before* the warp (rather than relying on an interpolation flag) is also
    what lets this support arbitrary rotation and non-integer magnification, which is the whole
    point: ``cv2.INTER_AREA`` cannot express a rotation.
    """
    box = max(int(round(nm_per_px)), 1)
    integrated = cv2.blur(canvas, (box, box)) if box > 1 else canvas

    theta = np.deg2rad(rotation_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    half = out_size / 2.0
    cx, cy = centre_nm

    # Maps output pixel -> canvas coordinate (WARP_INVERSE_MAP).
    m = np.array([
        [nm_per_px * cos_t, -nm_per_px * sin_t,
         cx - nm_per_px * (cos_t * half - sin_t * half)],
        [nm_per_px * sin_t, nm_per_px * cos_t,
         cy - nm_per_px * (sin_t * half + cos_t * half)],
    ], dtype=np.float32)

    return cv2.warpAffine(
        integrated, m, (out_size, out_size),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REFLECT,
    )


def canvas_to_search_coords(x_nm: float, y_nm: float, out_size: int, nm_per_px: float,
                            rotation_deg: float, centre_nm: tuple[float, float]) -> tuple[float, float]:
    """Exact inverse of :func:`resample_field_of_view` for a single point.

    This is how ground truth is computed. It is derived analytically from the same matrix used to
    render, rather than measured back off the image, so the ground truth is exact and continuous -
    which is what makes an honest sub-pixel accuracy claim possible.

    The half-pixel term, and why it is not a fudge (fixed 12 Aug, MacBook Air M2)
    ----------------------------------------------------------------------------
    Two different conventions meet here and they differ by exactly half a pixel:

    * ``warpAffine`` samples at **pixel centres**, so the value it returns for output index ``u`` is
      the scene at index ``u`` - the inverse above lands in *pixel-index* space;
    * the problem statement's centre convention is ``origin + size/2``, verified as H2 against the
      sponsor's manifests: content occupying pixels ``x0 .. x0+99`` has centre ``x0 + 50``, whereas
      those pixel centres have midpoint ``x0 + 49.5``.

    So a coordinate in pixel-index space must be shifted by ``+0.5`` to be quoted in the
    problem's convention. Without it our ground truth sat half a pixel from the sponsor's for the
    same physical situation - and since the sub-pixel threshold is 0.5 px, that alone would have
    made **every** sub-pixel claim on our own benchmark fail while the sponsor's data passed.

    It was found by measurement, not by reading: with the true pose supplied, the residual on 40
    dev pairs was ``dy = +0.503 px with a standard deviation of 0.035`` - far too consistent to be
    anything but a convention.
    """
    theta = np.deg2rad(rotation_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    cx, cy = centre_nm
    dx, dy = x_nm - cx, y_nm - cy
    u = (dx * cos_t + dy * sin_t) / nm_per_px + out_size / 2.0
    v = (-dx * sin_t + dy * cos_t) / nm_per_px + out_size / 2.0
    return float(u) + 0.5, float(v) + 0.5


# ---------------------------------------------------------------------------------------
# 6-7. Scan artefacts
# ---------------------------------------------------------------------------------------

def raster_drift(img: np.ndarray, shear_amplitude_px: float, jitter_std_px: float,
                 rng: np.random.Generator) -> np.ndarray:
    """Progressive row-to-row shear (stage drift over scan time) plus per-row vibration jitter."""
    if shear_amplitude_px == 0 and jitter_std_px == 0:
        return img
    h, w = img.shape
    rows = np.arange(h)
    shear = shear_amplitude_px * (rows / max(h - 1, 1))
    jitter = rng.normal(0, jitter_std_px, size=h) if jitter_std_px > 0 else np.zeros(h)
    shift = (shear + jitter).astype(np.float32)

    map_x = np.arange(w, dtype=np.float32)[None, :] + shift[:, None]
    map_y = np.tile(np.arange(h, dtype=np.float32)[:, None], (1, w))
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def barrel_distortion(img: np.ndarray, k: float) -> np.ndarray:
    """Radial scan-linearity error: barrel for k>0, pincushion for k<0."""
    if k == 0.0:
        return img
    h, w = img.shape
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = (xx - cx) / cx, (yy - cy) / cy
    factor = 1.0 + k * (nx**2 + ny**2)
    return cv2.remap(img, (nx * factor) * cx + cx, (ny * factor) * cy + cy,
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------------------------------
# 8-10. Noise and detector response
# ---------------------------------------------------------------------------------------

def shot_noise(img: np.ndarray, dose: float, rng: np.random.Generator) -> np.ndarray:
    """Poisson shot noise. ``dose`` is a proxy for electron count per pixel.

    Signal-dependent by construction: bright pixels are noisier than dark ones. That is precisely
    why plain correlation is not the maximum-likelihood estimator on raw intensity.
    """
    counts = np.clip(img.astype(np.float64) / 255.0 * dose, 0, None)
    return np.clip(rng.poisson(counts) / dose * 255.0, 0, 255)


def detector_noise(img: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    if sigma <= 0:
        return img
    return np.clip(img + rng.normal(0, sigma, size=img.shape), 0, 255)


def speckle_noise(img: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """Multiplicative gain variation: noise magnitude scales with brightness."""
    if sigma <= 0:
        return img
    return np.clip(img * (1.0 + rng.normal(0, sigma, size=img.shape)), 0, 255)


def salt_and_pepper(img: np.ndarray, prob: float, rng: np.random.Generator) -> np.ndarray:
    """Impulse noise: dead/hot detector pixels and discharge events."""
    if prob <= 0:
        return img
    out = img.copy()
    hit = rng.random(img.shape) < prob
    salt = rng.random(img.shape) < 0.5
    out[hit & salt] = 255
    out[hit & ~salt] = 0
    return out


def charging_streaks(img: np.ndarray, streaks_per_100_rows: float, intensity: float,
                     rng: np.random.Generator) -> np.ndarray:
    """Bright horizontal bands from local charging on insulating regions."""
    if streaks_per_100_rows <= 0 or intensity <= 0:
        return img
    h, w = img.shape
    out = img.copy()
    for _ in range(rng.poisson(max(streaks_per_100_rows * h / 100.0, 0))):
        row = int(rng.integers(0, h))
        band = max(1, int(abs(rng.normal(2, 1))))
        out[max(row - band, 0):min(row + band, h), :] += intensity * rng.uniform(0.5, 1.0) * 25.5
    return np.clip(out, 0, 255)


def vignette(img: np.ndarray, strength: float) -> np.ndarray:
    """Radial falloff from off-axis collection efficiency."""
    if strength <= 0:
        return img
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    r = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2) / np.sqrt(2)
    return np.clip(img * (1.0 - strength * np.clip(r, 0, 1) ** 2), 0, 255)


def apply_gamma(img: np.ndarray, gamma: float) -> np.ndarray:
    """Detector gain nonlinearity / contrast mis-calibration."""
    if gamma == 1.0:
        return img
    return np.clip(np.power(np.clip(img / 255.0, 0, 1), gamma) * 255.0, 0, 255)


def detector_chain(img: np.ndarray, params: AcquisitionParams,
                   rng: np.random.Generator) -> np.ndarray:
    """Steps 6-11, applied in order, to an already-sampled frame.

    Called with an INDEPENDENT rng per acquisition: the reference and the search image are two
    separate captures of the same physical scene, so their noise must be uncorrelated. Sharing a
    stream would make the search image's noise partly predictable from the reference and quietly
    inflate every accuracy number.
    """
    out = raster_drift(img, params.shear_amplitude_px, params.drift_jitter_px, rng)
    out = barrel_distortion(out, params.barrel_distortion_k)
    out = shot_noise(out, params.dose, rng)
    out = detector_noise(out, params.detector_noise_sigma, rng)
    out = speckle_noise(out, params.speckle_sigma, rng)
    out = salt_and_pepper(out, params.salt_pepper_prob, rng)
    out = vignette(out, params.vignette_strength)
    out = apply_gamma(out, params.gamma)
    out = charging_streaks(out, params.charging_streak_prob,
                           params.charging_streak_intensity, rng)
    return np.clip(out, 0, 255).astype(np.uint8)
