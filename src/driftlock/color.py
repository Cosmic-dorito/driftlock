"""Choosing the colour channel, instead of assuming one.

The RGB optical modality gives three channels, and the usual reflex is to convert them to luminance
with the broadcast weights ``0.299 R + 0.587 G + 0.114 B``. Those weights encode the sensitivity of
the human eye. Nothing about a wafer's film stack knows or cares about that, and the weights are
fixed while the stack is not.

What actually produces the colour is thin-film interference: reflectance oscillates with
``4*pi*n*d/lambda``, so two materials can share a luminance and still separate cleanly in one
channel - and *which* channel depends on the thickness of the layer that happens to be on the wafer.
A fixed projection therefore throws away a variable amount of the available contrast, and
occasionally almost all of it.

So do not pick a channel. **Measure the one this pair actually needs.** The direction in RGB space
along which the reference's own pixels vary most is the direction that best separates its materials,
and it costs one 3x3 eigen-decomposition to find. The same direction is then applied to both images,
which matters: a projection chosen independently per image would put the two into different
photometric frames and break the correlation it was meant to help.

This is the same move the rest of the project makes everywhere else - measure the nuisance parameter
from the data rather than assume it - applied to colour instead of to pose.
"""

from __future__ import annotations

import cv2
import numpy as np

# Rec. 601 luminance, the baseline this is measured against. Written out rather than delegated to
# cv2 so the comparison is explicit about what the alternative actually is.
LUMA_RGB = np.array([0.299, 0.587, 0.114], dtype=np.float64)


def contrast_projection(reference_rgb: np.ndarray, sample_stride: int = 4) -> np.ndarray:
    """The unit RGB direction along which the reference's pixels vary most.

    Computed from the REFERENCE alone, because it is the high-dose acquisition: its colour
    statistics are the trustworthy ones, and using the search image would let its noise steer the
    projection. Sub-sampled on a stride because a 3x3 covariance does not need a million pixels.
    """
    if reference_rgb.ndim != 3 or reference_rgb.shape[2] != 3:
        raise ValueError("contrast_projection expects an HxWx3 image")
    pixels = reference_rgb[::sample_stride, ::sample_stride].reshape(-1, 3).astype(np.float64)
    pixels = pixels - pixels.mean(axis=0, keepdims=True)
    if pixels.shape[0] < 3:
        return LUMA_RGB / np.linalg.norm(LUMA_RGB)

    covariance = np.cov(pixels, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    direction = vectors[:, int(np.argmax(values))]

    # eigh's sign is arbitrary. Fix it so the projection stays positively correlated with
    # brightness: an inverted image is a perfectly good correlation target, but flipping polarity
    # between runs on the same data would make the pipeline non-deterministic in appearance and
    # would invert every debug figure.
    if float(direction @ LUMA_RGB) < 0:
        direction = -direction
    return direction / max(float(np.linalg.norm(direction)), 1e-12)


def project(image_rgb: np.ndarray, direction: np.ndarray) -> np.ndarray:
    """Collapse HxWx3 to HxW along ``direction``, rescaled to the usual 0-255 working range."""
    flat = image_rgb.astype(np.float32) @ direction.astype(np.float32)
    lo, hi = float(flat.min()), float(flat.max())
    if hi - lo < 1e-9:
        return np.zeros(flat.shape, dtype=np.float32)
    return (flat - lo) * (255.0 / (hi - lo))


def to_matcher_input(reference_rgb: np.ndarray, search_rgb: np.ndarray,
                     mode: str = "pca") -> tuple[np.ndarray, np.ndarray]:
    """Reduce a colour pair to the single channel the matcher consumes.

    ``mode="luma"`` is the baseline; ``mode="pca"`` measures the projection from the reference. Both
    return float32 in the same range, so the only difference between them is which direction in
    colour space was used - which is what makes the ablation between them meaningful.
    """
    if reference_rgb.ndim == 2:
        return reference_rgb.astype(np.float32), search_rgb.astype(np.float32)
    if mode == "luma":
        direction = LUMA_RGB / np.linalg.norm(LUMA_RGB)
    elif mode == "pca":
        direction = contrast_projection(reference_rgb)
    else:
        raise ValueError(f"unknown colour mode {mode!r}")
    return project(reference_rgb, direction), project(search_rgb, direction)


def load_rgb(path) -> np.ndarray:
    """Read an image as HxWx3 RGB, or HxW if it is genuinely single-channel.

    OpenCV reads BGR; the optical renderer and everything in this module work in RGB, so the swap
    happens here, once, for the same reason the x/y convention is converted in exactly one place.
    """
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"could not read image: {path}")
    if img.dtype == np.uint16:
        img = (img.astype(np.float32) / 257.0).astype(np.uint8)
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
