"""Re-score each candidate at its OWN best pose, instead of at one pose shared by all of them.

The diagnosis this came from
----------------------------
On a clean information argument, ZNCC should already separate the true location from its lattice
impostors comfortably. The measured margin between them is about 0.016 (docs/FINDINGS.md), and for
a 100x100 template the sampling noise on a correlation of ~0.9 is roughly 0.002 - a signal-to-noise
ratio near 8, which would imply almost no mis-locks. We measure 27-33%.

So the noise that actually decides the ranking is **not photon noise**. It is model mismatch: the
residual difference between the template we synthesise and the patch the microscope actually
produced - leftover pose error, the raster drift's local gradient, PSF and apodisation differences.
The maximum-likelihood re-ranker found the same thing from the other direction: weighting by photon
variance sharpened a term that was not the limiting one (ADR-0018).

If mismatch is what dominates, then the fix is not a cleverer score - it is **less mismatch**. The
global pose is a compromise fitted across the whole search image, but drift accumulates over the
scan and distortion varies with field position, so the locally-best pose differs from candidate to
candidate. Scoring every candidate at one shared pose therefore compares them under a handicap that
is unequal and, worse, arbitrary.

Why this generalises when three re-rankers did not
--------------------------------------------------
This is re-**scoring**, not re-**ranking**. It introduces no new criterion and no blend weight: the
comparison is still ZNCC, just measured at each candidate's own optimum instead of at a compromise.
That keeps it on the safe side of the rule the earlier failures established (ADR-0012) - a stage
that only removes a handicap cannot invent a preference for the wrong answer.

Measured, mis-lock rate, top-10 candidates:

===============  ========  ========
split            argmax    refit
===============  ========  ========
dev (tuning)      20.0%     17.5%
bench             26.7%     23.3%
holdout FinFET    33.3%     30.0%
===============  ========  ========

Two variants were tried and both failed badly; they are recorded in docs/FINDINGS.md rather than
deleted. Ranking by the *gain* in score when the pose is freed reaches 80-92% mis-lock - impostors
gain more, because they have more mismatch available to absorb. And running the candidate-consensus
residual on the refitted patches reaches 40-53%, because refitting re-registers each patch
individually and the consensus average then compares patches that are no longer aligned to a common
frame.
"""

from __future__ import annotations

import cv2
import numpy as np


def refit_candidates(search: np.ndarray, reference: np.ndarray, candidates: list,
                     build_template, correlation_surface, config) -> list:
    """Return the candidates re-scored at their own locally-optimal pose.

    Positions are updated to the refitted peak as well, since a candidate that scores best at a
    slightly different pose also sits at a slightly different place.

    ``build_template`` and ``correlation_surface`` are passed in rather than imported to keep this
    module free of a circular import back into ``match``.
    """
    if len(candidates) < 2:
        return candidates

    span = config.refit_scale_span
    rot_span = config.refit_rotation_span
    steps = max(config.refit_steps, 1)
    margin = max(config.refit_margin_px, 1)

    # The template depends only on (scale, rotation) - NOT on which candidate we are scoring. The
    # obvious loop nesting (candidate outer, pose inner) therefore rebuilds the same few templates
    # once per candidate, and template construction - box-integrating a 1000x1000 reference and
    # warping it - is by far the most expensive step here. Building each template once and sweeping
    # the candidates inside it does identical work for 1/N the cost. Measured: 2250 ms -> 373 ms
    # per pair with no change to any result.
    # Candidates arrive from several different poses in the bracket, so each needs a grid centred
    # on its OWN pose - centring one shared grid on the top candidate silently erased the whole
    # effect when it was tried. But candidates that came from the same pose share a grid exactly,
    # and template construction (box-integrating a 1000x1000 reference, then warping) dominates the
    # cost here. So group by pose and build each template once per group rather than once per
    # candidate. Identical results, measured 2250 ms -> ~370 ms per pair.
    groups: dict[tuple[float, float], list[int]] = {}
    for i, cand in enumerate(candidates):
        groups.setdefault((round(cand.scale, 6), round(cand.rotation_deg, 6)), []).append(i)

    best = [{"score": c.score, "xy": (c.x, c.y), "pose": (c.scale, c.rotation_deg)}
            for c in candidates]

    for (pose_scale, pose_rotation), members in groups.items():
        scales = ([pose_scale] if steps == 1 else
                  np.linspace(pose_scale * (1 - span), pose_scale * (1 + span), steps))
        rotations = ([pose_rotation] if steps == 1 else
                     np.linspace(pose_rotation - rot_span, pose_rotation + rot_span, steps))

        for scale in scales:
            for rotation in rotations:
                template = build_template(reference, float(scale), float(rotation))
                th, tw = template.shape
                if th + 2 * margin >= search.shape[0] or tw + 2 * margin >= search.shape[1]:
                    continue

                for i in members:
                    cand = candidates[i]
                    # A window around the candidate: wide enough that the refitted peak can move a
                    # little, tight enough that a different lattice repeat cannot enter it.
                    y0 = int(round(cand.y - th / 2.0))
                    x0 = int(round(cand.x - tw / 2.0))
                    y0 = max(margin, min(y0, search.shape[0] - th - margin))
                    x0 = max(margin, min(x0, search.shape[1] - tw - margin))
                    window = search[y0 - margin:y0 + th + margin, x0 - margin:x0 + tw + margin]
                    if window.shape[0] <= th or window.shape[1] <= tw:
                        continue

                    _, score, _, loc = cv2.minMaxLoc(correlation_surface(window, template))
                    if score > best[i]["score"]:
                        best[i] = {
                            "score": float(score),
                            "xy": (x0 - margin + loc[0] + tw / 2.0,
                                   y0 - margin + loc[1] + th / 2.0),
                            "pose": (float(scale), float(rotation)),
                        }

    for cand, fit in zip(candidates, best):
        cand.extra["score_before_refit"] = cand.score
        cand.score = fit["score"]
        cand.x, cand.y = fit["xy"]
        cand.scale, cand.rotation_deg = fit["pose"]

    candidates.sort(key=lambda c: -c.score)
    return candidates
