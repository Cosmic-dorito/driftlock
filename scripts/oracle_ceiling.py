"""Oracle ceiling: with the EXACT ground-truth pose, is the true site recoverable at all?

This is the experiment that decides whether to keep searching. Every failure so far has been
attributed to selection, but selection operates on templates built at an ESTIMATED pose. If the
estimate is even slightly wrong, the true site is handicapped relative to an impostor that happens
to suit the estimate better.

So hand the matcher the answer to the geometry: read scale_ratio and rotation_deg from the manifest,
build the template at exactly that pose, and correlate over the whole search image.

  argmax at the truth  -> the information IS there; geometry estimation is the bottleneck
  argmax elsewhere     -> even a perfect pose cannot separate them at this dose and footprint

The second outcome is a measured information limit rather than an algorithmic shortfall, and it is
the only evidence that would justify stopping.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import localize as L  # noqa: E402
from src.driftlock.io import load_grayscale, read_manifest, resolve_manifest_path  # noqa: E402
from src.driftlock.match import build_template, correlation_surface, localize  # noqa: E402

NEAR = 5.0
SPLITS = {"sponsor": "data/_sponsor/verify", "bench": "data/bench",
          "finfet": "data/holdout_finfet"}


def main() -> int:
    cfg = L.build_config(argparse.Namespace(config="driftlock"))
    rows = []

    for split, folder in SPLITS.items():
        manifest = REPO / folder / "manifest.csv"
        for rec in read_manifest(manifest):
            gt = (float(rec["gt_x"]), float(rec["gt_y"]))
            ref = load_grayscale(resolve_manifest_path(manifest, rec["reference_path"]))
            search = load_grayscale(resolve_manifest_path(manifest, rec["search_path"]))

            m = localize(ref, search, cfg)
            shipped_ok = math.hypot(m.x - gt[0], m.y - gt[1]) <= NEAR

            # The generator records the exact pose it used.
            scale = float(rec.get("scale_ratio") or 10.0)
            rot = float(rec.get("rotation_deg") or 0.0)
            tpl = build_template(ref.astype(np.float32), scale, rot)
            surf = correlation_surface(search.astype(np.float32), tpl)
            _, _, _, loc = cv2.minMaxLoc(surf)
            th, tw = tpl.shape
            ox, oy = loc[0] + tw / 2.0, loc[1] + th / 2.0
            oracle_ok = math.hypot(ox - gt[0], oy - gt[1]) <= NEAR

            rows.append({"split": split, "id": rec["id"], "shipped": shipped_ok,
                         "oracle": oracle_ok,
                         "err_oracle": math.hypot(ox - gt[0], oy - gt[1])})

    n = len(rows)
    s_ok = sum(r["shipped"] for r in rows)
    o_ok = sum(r["oracle"] for r in rows)
    fails = [r for r in rows if not r["shipped"]]
    rescued = sum(1 for r in fails if r["oracle"])
    print(f"\n  {n} pairs")
    print(f"    shipped pipeline correct        : {s_ok}/{n} = {100 * s_ok / n:.1f}%")
    print(f"    ORACLE POSE + plain argmax      : {o_ok}/{n} = {100 * o_ok / n:.1f}%")
    print()
    print(f"    of the {len(fails)} shipped failures, the oracle pose recovers : {rescued}")
    print(f"    irrecoverable even with perfect geometry               : {len(fails) - rescued}")
    broke = sum(1 for r in rows if r["shipped"] and not r["oracle"])
    print(f"    (oracle loses {broke} pairs the shipped pipeline gets right - it has no refit)")

    out = REPO / "results" / "oracle_ceiling.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        fh.write("\n# Template built at the generator's recorded scale_ratio/rotation_deg, then a\n")
        fh.write("# single plain correlation over the whole search image. No pose search, no\n")
        fh.write("# refit, no screen - this isolates how much of the failure is geometry.\n")
    print(f"\n  Wrote {out.relative_to(REPO).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
