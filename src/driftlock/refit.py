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

    pose_penalty = getattr(config, "refit_pose_penalty", 0.0)
    span = config.refit_scale_span
    rot_span = config.refit_rotation_span
    steps = max(config.refit_steps, 1)
    margin = max(config.refit_margin_px, 1)
    passes = max(getattr(config, "refit_passes", 1), 1)
    shrink = getattr(config, "refit_pass_shrink", 0.4)

    # Coarse-to-fine instead of one dense grid. A wide span genuinely helps - measured, held-out
    # mis-lock 22.0% -> 20.0% - but only when the grid over it is fine, because a wide span sampled
    # coarsely steps straight over the optimum (span 0.03 with 3 steps measured 26.0%, WORSE than
    # not widening at all). Covering that span densely in one pass costs 25 templates per pose group
    # and 876 ms per pair.
    #
    # Two passes reach the same places for far fewer templates: sweep the wide span coarsely, then
    # re-centre on the winner and sweep a shrunken span. Same coverage, ~1/3 the correlations.

    # Screen before spending the dense budget. Measured: the dense grid's cost is correlation
    # count, not template construction - candidates arrive top_k-per-POSE, so a 5x5 grid over 60
    # candidates is 1500 correlations per pair (334 of the 540 ms). A cheap narrow refit ranks
    # them first, and only the survivors get the expensive grid. Same criterion throughout.
    screen_steps = getattr(config, "refit_screen_steps", 0)
    screen_n = getattr(config, "refit_screen_top_n", 10)
    deferred: list = []
    if screen_steps > 0 and len(candidates) > 1:
        candidates = _refit_once(search, reference, candidates, build_template,
                                 correlation_surface,
                                 getattr(config, "refit_screen_scale_span", 0.006),
                                 getattr(config, "refit_screen_rotation_span", 0.30),
                                 screen_steps, margin, pose_penalty)
        # Truncation is deliberately SEPARATE from running the screen, so the two things the screen
        # does - pruning the field, and re-scoring it before pruning - can be measured apart.
        # Setting screen_top_n above the candidate count runs the screen with no pruning at all,
        # which is the control that separates them. Measured (FINDINGS 23f), held-out mis-lock:
        #
        #   no screen                      20.0%     re-scoring alone buys NOTHING (C == A), and
        #   screen + prune (shipped)       18.0%     pruning alone is WORSE THAN NOTHING (D).
        #   screen, nothing pruned  (C)    20.0%
        #   prune on unrefit scores (D)    24.0%
        #
        # So this is not "better initialisation for the wide grid", which was our first published
        # explanation and is refuted by C. A wide pose search helps the true candidate and helps
        # impostors MORE - the same asymmetry that sank refit-gain ranking at 80-92% (FINDINGS 15d).
        # Handing +/-3% and +/-1.5 deg to 60 candidates gives 59 impostors 25 chances each to find a
        # flattering pose. The screen BOUNDS how much geometric freedom the field collectively gets,
        # and the narrow refit is what makes a top-10 cut trustworthy enough to take beforehand.
        # Spend the screen's slots on DISTINCT sites.
        #
        # extract_peaks applies non-maximum suppression inside each pose's correlation surface, but
        # candidates from every pose in the bracket are then merged with no suppression ACROSS
        # poses. The same physical site therefore enters the refit once per pose that found it.
        # Measured on bench: 60 candidates arrive at 33.8 distinct positions, and the top 10 after
        # the screen hold only 6.2 - so **3.8 of the 10 expensive slots go to duplicates**.
        #
        # That is not merely wasted compute. The failure analysis (FINDINGS 30) found the true
        # candidate is never the runner-up and sits at rank 3+ or outside the pool entirely; part of
        # the reason is that the ranks above it are occupied by COPIES of one impostor rather than
        # by distinct rivals. Deduplicating here converts wasted slots into hypotheses.
        #
        # Done AFTER the screen, not before: the screen re-scores at a corrected pose, so positions
        # are more trustworthy here, and keeping the best-scoring copy is then meaningful. The
        # tolerance stays well inside one lattice pitch (6.4 px word / 9.6 px bit at 10:1) so
        # genuinely adjacent repeats are never merged.
        dedup_px = getattr(config, "refit_screen_dedup_px", 0.0)
        if dedup_px > 0.0:
            kept: list = []
            for cand in candidates:                      # already sorted by score, best first
                if all((cand.x - k.x) ** 2 + (cand.y - k.y) ** 2 > dedup_px * dedup_px
                       for k in kept):
                    kept.append(cand)
                else:
                    deferred.append(cand)
            candidates = kept

        if len(candidates) > screen_n:
            # The losers are kept, not dropped: they still carry their screened score, and
            # downstream stages (ambiguity index, confidence radius) read the whole candidate set.
            candidates, deferred = candidates[:screen_n], deferred + candidates[screen_n:]

    for pass_index in range(passes):
        scale_span = span * (shrink ** pass_index)
        rotation_span = rot_span * (shrink ** pass_index)
        candidates = _refit_once(search, reference, candidates, build_template,
                                 correlation_surface, scale_span, rotation_span, steps,
                                 margin, pose_penalty)

    # Interpolate the pose between grid samples, then evaluate there.
    #
    # Measured: a wide span helps (22.0% -> 20.0% held-out) but ONLY when sampled densely - the
    # same span with 3 steps instead of 5 gives 26.0%, worse than not widening at all. The optimum
    # therefore lies BETWEEN coarse samples, and a dense grid is an expensive way to find it: 25
    # templates per pose group, 876 ms per pair.
    #
    # The scores on the coarse grid already describe the local shape of the objective, so fit a
    # parabola per axis and evaluate once at its vertex. That is the same argument as sub-pixel
    # peak fitting, applied to pose instead of position: one extra evaluation instead of sixteen.
    # The interpolated pose is only adopted if it actually scores higher, so this cannot make a
    # candidate worse.
    if getattr(config, "refit_pose_interp", False):
        candidates = _interpolate_pose(search, reference, candidates, build_template,
                                       correlation_surface, margin)

    # Multi-basin refinement: sweep the wide span coarsely, keep the distinct local maxima, and
    # spend the fine budget inside each of them rather than only around the single best sample.
    basins = getattr(config, "refit_basins", 0)
    if basins > 1:
        candidates = _refit_multibasin(search, reference, candidates, build_template,
                                       correlation_surface, span, rot_span, steps, margin,
                                       basins, shrink)
    if deferred:
        candidates = sorted(candidates + deferred, key=lambda c: -c.score)
    return candidates


def _refit_multibasin(search: np.ndarray, reference: np.ndarray, candidates: list,
                      build_template, correlation_surface, span: float, rot_span: float,
                      steps: int, margin: int, max_basins: int, shrink: float) -> list:
    """Refine each candidate inside several distinct pose basins, then keep its best result."""
    for cand in candidates:
        probe = cand.extra.get("refit_grid")
        if probe is None:
            continue
        grid, scales_ax, rot_ax = probe
        peaks = _pose_basins(grid, max_basins)
        if len(peaks) < 2:
            continue                      # a single basin: the plain refit already found it

        fine_scale_span = span * shrink
        fine_rot_span = rot_span * shrink
        for si, ri in peaks:
            centre_scale = float(scales_ax[si])
            centre_rot = float(rot_ax[ri])
            fine_scales = np.linspace(centre_scale * (1 - fine_scale_span),
                                      centre_scale * (1 + fine_scale_span), steps)
            fine_rots = np.linspace(centre_rot - fine_rot_span,
                                    centre_rot + fine_rot_span, steps)
            for scale in fine_scales:
                for rotation in fine_rots:
                    template = build_template(reference, float(scale), float(rotation))
                    th, tw = template.shape
                    if th + 2 * margin >= search.shape[0] or tw + 2 * margin >= search.shape[1]:
                        continue
                    y0 = max(margin, min(int(round(cand.y - th / 2.0)),
                                         search.shape[0] - th - margin))
                    x0 = max(margin, min(int(round(cand.x - tw / 2.0)),
                                         search.shape[1] - tw - margin))
                    window = search[y0 - margin:y0 + th + margin, x0 - margin:x0 + tw + margin]
                    if window.shape[0] <= th or window.shape[1] <= tw:
                        continue
                    _, score, _, loc = cv2.minMaxLoc(correlation_surface(window, template))
                    if score > cand.score:
                        cand.score = float(score)
                        cand.x = x0 - margin + loc[0] + tw / 2.0
                        cand.y = y0 - margin + loc[1] + th / 2.0
                        cand.scale, cand.rotation_deg = float(scale), float(rotation)
    candidates.sort(key=lambda c: -c.score)
    return candidates


def _pose_basins(grid: np.ndarray, max_basins: int) -> list[tuple[int, int]]:
    """Distinct local maxima of the pose-score surface, best first.

    Both earlier failures share one cause: they assume the pose surface has a single basin.
    A coarse wide grid takes its highest SAMPLE, which can sit in the wrong basin; and fitting a
    parabola across widely separated samples interpolates BETWEEN basins rather than within one
    (measured 27.0% held-out, worse than not widening at all).

    Retaining several basins removes that assumption. Note this is not "keep the top N samples" -
    those usually all belong to the same peak. A sample qualifies only if it beats its four
    neighbours, which is non-maximum suppression in (scale, rotation) space rather than in image
    space.
    """
    rows, cols = grid.shape
    peaks = []
    for si in range(rows):
        for ri in range(cols):
            value = grid[si, ri]
            if value <= -1.5:
                continue
            neighbours = []
            if si > 0:
                neighbours.append(grid[si - 1, ri])
            if si < rows - 1:
                neighbours.append(grid[si + 1, ri])
            if ri > 0:
                neighbours.append(grid[si, ri - 1])
            if ri < cols - 1:
                neighbours.append(grid[si, ri + 1])
            if all(value >= n for n in neighbours):
                peaks.append((value, si, ri))
    peaks.sort(reverse=True)
    return [(si, ri) for _, si, ri in peaks[:max_basins]]


def _parabola_vertex(lo: float, mid: float, hi: float) -> float:
    """Offset of the parabola's peak from the centre sample, in grid steps, clipped to +/-1."""
    denom = lo - 2.0 * mid + hi
    if abs(denom) < 1e-12:
        return 0.0
    return float(np.clip(0.5 * (lo - hi) / denom, -1.0, 1.0))


def _interpolate_pose(search: np.ndarray, reference: np.ndarray, candidates: list,
                      build_template, correlation_surface, margin: int) -> list:
    """Refine each candidate's pose to a continuous optimum between its grid samples."""
    for cand in candidates:
        probe = cand.extra.get("refit_probe")
        if not probe:
            continue
        (s_lo, s_mid, s_hi), (r_lo, r_mid, r_hi), (ds, dr) = probe
        offset_s = _parabola_vertex(s_lo, s_mid, s_hi)
        offset_r = _parabola_vertex(r_lo, r_mid, r_hi)
        if abs(offset_s) < 1e-6 and abs(offset_r) < 1e-6:
            continue

        scale = cand.scale + offset_s * ds
        rotation = cand.rotation_deg + offset_r * dr
        template = build_template(reference, float(scale), float(rotation))
        th, tw = template.shape
        if th + 2 * margin >= search.shape[0] or tw + 2 * margin >= search.shape[1]:
            continue
        y0 = max(margin, min(int(round(cand.y - th / 2.0)), search.shape[0] - th - margin))
        x0 = max(margin, min(int(round(cand.x - tw / 2.0)), search.shape[1] - tw - margin))
        window = search[y0 - margin:y0 + th + margin, x0 - margin:x0 + tw + margin]
        if window.shape[0] <= th or window.shape[1] <= tw:
            continue

        _, score, _, loc = cv2.minMaxLoc(correlation_surface(window, template))
        if score > cand.score:            # never adopt a worse pose
            cand.score = float(score)
            cand.x = x0 - margin + loc[0] + tw / 2.0
            cand.y = y0 - margin + loc[1] + th / 2.0
            cand.scale, cand.rotation_deg = float(scale), float(rotation)
    candidates.sort(key=lambda c: -c.score)
    return candidates


def _refit_once(search: np.ndarray, reference: np.ndarray, candidates: list,
                build_template, correlation_surface, span: float, rot_span: float,
                steps: int, margin: int, pose_penalty: float) -> list:
    """One sweep of the refit, centred on each candidate's current pose."""
    # Imported here, not at module level, for the same reason build_template is injected rather
    # than imported: match imports this module, so a top-level import would close the cycle.
    from src.driftlock.match import integrate_reference

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

    best = [{"score": c.score, "penalty": 0.0, "xy": (c.x, c.y),
             "pose": (c.scale, c.rotation_deg)} for c in candidates]
    # Score grid per candidate, so the winning pose can later be interpolated between samples
    # rather than snapped to whichever sample happened to be nearest.
    grids: dict[int, np.ndarray] = {}
    axes: dict[int, tuple] = {}

    for (pose_scale, pose_rotation), members in groups.items():
        scales = ([pose_scale] if steps == 1 else
                  np.linspace(pose_scale * (1 - span), pose_scale * (1 + span), steps))
        rotations = ([pose_rotation] if steps == 1 else
                     np.linspace(pose_rotation - rot_span, pose_rotation + rot_span, steps))

        for i in members:
            grids[i] = np.full((len(scales), len(rotations)), -2.0)
            axes[i] = (np.asarray(scales), np.asarray(rotations))

        for si, scale in enumerate(scales):
            # build_template does two things: box-integrate the full 1000x1000 reference over one
            # detector footprint (a separable filter, and by far the dominant cost) and affine-warp
            # it to ~100x100. Only the FIRST depends on rotation - it does not. Integrating once per
            # scale instead of once per (scale, rotation) turns a 5x5 grid's 25 integrations into 5.
            # The value passed is exactly what build_template would have computed itself, so this is
            # a pure hoist: results are bit-identical.
            integrated = integrate_reference(reference, float(scale))
            for ri, rotation in enumerate(rotations):
                template = build_template(reference, float(scale), float(rotation),
                                          integrated=integrated)
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
                    grids[i][si, ri] = score

                    # Charge a candidate for how far it had to move to reach that score.
                    #
                    # Ranking candidates by their score GAIN when the pose is freed measured at
                    # 80-92% mis-lock - catastrophically backwards - because an impostor starts
                    # with MORE mismatch and so has more to absorb. The same asymmetry leaks into
                    # the plain maximum: a wrong candidate can buy a high score with a large pose
                    # excursion that the true one never needs. Penalising the excursion keeps the
                    # freedom that made the refit work while removing the loophole.
                    #
                    # Expressed in units of the search span, so it is scale-free.
                    penalty = 0.0
                    if pose_penalty > 0.0:
                        ds = (scale - pose_scale) / max(pose_scale * span, 1e-9)
                        dr = (rotation - pose_rotation) / max(rot_span, 1e-9)
                        penalty = pose_penalty * (ds * ds + dr * dr)

                    if score - penalty > best[i]["score"] - best[i]["penalty"]:
                        best[i] = {
                            "score": float(score),
                            "penalty": float(penalty),
                            "xy": (x0 - margin + loc[0] + tw / 2.0,
                                   y0 - margin + loc[1] + th / 2.0),
                            "pose": (float(scale), float(rotation)),
                        }

    for i, (cand, fit) in enumerate(zip(candidates, best)):
        grid, ax = grids.get(i), axes.get(i)
        if grid is not None and grid.shape[0] >= 3 and grid.shape[1] >= 3:
            si, ri = np.unravel_index(int(np.argmax(grid)), grid.shape)
            if 0 < si < grid.shape[0] - 1 and 0 < ri < grid.shape[1] - 1:
                scales_ax, rot_ax = ax
                # Keep the whole grid too: multi-basin refinement needs every local maximum,
                # not just the neighbourhood of the single best sample.
                cand.extra["refit_grid"] = (grid, scales_ax, rot_ax)
                cand.extra["refit_probe"] = (
                    (grid[si - 1, ri], grid[si, ri], grid[si + 1, ri]),
                    (grid[si, ri - 1], grid[si, ri], grid[si, ri + 1]),
                    (float(scales_ax[1] - scales_ax[0]), float(rot_ax[1] - rot_ax[0])),
                )
        cand.extra["score_before_refit"] = cand.score
        cand.score = fit["score"]
        cand.x, cand.y = fit["xy"]
        cand.scale, cand.rotation_deg = fit["pose"]

    candidates.sort(key=lambda c: -c.score)
    return candidates
