#!/usr/bin/env python3
"""For the failures the candidate generator never proposes, does ANY representation see them?

    python scripts/proposal_forensics.py

Three of the eight remaining failures are `absent`: the true site never enters the candidate set, so
no selection rule of any kind can reach them. That bucket has not moved through any change made so
far, because nothing built so far touches candidate generation.

The tempting next move is to build a proposal-union pipeline. This script exists to avoid doing that
blind. It asks the cheap diagnostic question first:

    plot the correlation surface of each candidate representation and see whether ANY of them has a
    peak near the truth.

If one does, that representation is the proposal mechanism and the engineering is obvious. If none
does, the information is not present in any of them and a union of them cannot conjure it - which
saves building the whole thing to discover that.

CONTROLS THAT MAKE THE ANSWER MEAN SOMETHING

* Every representation is scored at the generator's **exact recorded pose**, so a representation is
  never blamed for a pose error. This isolates "can it see the site" from "can it estimate geometry".
* The same statistic is reported for every representation - the truth's rank among non-maximum-
  suppressed peaks - so a representation with a high score everywhere gains nothing.
* The `correct` pairs are measured too. A representation that ranks the truth first on the failures
  but also on nothing else would just be noise; the contrast is the evidence.

REPRESENTATIONS

  intensity   what ships - the control
  edge        Scharr gradient magnitude; structure without absolute grey level
  variance    local standard deviation; texture energy rather than edges
  residual    the image minus its own lattice-periodic prediction, in the SPATIAL domain

The residual deserves a note, because it looks like PADM (§8), which failed. PADM removed periodic
frequencies with a Fourier mask and used the result as a RANKING score with two tuned constants.
This builds the periodic prediction by averaging the image over its own lattice translations,
subtracts it, and uses the result **only to propose locations**. A representation can be hopeless at
ranking and still be useful at proposing, and those are different claims.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.driftlock.io import (  # noqa: E402
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)
from src.driftlock.match import (  # noqa: E402
    PipelineConfig,
    build_template,
    correlation_surface,
)

NEAR_PX = 5.0
SPLITS = {"sponsor": "data/_sponsor/verify", "bench": "data/bench",
          "finfet": "data/holdout_finfet"}
TOP_PEAKS = 30                 # the pool the pipeline actually keeps, so the rank is comparable
MIN_PERIOD_PX = 4.0
MAX_PERIOD_PX = 60.0


# ---------------------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------------------

def rep_intensity(image: np.ndarray) -> np.ndarray:
    return image.astype(np.float32)


def rep_edge(image: np.ndarray) -> np.ndarray:
    """Scharr gradient magnitude - structure without absolute grey level."""
    work = image.astype(np.float32)
    gx = cv2.Scharr(work, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(work, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


def rep_variance(image: np.ndarray, ksize: int = 5) -> np.ndarray:
    """Local standard deviation - texture energy rather than edge position."""
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


def rep_residual(image: np.ndarray) -> np.ndarray:
    """The image minus its own lattice-periodic prediction, built in the spatial domain.

    The prediction is the average of the image shifted by +-1 and +-2 lattice periods along each
    axis. Whatever repeats survives that average; whatever is unique to a site does not, so the
    residual keeps the aperiodic fingerprint. Excluding the zero shift matters - including it would
    put the site's own content into its own prediction and cancel the thing being looked for.
    """
    work = image.astype(np.float32)
    py, px = dominant_period(work, 0), dominant_period(work, 1)
    if not (MIN_PERIOD_PX <= py <= MAX_PERIOD_PX) or not (MIN_PERIOD_PX <= px <= MAX_PERIOD_PX):
        return work - cv2.blur(work, (9, 9))          # fall back to a plain high-pass
    height, width = work.shape
    accum = np.zeros_like(work)
    count = 0
    for ky in (-2, -1, 0, 1, 2):
        for kx in (-2, -1, 0, 1, 2):
            if ky == 0 and kx == 0:
                continue
            matrix = np.array([[1.0, 0.0, kx * px], [0.0, 1.0, ky * py]], dtype=np.float32)
            accum += cv2.warpAffine(work, matrix, (width, height), flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REFLECT)
            count += 1
    return work - accum / max(count, 1)


REPRESENTATIONS = {
    "intensity": rep_intensity,
    "edge": rep_edge,
    "variance": rep_variance,
    "residual": rep_residual,
}


# ---------------------------------------------------------------------------------------

def peak_rank_of_truth(surface: np.ndarray, template_size: int, gt: tuple[float, float],
                       nms_radius: float) -> tuple[int, float, float]:
    """Rank of the truth among NMS peaks, its score, and the surface maximum.

    Returns rank -1 if the truth is not among the top TOP_PEAKS peaks. Non-maximum suppression uses
    the same radius idea as the pipeline's extractor so the rank means the same thing.
    """
    work = surface.copy()
    half = template_size / 2.0
    gx, gy = gt
    peaks: list[tuple[float, float, float]] = []
    for _ in range(TOP_PEAKS):
        _, value, _, loc = cv2.minMaxLoc(work)
        cx, cy = loc[0] + half, loc[1] + half
        peaks.append((float(value), cx, cy))
        x0, y0 = max(int(loc[0] - nms_radius), 0), max(int(loc[1] - nms_radius), 0)
        x1 = min(int(loc[0] + nms_radius) + 1, work.shape[1])
        y1 = min(int(loc[1] + nms_radius) + 1, work.shape[0])
        work[y0:y1, x0:x1] = -2.0

    rank = next((i for i, (_v, cx, cy) in enumerate(peaks)
                 if math.hypot(cx - gx, cy - gy) <= NEAR_PX), -1)
    # The score AT the truth, whether or not it is a peak - a representation can put signal there
    # without it surviving suppression, and that is worth seeing separately from the rank.
    ty, tx = int(round(gy - half)), int(round(gx - half))
    at_truth = (float(surface[ty, tx])
                if 0 <= ty < surface.shape[0] and 0 <= tx < surface.shape[1] else float("nan"))
    return rank, at_truth, float(peaks[0][0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default="bench:4,bench:17,finfet:17",
                    help="split:id pairs to dissect; defaults to the three ABSENT failures")
    ap.add_argument("--controls", type=int, default=6,
                    help="correct pairs to measure alongside, as the contrast")
    ap.add_argument("--out", type=Path, default=Path("results/proposal_forensics.csv"))
    args = ap.parse_args()

    out_path = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    wanted = []
    for token in args.ids.split(","):
        split, _, ident = token.strip().partition(":")
        wanted.append((split, ident))

    rows: list[dict] = []
    for split, folder in SPLITS.items():
        manifest = REPO_ROOT / folder / "manifest.csv"
        if not manifest.exists():
            continue
        records = list(read_manifest(manifest))
        targets = [(r, True) for r in records if (split, r["id"]) in wanted]
        controls = [(r, False) for r in records
                    if (split, r["id"]) not in wanted][:args.controls if targets else 0]

        for rec, is_target in targets + controls:
            gt = (float(rec["gt_x"]), float(rec["gt_y"]))
            ref = load_grayscale(resolve_manifest_path(manifest, rec["reference_path"]))
            search = load_grayscale(resolve_manifest_path(manifest, rec["search_path"]))
            scale = float(rec.get("scale_ratio") or 10.0)
            rotation = float(rec.get("rotation_deg") or 0.0)

            for name, transform in REPRESENTATIONS.items():
                # Transform BOTH sides, then build the template at the exact recorded pose, so no
                # representation is ever blamed for a pose error.
                ref_rep = transform(ref)
                search_rep = transform(search)
                template = build_template(ref_rep.astype(np.float32), scale, rotation)
                if template.shape[0] >= search_rep.shape[0]:
                    continue
                surface = correlation_surface(search_rep.astype(np.float32), template)
                # The pipeline's own suppression radius (PipelineConfig.nms_radius_px = 6.0), which
                # is a fraction of a LATTICE PITCH, not of the template. A first version of this
                # used 0.6 x template size = 60 px and read ABSENT on 4 of 12 pairs the pipeline
                # solves correctly - suppressing a 60 px neighbourhood removes the truth whenever
                # any stronger repeat sits within half a footprint of it. That is a property of the
                # measurement, not of the representation.
                rank, at_truth, best = peak_rank_of_truth(
                    surface, template.shape[0], gt, nms_radius=PipelineConfig().nms_radius_px
                )
                rows.append({
                    "split": split, "id": rec["id"],
                    "case": "ABSENT-failure" if is_target else "control-correct",
                    "representation": name,
                    "truth_peak_rank": rank,
                    "score_at_truth": round(at_truth, 4),
                    "surface_max": round(best, 4),
                    "deficit": round(best - at_truth, 4),
                })

    if not rows:
        sys.exit("no matching pairs found")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        for line in [
            "# Every representation is scored at the generator's EXACT recorded pose, so none is",
            "# blamed for a pose error. truth_peak_rank is the truth's position among the top 30",
            "# non-maximum-suppressed peaks, or -1 if it is not among them. The control rows are",
            "# pairs the pipeline already gets right - a representation that ranks the truth first",
            "# everywhere has found nothing, so the contrast is the evidence.",
        ]:
            fh.write(line + "\n")

    print(f"\n  {'case':<17}{'split':<9}{'id':>4}{'representation':>15}"
          f"{'truth rank':>12}{'@truth':>9}{'max':>9}")
    print("  " + "-" * 76)
    for row in sorted(rows, key=lambda r: (r["case"], r["split"], r["id"])):
        rank = "ABSENT" if row["truth_peak_rank"] < 0 else str(row["truth_peak_rank"])
        print(f"  {row['case']:<17}{row['split']:<9}{row['id']:>4}"
              f"{row['representation']:>15}{rank:>12}"
              f"{row['score_at_truth']:>9.4f}{row['surface_max']:>9.4f}")

    print("\n  SUMMARY - does any representation SEE the sites the pipeline never proposes?\n")
    print(f"  {'representation':<14}{'found on failures':>20}{'found on controls':>20}")
    print("  " + "-" * 56)
    for name in REPRESENTATIONS:
        fails = [r for r in rows if r["representation"] == name and r["case"].startswith("ABSENT")]
        ctrls = [r for r in rows if r["representation"] == name and r["case"].startswith("control")]
        f_hit = sum(1 for r in fails if r["truth_peak_rank"] >= 0)
        c_hit = sum(1 for r in ctrls if r["truth_peak_rank"] >= 0)
        print(f"  {name:<14}{f'{f_hit}/{len(fails)}':>20}{f'{c_hit}/{len(ctrls)}':>20}")
    print(f"\n  Wrote {out_path.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
