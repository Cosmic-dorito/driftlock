#!/usr/bin/env python3
"""Accuracy stratified by where the target sits in the field.

    python scripts/position_strata.py

The problem statement asks for results across "multiple noise levels, **target positions**, scales
and rotations". The robustness sweep covers noise, scale and rotation by generating new data; target
position needed no new data at all, because the existing 100 evaluated pairs already place targets
from 32 px to 547 px from the field centre. Stratifying what we have answers the question at zero
generation cost - which matters, since generating a stress split costs more machine time than every
other analysis in this project combined.

Two stratifications, because they ask different questions:

* **Radius from the field centre.** Barrel distortion, vignetting and the drift model's linear
  approximation all worsen with radius, so if any of them were biting, this is where it would show.
  It is also the axis the closest-to-centre tie-break would exploit if it were enabled (ADR-0021).
* **Distance to the nearest image edge.** A target near an edge has less surrounding context for the
  correlation window and less room for the refit's search margin, which is a different mechanism
  from radial distortion and would not show up in the radius view.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MISLOCK_PX = 5.0
SEARCH_SIZE = 1000
CENTRE = (SEARCH_SIZE - 1) / 2.0
SPLITS = {"sponsor": "data/_sponsor/verify",
          "bench": "data/bench",
          "finfet": "data/holdout_finfet"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def collect() -> list[dict]:
    """Every evaluated pair, with its error and where its target sat."""
    out = []
    for split, folder in SPLITS.items():
        manifest = REPO_ROOT / folder / "manifest.csv"
        preds = REPO_ROOT / "results" / f"predictions_{split}.csv"
        if not (manifest.exists() and preds.exists()):
            continue
        with manifest.open(newline="", encoding="utf-8") as fh:
            gt = {r["id"]: (float(r["gt_x"]), float(r["gt_y"])) for r in csv.DictReader(fh)}
        with preds.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["id"] not in gt:
                    continue
                gx, gy = gt[row["id"]]
                error = math.hypot(float(row["pred_x"]) - gx, float(row["pred_y"]) - gy)
                out.append({
                    "split": split, "id": row["id"], "error_px": error,
                    "radius_px": math.hypot(gx - CENTRE, gy - CENTRE),
                    # How close the target centre is to the nearest frame edge.
                    "edge_px": min(gx, gy, SEARCH_SIZE - 1 - gx, SEARCH_SIZE - 1 - gy),
                })
    return out


def report(rows: list[dict], key: str, edges: list[float], labels: list[str]) -> list[dict]:
    out = []
    for lo, hi, label in zip(edges[:-1], edges[1:], labels):
        sel = [r for r in rows if lo <= r[key] < hi]
        if not sel:
            continue
        n = len(sel)
        k = sum(1 for r in sel if r["error_px"] > MISLOCK_PX)
        med = float(np.median([r["error_px"] for r in sel]))
        ci_lo, ci_hi = wilson(k, n)
        out.append({"stratum": f"{key.replace('_px', '')} {label}", "n_pairs": n,
                    "mislock_k": k, "mislock_rate": f"{k / n:.4f}",
                    "ci95_low": f"{ci_lo:.4f}", "ci95_high": f"{ci_hi:.4f}",
                    "median_err_px": f"{med:.3f}"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results/position_strata.csv")
    args = ap.parse_args()

    rows = collect()
    if not rows:
        sys.exit("no predictions found - run localize.py over the splits first")

    table = (report(rows, "radius_px", [0, 200, 350, 10_000], ["inner", "mid", "outer"])
             + report(rows, "edge_px", [0, 120, 250, 10_000], ["near edge", "mid", "central"]))

    print(f"\n  {len(rows)} evaluated pairs, pooled across all three reported splits")
    print(f"\n  {'stratum':<24}{'n':>5}{'mis-lock':>10}{'95% CI':>20}{'median px':>11}")
    print("  " + "-" * 70)
    for r in table:
        ci = f"[{float(r['ci95_low']) * 100:.0f}%, {float(r['ci95_high']) * 100:.0f}%]"
        print(f"  {r['stratum']:<24}{r['n_pairs']:>5}{float(r['mislock_rate']) * 100:>9.1f}%"
              f"{ci:>20}{r['median_err_px']:>11}")

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
        fh.write("\n# Pooled over sponsor + bench + holdout_finfet, the same pairs reported in\n")
        fh.write("# results/metrics_*.csv. No new data: the existing targets already span 32-547 px\n")
        fh.write("# from the field centre, so position is stratified rather than re-generated.\n")
        fh.write("# Wilson intervals; overlapping intervals mean the strata are NOT distinguishable.\n")
    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
