"""Extra candidate PROPOSALS from representations that are bad at ranking.

The failure decomposition after ADR-0034 is 3 `absent`, 0 `screened`, 5 `outscored`. The `absent`
bucket is the one nothing else can reach: the true site never enters the candidate set, so no
selection rule of any kind applies to it, and it is the only bucket that has not moved through any
change made in this project.

WHAT THE FORENSICS FOUND (FINDINGS 42). Scoring several representations at the generator's exact
recorded pose - so none is ever blamed for a pose error - and taking the truth's rank among the top
30 suppressed peaks:

    absent failure   intensity   edge   variance   residual
    bench 4            ABSENT   ABSENT     6        ABSENT
    bench 17              13       1      12        ABSENT
    finfet 17          ABSENT   ABSENT   ABSENT       0

All three are visible, and **no single representation sees more than two of them**. That is what
makes a union worth building rather than a replacement: intensity stays exactly as it is, and the
others only ADD locations.

THE DISTINCTION THAT MAKES THIS DIFFERENT FROM PADM. Section 8's PADM removed periodic frequencies
with a Fourier mask and used the result as a *ranking* score with two tuned constants; it gained on
the split it was tuned on and lost on both held-out splits. Nothing here ranks. These
representations propose locations and then **the existing ZNCC and the existing refit decide**, on
the original intensity image, exactly as before. A representation can be useless at ranking and
still be useful at proposing; only the first was ever tested.

Which is also why this cannot quietly become a re-ranker: proposals carry no score into the
comparison. They are re-scored by the shipped criterion at the shipped geometry, or they are not
candidates at all.
"""

from __future__ import annotations

import cv2
import numpy as np

# Bounds on a believable lattice period in search pixels. Below the lag search a "period" is noise;
# above ~60 px it reaches out of a mat. Both are geometry, not tuning.
MIN_PERIOD_PX = 4.0
MAX_PERIOD_PX = 60.0


def local_variance(image: np.ndarray, ksize: int = 5) -> np.ndarray:
    """Local standard deviation: texture energy, independent of absolute grey level.

    Recovers bench 4 and bench 17 in the forensics, which plain intensity ranks 13th and not at all.
    """
    work = image.astype(np.float32)
    mean = cv2.blur(work, (ksize, ksize))
    mean_sq = cv2.blur(work * work, (ksize, ksize))
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))


def dominant_period(image: np.ndarray, axis: int) -> float:
    """The dominant spatial period along one axis, from the mean power spectrum."""
    work = image.astype(np.float32)
    work = work - work.mean(axis=axis, keepdims=True)
    spectrum = np.abs(np.fft.rfft(work, axis=axis)) ** 2
    power = spectrum.mean(axis=1 - axis)
    n = work.shape[axis]
    lo = max(int(np.ceil(n / MAX_PERIOD_PX)), 2)
    hi = min(int(np.floor(n / MIN_PERIOD_PX)), power.size - 1)
    if hi <= lo:
        return 0.0
    peak = int(np.argmax(power[lo:hi + 1])) + lo
    return float(n / peak) if peak else 0.0


def lattice_residual(image: np.ndarray) -> np.ndarray:
    """The image minus its own lattice-periodic prediction, built in the spatial domain.

    The prediction averages the image shifted by +-1 and +-2 lattice periods along each axis.
    Whatever repeats survives that average; whatever is unique to a site does not. The zero shift is
    excluded deliberately - including it would put a site's own content into its own prediction and
    cancel exactly the thing being looked for.

    Recovers finfet 17 at rank 0, which no other representation sees at all.
    """
    work = image.astype(np.float32)
    period_y, period_x = dominant_period(work, 0), dominant_period(work, 1)
    if not (MIN_PERIOD_PX <= period_y <= MAX_PERIOD_PX):
        return work - cv2.blur(work, (9, 9))
    if not (MIN_PERIOD_PX <= period_x <= MAX_PERIOD_PX):
        return work - cv2.blur(work, (9, 9))

    height, width = work.shape
    accum = np.zeros_like(work)
    count = 0
    for ky in (-2, -1, 0, 1, 2):
        for kx in (-2, -1, 0, 1, 2):
            if ky == 0 and kx == 0:
                continue
            matrix = np.array([[1.0, 0.0, kx * period_x], [0.0, 1.0, ky * period_y]],
                              dtype=np.float32)
            accum += cv2.warpAffine(work, matrix, (width, height), flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REFLECT)
            count += 1
    return work - accum / max(count, 1)


def edge_magnitude(image: np.ndarray) -> np.ndarray:
    """Scharr gradient magnitude: structure without absolute grey level.

    The only channel that finds bench 17 at rank 1, where variance ranks it 12th and the residual
    does not see it at all.
    """
    work = image.astype(np.float32)
    gx = cv2.Scharr(work, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(work, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


CHANNELS = {
    "variance": local_variance,
    "residual": lattice_residual,
    "edge": edge_magnitude,
}


def propose(
    reference: np.ndarray, search: np.ndarray, poses, config,
    build_template, correlation_surface, extract_peaks, level: int = 1,
) -> list:
    """Extra candidates from the auxiliary channels, at the same poses as the main pass.

    Returns candidates whose ``extra["proposal"]`` records which channel found them. Their scores
    come from the auxiliary surface and are **not comparable** with the main pass's ZNCC - callers
    must re-score them, which is what the refit does anyway.

    WHY THIS RUNS AT REDUCED RESOLUTION. Provenance measured the candidate pool growing only 60 to
    63 while runtime grew to 1.46x, so the cost is the residual's own COMPUTATION - two dozen warps
    of a 1000x1000 image, plus a correlation surface per pose - and not the extra candidates. And
    the proposal stage does not need precision: it has to say "look near here", after which the
    existing refit and sub-pixel stages find the exact location on the intensity image. Halving the
    resolution quarters both the warps and the correlations while leaving the proposal well inside
    the merge radius.

    Downsampling BOTH images by the same factor leaves their scale ratio unchanged, so the pose
    values still describe the pair correctly and only the recovered coordinates need scaling back.
    """
    wanted = [name.strip() for name in getattr(config, "proposal_channels", "").split(",")
              if name.strip() in CHANNELS]
    if not wanted:
        return []

    out: list = []
    per_channel = max(getattr(config, "proposal_top_k", 5), 1)
    shrink = max(int(getattr(config, "proposal_level", 1)), 1)
    total = level * shrink

    ref_small, search_small = reference, search
    if shrink > 1:
        ref_small = cv2.resize(reference, (reference.shape[1] // shrink,
                                           reference.shape[0] // shrink),
                               interpolation=cv2.INTER_AREA)
        search_small = cv2.resize(search, (search.shape[1] // shrink,
                                           search.shape[0] // shrink),
                                  interpolation=cv2.INTER_AREA)

    for name in wanted:
        transform = CHANNELS[name]
        ref_rep = transform(ref_small)
        search_rep = transform(search_small)
        work = search_rep
        if level > 1:
            work = cv2.resize(search_rep, (search_rep.shape[1] // level,
                                           search_rep.shape[0] // level),
                              interpolation=cv2.INTER_AREA)
        for scale, rotation in poses:
            template = build_template(ref_rep, scale * level, rotation)
            if template.shape[0] >= work.shape[0] or template.shape[1] >= work.shape[1]:
                continue
            found = extract_peaks(correlation_surface(work, template), template.shape,
                                  per_channel, config.nms_radius_px, scale, rotation)
            for cand in found:
                cand.x *= total
                cand.y *= total
                cand.extra["proposal"] = name
            out.extend(found)
    return out


def merge(main: list, extra: list, radius_px: float) -> list:
    """Add proposals that are not already within ``radius_px`` of an existing candidate.

    Deduplication is against the MAIN list only, and by position only. A proposal that lands on a
    site intensity already found adds nothing but cost; one that lands somewhere new is the entire
    point of the channel.
    """
    if not extra:
        return main
    kept = list(main)
    radius_sq = radius_px * radius_px
    for cand in extra:
        if all((cand.x - other.x) ** 2 + (cand.y - other.y) ** 2 > radius_sq for other in kept):
            kept.append(cand)
    return kept
