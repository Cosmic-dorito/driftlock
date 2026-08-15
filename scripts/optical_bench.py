#!/usr/bin/env python3
"""The RGB optical bonus: does the SEM pipeline transfer, and does using the colour help?

    python scripts/optical_bench.py --manifest data/optical/manifest.csv

The problem statement lists an "RGB optical-image extension" as a bonus after the grayscale SEM
task. Two questions, in order, because the second is only interesting if the first says yes:

  1. Does the physics-based matcher transfer to a *different imaging modality* unchanged? It was
     built around an electron beam, an area-average decimation and Poisson-Gaussian noise. Optical
     brightfield shares none of those: it is diffraction-limited, its contrast comes from thin-film
     interference, and its three channels are separate photodiodes.

  2. Given that it does, is anything gained by using the colour rather than collapsing it? The
     reflex is Rec. 601 luminance, whose weights describe the human eye and have nothing to do with
     a film stack. The alternative measured here is to take the direction in RGB space along which
     the REFERENCE's own pixels vary most - the projection that best separates the materials that
     are actually on this wafer (src/driftlock/color.py).

Three arms, identical in every other respect, so the comparison is exactly paired:

  luma   Rec. 601 - what happens today if an RGB pair is handed to the existing CLI
  pca    the measured contrast projection
  green  the single sharpest channel, as a control - if 'pca' only ever picks one channel, the
         honest description is 'we chose a channel', not 'we used the colour'

Emits results/optical.csv before anything is interpreted (ADR-0030).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import localize as L  # noqa: E402
from src.driftlock.color import (  # noqa: E402
    LUMA_RGB,
    contrast_projection,
    load_rgb,
    project,
)
from src.driftlock.io import read_manifest, resolve_manifest_path  # noqa: E402
from src.driftlock.match import localize  # noqa: E402

NEAR_PX = 5.0
GREEN = np.array([0.0, 1.0, 0.0], dtype=np.float64)


def mcnemar_exact(only_a: int, only_b: int) -> float:
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = min(only_a, only_b)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(tail + 1)) / 2 ** n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=Path("data/optical/manifest.csv"))
    ap.add_argument("--out", type=Path, default=Path("results/optical.csv"))
    args = ap.parse_args()

    manifest = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    out_path = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    if not manifest.exists():
        sys.exit(f"missing {manifest} - generate it with "
                 f"`python generate_dataset.py --modality optical --split optical`")

    cfg = L.build_config(argparse.Namespace(config="driftlock"))
    arms = {"luma": LUMA_RGB / np.linalg.norm(LUMA_RGB), "pca": None, "green": GREEN}
    rows: list[dict] = []

    for rec in read_manifest(manifest):
        gt_x, gt_y = float(rec["gt_x"]), float(rec["gt_y"])
        ref_rgb = load_rgb(resolve_manifest_path(manifest, rec["reference_path"]))
        search_rgb = load_rgb(resolve_manifest_path(manifest, rec["search_path"]))
        if ref_rgb.ndim != 3:
            sys.exit(f"{rec['reference_path']} is not a colour image - wrong split?")

        measured = contrast_projection(ref_rgb)
        row: dict = {"id": rec["id"],
                     "pca_r": round(float(measured[0]), 4),
                     "pca_g": round(float(measured[1]), 4),
                     "pca_b": round(float(measured[2]), 4),
                     # How far the measured direction is from plain luminance. If this is ~0 the
                     # two arms are the same thing and any difference between them is noise.
                     "angle_from_luma_deg": round(float(np.degrees(np.arccos(
                         np.clip(measured @ (LUMA_RGB / np.linalg.norm(LUMA_RGB)), -1, 1)))), 2)}

        for name, fixed in arms.items():
            direction = measured if fixed is None else fixed / np.linalg.norm(fixed)
            ref = project(ref_rgb, direction)
            search = project(search_rgb, direction)
            started = time.perf_counter()
            match = localize(ref.astype(np.uint8), search.astype(np.uint8), cfg)
            elapsed = (time.perf_counter() - started) * 1000.0
            err = math.hypot(match.x - gt_x, match.y - gt_y)
            row[f"err_{name}"] = round(err, 4)
            row[f"ok_{name}"] = int(err <= NEAR_PX)
            row[f"ms_{name}"] = round(elapsed, 1)
        rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        for line in [
            "# RGB optical brightfield, the problem statement's bonus modality. The SEM pipeline is",
            "# unchanged; only the RGB -> single-channel projection differs between the three arms.",
            "# luma  = Rec. 601, the weights a human eye would use",
            "# pca   = the direction of greatest colour variance in the REFERENCE, measured per pair",
            "# green = the single sharpest channel, as a control on what 'pca' is really doing",
        ]:
            fh.write(line + "\n")

    n = len(rows)
    print(f"\n  RGB optical, {n} pairs\n")
    print(f"  {'arm':<8}{'mis-lock':>11}{'median px':>12}{'p95 px':>10}{'pass@1px':>11}{'p50 ms':>9}")
    print("  " + "-" * 61)
    for name in arms:
        errs = np.array([r[f"err_{name}"] for r in rows])
        ok = np.array([r[f"ok_{name}"] for r in rows])
        located = errs[ok.astype(bool)]
        print(f"  {name:<8}{100 * (1 - ok.mean()):>10.1f}%"
              f"{(np.median(located) if located.size else float('nan')):>12.4f}"
              f"{np.percentile(errs, 95):>10.2f}"
              f"{100 * (errs <= 1.0).mean():>10.1f}%"
              f"{np.median([r[f'ms_{name}'] for r in rows]):>9.0f}")

    print()
    for challenger in ("pca", "green"):
        fixed = sum(1 for r in rows if not r["ok_luma"] and r[f"ok_{challenger}"])
        broke = sum(1 for r in rows if r["ok_luma"] and not r[f"ok_{challenger}"])
        better = sum(1 for r in rows if r[f"err_{challenger}"] < r["err_luma"])
        print(f"  {challenger} vs luma: +{fixed}/-{broke} mis-locks, "
              f"more accurate on {better}/{n}, exact McNemar p = "
              f"{mcnemar_exact(broke, fixed):.3f}")

    angles = [r["angle_from_luma_deg"] for r in rows]
    print(f"\n  measured projection sits {np.median(angles):.1f} deg from luminance "
          f"(min {min(angles):.1f}, max {max(angles):.1f})")
    mean_dir = np.mean([[r["pca_r"], r["pca_g"], r["pca_b"]] for r in rows], axis=0)
    print(f"  mean direction  R {mean_dir[0]:+.3f}  G {mean_dir[1]:+.3f}  B {mean_dir[2]:+.3f}")
    print(f"\n  Wrote {out_path.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
