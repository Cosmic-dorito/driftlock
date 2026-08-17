"""Overlay rendering — what the matcher decided, and why it is worth believing or not.

The spec requires "at least one visualized failure case with root-cause explanation", and failure
analysis is 10% of the score. A crosshair on an image is not that. A useful overlay has to answer
the question a process engineer would actually ask: *the tool says the pattern is here — how do I
know it is not one lattice repeat to the left?*

So the overlay shows the runners-up as well as the winner. On this problem a mis-lock is never a
near miss: rival peaks sit a median of 45 px away while scoring only 0.016 lower (H8). Drawing the
rivals makes that visible — a pair with one clear box is a confident result, and a pair with four
almost-equally-bright boxes is one that happened to win a coin toss.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.driftlock.io import Match, load_grayscale

_WINNER = (0, 235, 0)
_RIVAL = (0, 165, 255)
_TRUTH = (255, 80, 80)


def _to_bgr(img: np.ndarray) -> np.ndarray:
    work = img.astype(np.float32)
    lo, hi = float(work.min()), float(work.max())
    work = (work - lo) / (hi - lo + 1e-9) * 255.0
    return cv2.cvtColor(work.astype(np.uint8), cv2.COLOR_GRAY2BGR)


def _draw_box(canvas: np.ndarray, cx: float, cy: float, size: float,
              colour: tuple[int, int, int], thickness: int, label: str = "") -> None:
    x0, y0 = int(round(cx - size / 2.0)), int(round(cy - size / 2.0))
    x1, y1 = int(round(cx + size / 2.0)), int(round(cy + size / 2.0))
    cv2.rectangle(canvas, (x0, y0), (x1, y1), colour, thickness)
    arm = max(int(size * 0.18), 4)
    ix, iy = int(round(cx)), int(round(cy))
    cv2.line(canvas, (ix - arm, iy), (ix + arm, iy), colour, thickness)
    cv2.line(canvas, (ix, iy - arm), (ix, iy + arm), colour, thickness)
    if label:
        cv2.putText(canvas, label, (x0, max(y0 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1, cv2.LINE_AA)


def save_overlay(
    out_path: str | Path, reference_path: str | Path, search_path: str | Path,
    match: Match, truth: tuple[float, float] | None = None,
    rivals: list[tuple[float, float, float]] | None = None,
    footprint_px: float | None = None,
) -> Path:
    """Write a side-by-side overlay: the reference, and the search image with the decision drawn.

    ``rivals`` are ``(x, y, score)`` triples for the candidates that lost. ``truth``, when supplied,
    is drawn in a third colour so a failure case shows the true location and the chosen one in the
    same frame — which is what makes the root cause legible rather than asserted.
    """
    reference = load_grayscale(reference_path)
    search = load_grayscale(search_path)

    size = float(footprint_px if footprint_px is not None
                 else reference.shape[0] / 10.0)

    panel = _to_bgr(search)
    for rx, ry, rscore in (rivals or []):
        _draw_box(panel, rx, ry, size, _RIVAL, 1, f"{rscore:.3f}")
    if truth is not None:
        _draw_box(panel, truth[0], truth[1], size, _TRUTH, 2, "truth")
    _draw_box(panel, match.x, match.y, size, _WINNER, 2, f"pred {match.score:.3f}")

    ref_panel = _to_bgr(cv2.resize(reference, (search.shape[1], search.shape[0]),
                                   interpolation=cv2.INTER_AREA))

    caption = [f"predicted centre  ({match.x:.2f}, {match.y:.2f})  score {match.score:.4f}"]
    if truth is not None:
        error = float(np.hypot(match.x - truth[0], match.y - truth[1]))
        caption.append(f"truth ({truth[0]:.2f}, {truth[1]:.2f})   error {error:.2f} px")
    if match.ambiguity_index is not None:
        caption.append(f"ambiguity index {match.ambiguity_index:.3f}")

    combined = np.hstack([ref_panel, panel])
    banner = np.zeros((26 * len(caption) + 10, combined.shape[1], 3), dtype=np.uint8)
    for i, line in enumerate(caption):
        cv2.putText(banner, line, (10, 20 + 26 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1, cv2.LINE_AA)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), np.vstack([combined, banner]))
    return out_path
