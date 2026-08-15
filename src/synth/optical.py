"""RGB optical image formation — the spec's bonus modality, and a genuinely different problem.

The Drift-Sense problem statement lists an "RGB optical-image extension" as an optional bonus after
the grayscale SEM task. It is not the SEM path with three copies of the same picture: an optical
microscope forms its image by a completely different mechanism, and the two differences that matter
here both cut against the SEM assumptions the rest of this project is built on.

1. DIFFRACTION, NOT A BEAM SPOT
------------------------------
An SEM's resolution is set by the probe size - about 5 nm here, so a 64 nm word-line pitch is
resolved with room to spare. An optical microscope is limited by ``0.61 * lambda / NA``: at
lambda = 550 nm and NA = 0.90 that is **373 nm**, which is *six times larger than the DRAM pitch.*

**So the fine lattice is not blurry in the optical modality. It is absent.** It averages to a flat
tone, and every identifying feature has to come from structure coarser than the diffraction limit -
the mats, the peripheral strips, and their aperiodic variation. That inverts the SEM problem, where
the lattice is the ruler and the aperiodic residual is the fingerprint.

To keep the task meaningful the optical modality is therefore imaged at a coarser plate scale
(``PIXEL_SIZE_OPTICAL_NM``): the reference covers ~50 um and the search ~500 um, so the *mat array*
plays the role the cell array plays in SEM. The ambiguity is preserved - a periodic array of mats,
one of which is the answer - while the physics is honestly different.

2. COLOUR IS THIN-FILM INTERFERENCE, NOT DYE
--------------------------------------------
A patterned wafer reflects differently at each wavelength because each material sits under a
different film stack, and the reflectance oscillates with ``4 pi n d / lambda``. That is why wafer
images are vividly coloured under a white-light microscope while carrying no "colour" in the
everyday sense. Modelling it as an interference term rather than as an arbitrary per-material RGB
triple is what makes the channels *informative*: two materials with the same luminance can differ
strongly in hue, which is exactly the signal the localizer can exploit.

Two smaller effects follow from the same optics and are modelled because they are free:

* the PSF width scales with wavelength, so the blue channel is genuinely sharper than the red;
* lateral chromatic aberration scales the channels slightly differently about the optical axis.

Both are real, both are per-channel, and both mean the three channels are not redundant.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Plate scale for the optical modality. Chosen from the diffraction limit rather than for
# convenience: at 373 nm resolution a 50 nm pixel is comfortably Nyquist-sampled for the reference,
# and the 10:1 relationship the spec fixes then puts the search image at 500 nm/px.
PIXEL_SIZE_OPTICAL_NM = 50.0

# Sensor channel centre wavelengths, nm. Ordinary Bayer-filter centres.
CHANNEL_WAVELENGTHS_NM = (610.0, 540.0, 465.0)          # R, G, B


@dataclass
class OpticalParams:
    """Everything about the microscope, as opposed to about the wafer."""

    pixel_size_nm: float = PIXEL_SIZE_OPTICAL_NM
    numerical_aperture: float = 0.90
    # Optical thickness of the film over each material, in nm. The interference term is what turns
    # a difference in material into a difference in HUE rather than only in brightness.
    film_thickness_nm: tuple[float, float, float, float] = (0.0, 120.0, 200.0, 310.0)
    refractive_index: float = 1.46                       # oxide-like overlayer
    # Lateral chromatic aberration: fractional magnification difference across the visible band,
    # applied about the image centre. A tenth of a percent is a realistic objective.
    chromatic_aberration: float = 0.0010
    illumination_uniformity: float = 0.92                # bright-field falloff at the field edge
    exposure: float = 1.0


def airy_sigma_px(wavelength_nm: float, numerical_aperture: float,
                  pixel_size_nm: float) -> float:
    """Gaussian sigma approximating the Airy disc, in pixels.

    The Airy pattern's central lobe is well approximated for imaging purposes by a Gaussian with
    ``sigma ~ 0.21 * lambda / NA`` (the usual fit to the FWHM of the diffraction-limited PSF). Using
    the Rayleigh radius directly as a sigma would over-blur by roughly 3x, which would wipe out the
    mat structure this modality depends on - so the constant matters and is not a fudge factor.
    """
    return float(0.21 * wavelength_nm / max(numerical_aperture, 1e-6) / max(pixel_size_nm, 1e-9))


def rayleigh_resolution_nm(wavelength_nm: float, numerical_aperture: float) -> float:
    """``0.61 lambda / NA`` - the number that decides what is visible at all."""
    return float(0.61 * wavelength_nm / max(numerical_aperture, 1e-6))


def film_reflectance(thickness_nm: float, wavelength_nm: float, index: float) -> float:
    """Two-beam thin-film interference, normalised to [0, 1].

    Reflections from the top and bottom of a transparent film of optical thickness ``n*d`` interfere
    with a phase difference of ``4*pi*n*d/lambda``. This is the whole reason a patterned wafer looks
    coloured, and it is why the same material shifts hue as the stack thickness changes across a
    die.
    """
    if thickness_nm <= 0.0:
        return 0.35                                       # bare substrate: grey, no interference
    phase = 4.0 * np.pi * index * thickness_nm / max(wavelength_nm, 1e-9)
    return float(0.25 + 0.55 * (0.5 * (1.0 - np.cos(phase))))


def material_channel_response(labels: np.ndarray, params: OpticalParams) -> np.ndarray:
    """Map a label image to an HxWx3 reflectance field via the film stack.

    ``labels`` holds a small integer per pixel identifying the material. Reflectance is looked up
    per (material, channel) rather than per material, which is the entire point: two materials can
    share a luminance and still separate cleanly in one channel.
    """
    height, width = labels.shape
    out = np.zeros((height, width, 3), dtype=np.float32)
    n_materials = len(params.film_thickness_nm)
    for material in range(n_materials):
        mask = labels == material
        if not mask.any():
            continue
        for channel, wavelength in enumerate(CHANNEL_WAVELENGTHS_NM):
            out[..., channel][mask] = film_reflectance(
                params.film_thickness_nm[material], wavelength, params.refractive_index
            )
    return out


def quantise_to_materials(canvas: np.ndarray, n_materials: int = 4) -> np.ndarray:
    """Recover material labels from the layout's grey levels.

    The layout renderer paints one grey level per material (background, word line, bit line,
    contact), so the distinct levels ARE the materials. Quantising by rank rather than by fixed
    thresholds keeps this working if a preset changes its palette.
    """
    values = np.unique(canvas)
    if values.size <= n_materials:
        lookup = {v: i for i, v in enumerate(values)}
        out = np.zeros(canvas.shape, dtype=np.uint8)
        for value, index in lookup.items():
            out[canvas == value] = index
        return out
    # More levels than materials (anti-aliased edges): bucket by intensity rank.
    edges = np.quantile(values, np.linspace(0, 1, n_materials + 1)[1:-1])
    return np.digitize(canvas, edges).astype(np.uint8)


def apply_chromatic_aberration(rgb: np.ndarray, strength: float) -> np.ndarray:
    """Scale each channel slightly differently about the image centre.

    Blue focuses shorter than red through a real objective, so the channels are not registered to
    each other. Modelling it means a localizer that simply averages the channels loses a little
    sharpness - which is the honest cost of ignoring the physics.
    """
    if strength == 0.0:
        return rgb
    height, width = rgb.shape[:2]
    centre = ((width - 1) / 2.0, (height - 1) / 2.0)
    out = np.empty_like(rgb)
    # Red long, blue short: index 0 magnified slightly, index 2 slightly reduced.
    for channel, factor in enumerate((1.0 + strength, 1.0, 1.0 - strength)):
        matrix = cv2.getRotationMatrix2D(centre, 0.0, factor)
        out[..., channel] = cv2.warpAffine(rgb[..., channel], matrix, (width, height),
                                           flags=cv2.INTER_LINEAR,
                                           borderMode=cv2.BORDER_REFLECT)
    return out


def diffraction_blur(rgb: np.ndarray, params: OpticalParams) -> np.ndarray:
    """Per-channel diffraction PSF. Blue is genuinely sharper than red."""
    out = np.empty_like(rgb)
    for channel, wavelength in enumerate(CHANNEL_WAVELENGTHS_NM):
        sigma = airy_sigma_px(wavelength, params.numerical_aperture, params.pixel_size_nm)
        out[..., channel] = (rgb[..., channel] if sigma < 0.3 else
                             cv2.GaussianBlur(rgb[..., channel], (0, 0), sigmaX=sigma,
                                              sigmaY=sigma, borderType=cv2.BORDER_REFLECT))
    return out


def illumination(shape: tuple[int, int], uniformity: float) -> np.ndarray:
    """Bright-field Koehler illumination is flat in the middle and falls off at the field stop."""
    height, width = shape
    ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    radius = np.sqrt(xs * xs + ys * ys) / np.sqrt(2.0)
    return (1.0 - (1.0 - uniformity) * radius ** 2).astype(np.float32)


def render_optical(canvas: np.ndarray, params: OpticalParams) -> np.ndarray:
    """Layout -> HxWx3 float image, before any detector noise.

    Order matters here exactly as it does in the SEM chain: reflectance is a property of the wafer,
    diffraction is a property of the objective, and both precede anything the sensor does.
    """
    labels = quantise_to_materials(canvas, len(params.film_thickness_nm))
    rgb = material_channel_response(labels, params)
    rgb = apply_chromatic_aberration(rgb, params.chromatic_aberration)
    rgb = diffraction_blur(rgb, params)
    rgb *= illumination(rgb.shape[:2], params.illumination_uniformity)[..., None]
    return np.clip(rgb * 255.0 * params.exposure, 0.0, 255.0)


def optical_detector(rgb: np.ndarray, dose: float, read_sigma: float,
                     rng: np.random.Generator) -> np.ndarray:
    """Photon shot noise then read noise, per channel, independent across channels.

    A colour sensor's three channels are separate photodiodes, so their noise is independent - which
    is the reason a colour-aware matcher can average noise down across channels while a luminance
    conversion throws two thirds of that away.
    """
    out = np.empty_like(rgb)
    for channel in range(rgb.shape[2]):
        scaled = np.clip(rgb[..., channel], 0.0, None) / 255.0 * dose
        noisy = rng.poisson(scaled).astype(np.float32) / max(dose, 1e-9) * 255.0
        out[..., channel] = noisy + rng.normal(0.0, read_sigma, size=noisy.shape)
    return np.clip(out, 0, 255).astype(np.uint8)
