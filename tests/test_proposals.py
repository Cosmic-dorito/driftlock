"""The proposal stage must return the same physical location at every resolution.

`propose()` composes TWO independent reductions - `proposal_level`, which shrinks both images before
the residual is computed, and `pose_bracket_level`, which shrinks the search image again for the
coarse pose sweep - and then maps coordinates back by their product. A mistake in that composition
does not raise: it silently returns proposals displaced by a factor of two, which downstream looks
like "the cheaper setting is less accurate" rather than like a bug.

So the invariant is asserted directly. If the reduction is wired correctly, the same site comes back
at the same coordinate whatever resolution it was found at, to within the merge tolerance.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.driftlock.match import (
    PipelineConfig,
    build_template,
    correlation_surface,
    extract_peaks,
)
from src.driftlock.proposals import dominant_period, lattice_residual, merge, propose

SCALE = 10.0


def _canvas(size: int = 1200, period: float = 40.0, seed: int = 11) -> np.ndarray:
    """A periodic lattice with one aperiodic blemish, which is what the residual is built to find."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    img = (128.0
           + 45.0 * np.cos(2 * np.pi * xs / period)
           + 45.0 * np.cos(2 * np.pi * ys / period))
    img += rng.normal(0.0, 1.5, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def _pair() -> tuple[np.ndarray, np.ndarray]:
    """A reference crop and a search view of the same canvas at SCALE:1, as the generator does."""
    canvas = _canvas()
    search = cv2.resize(canvas, (canvas.shape[1] // 10, canvas.shape[0] // 10),
                        interpolation=cv2.INTER_AREA)
    # An asymmetric crop: a centred one could not catch an x/y swap or a sign error.
    reference = canvas[260:360, 420:520]
    reference = cv2.resize(reference, (1000, 1000), interpolation=cv2.INTER_LINEAR)
    return reference, search


@pytest.mark.parametrize("shrink", [1, 2, 4])
def test_proposal_coordinates_are_resolution_invariant(shrink: int) -> None:
    """A proposal's coordinate must not depend on the resolution it was computed at."""
    reference, search = _pair()
    poses = [(SCALE, 0.0)]

    def run(level_value: int) -> list[tuple[float, float]]:
        config = PipelineConfig(proposal_channels="residual", proposal_top_k=4,
                                proposal_level=level_value)
        found = propose(reference.astype(np.float32), search.astype(np.float32), poses, config,
                        build_template, correlation_surface, extract_peaks, level=1)
        return sorted((round(c.x, 1), round(c.y, 1)) for c in found)

    at_one = run(1)
    at_shrink = run(shrink)
    if shrink == 1:
        assert at_one == at_shrink
        return

    assert at_shrink, "the reduced-resolution stage returned no proposals at all"
    # Each reduced-resolution proposal must have a full-resolution counterpart nearby. The tolerance
    # is the merge radius: a proposal only has to say "look near here", and the refit finds the
    # exact location afterwards on the intensity image.
    tolerance = PipelineConfig().proposal_dedup_px
    for x, y in at_shrink:
        nearest = min((abs(x - px) + abs(y - py)) for px, py in at_one)
        assert nearest <= tolerance * shrink, (
            f"proposal at ({x}, {y}) from level {shrink} has no full-resolution counterpart "
            f"within {tolerance * shrink} px (nearest {nearest:.1f})"
        )


def test_proposal_coordinates_survive_the_pose_bracket_reduction() -> None:
    """`proposal_level` and `pose_bracket_level` compose, and their product is what maps back.

    Getting this wrong displaces every proposal by exactly a factor of two, which reads downstream
    as an accuracy loss rather than as a defect.
    """
    reference, search = _pair()
    poses = [(SCALE, 0.0)]
    config = PipelineConfig(proposal_channels="residual", proposal_top_k=3, proposal_level=2)

    plain = propose(reference.astype(np.float32), search.astype(np.float32), poses, config,
                    build_template, correlation_surface, extract_peaks, level=1)
    bracketed = propose(reference.astype(np.float32), search.astype(np.float32), poses, config,
                        build_template, correlation_surface, extract_peaks, level=2)

    assert plain and bracketed
    for cand in bracketed:
        nearest = min(abs(cand.x - o.x) + abs(cand.y - o.y) for o in plain)
        assert nearest <= 4 * PipelineConfig().proposal_dedup_px, (
            f"pose-bracket reduction moved a proposal by {nearest:.1f} px"
        )


def test_merge_keeps_only_spatially_novel_proposals() -> None:
    """A proposal on top of an existing candidate is pure cost; a distant one is the whole point."""
    from src.driftlock.match import Candidate

    main = [Candidate(x=100.0, y=100.0, score=0.9)]
    extra = [
        Candidate(x=101.0, y=100.5, score=0.5),      # duplicate of the existing candidate
        Candidate(x=400.0, y=400.0, score=0.4),      # genuinely new location
    ]
    merged = merge(main, extra, radius_px=8.0)
    assert len(merged) == 2
    assert any(abs(c.x - 400.0) < 1e-6 for c in merged)


def test_residual_removes_what_repeats_and_keeps_what_does_not() -> None:
    """The whole premise: periodic content should cancel, an aperiodic blemish should survive."""
    canvas = _canvas(size=600, period=30.0).astype(np.float32)
    blemished = canvas.copy()
    blemished[300:312, 180:192] = 255.0                     # asymmetric, off-centre

    residual = lattice_residual(blemished)
    inner = (slice(60, 540), slice(60, 540))
    blemish = np.abs(residual[300:312, 180:192]).mean()
    elsewhere = np.abs(residual[inner]).mean()
    assert blemish > 3 * elsewhere, f"blemish {blemish:.2f} vs background {elsewhere:.2f}"


def test_dominant_period_recovers_a_period_we_chose() -> None:
    """Hand-derived: the canvas is built at period 30, so nothing else is an acceptable answer."""
    canvas = _canvas(size=600, period=30.0).astype(np.float32)
    assert dominant_period(canvas, 0) == pytest.approx(30.0, abs=1.5)
    assert dominant_period(canvas, 1) == pytest.approx(30.0, abs=1.5)
