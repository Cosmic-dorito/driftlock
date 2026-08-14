#!/usr/bin/env python3
"""Stratified robustness sweep: accuracy across noise, scale, rotation and target position.

    python scripts/robustness_sweep.py                 # full sweep, ~20 min
    python scripts/robustness_sweep.py --pairs 20      # faster

Why this exists. The problem statement lists, under required deliverables:

    "Results across multiple noise levels, target positions, scales and rotations."

We were not producing that. Every number in `results/` came from three splits at ONE operating
point, which answers "how good is it?" but not "where does it break?" - and the spec also warns that
the released test data uses parameters we have not seen. A single-point result cannot distinguish a
method that degrades gracefully from one that falls off a cliff just outside the tested envelope.

**This is validation, not tuning (R5).** Nothing is fitted here and no threshold is chosen from
these numbers. The seeds are drawn from a band disjoint from `bench` (123403702+), `dev`
(777723331+) and `holdout_finfet` (42425472726+) so a stress split can never coincide with a
reporting or tuning pair. If a future change is tuned against this sweep, the sweep is dead and must
be regenerated with fresh seeds.

The ladders deliberately run PAST the specified envelope. The spec promises ~9:1-11:1 and 1-2
degrees; we measure to 8:1-12:1 and 5 degrees, and down to a twentieth of the nominal dose. Knowing
the shape of the failure beyond the envelope is worth more than another point inside it.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import localize as L  # noqa: E402
from src.driftlock.io import (  # noqa: E402
    euclidean_error,
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)
from src.driftlock.match import localize  # noqa: E402

MISLOCK_PX = 5.0
STRESS_DIR = REPO_ROOT / "data" / "_stress"
SEED_BASE = 90_000_000          # disjoint from every reporting and tuning split

# (axis, label, in_envelope, generator flags). `in_envelope` records whether the point lies inside
# the range the problem statement actually promises, so the table can separate "we were asked to
# handle this" from "we went looking for the cliff".
LADDERS: list[tuple[str, str, bool, list[str]]] = [
    # Shot noise. Dose 200 is the sponsor's own default and our nominal.
    ("noise (dose)", "dose 800  (4x nominal)", True, ["--dose-search", "800"]),
    ("noise (dose)", "dose 400  (2x)", True, ["--dose-search", "400"]),
    ("noise (dose)", "dose 200  NOMINAL", True, ["--dose-search", "200"]),
    ("noise (dose)", "dose 100  (2x noisier)", False, ["--dose-search", "100"]),
    ("noise (dose)", "dose 50   (4x noisier)", False, ["--dose-search", "50"]),
    ("noise (dose)", "dose 25   (8x noisier)", False, ["--dose-search", "25"]),
    # Read noise - the other half of the Poisson-Gaussian model, constant-variance.
    ("noise (read sigma)", "sigma 5   NOMINAL", True, ["--detector-noise-sigma-search", "5"]),
    ("noise (read sigma)", "sigma 10  (2x)", False, ["--detector-noise-sigma-search", "10"]),
    ("noise (read sigma)", "sigma 20  (4x)", False, ["--detector-noise-sigma-search", "20"]),
    # Magnification. Spec says nominal 10:1, robustness ~9:1-11:1.
    ("scale", "10:1 fixed  (sponsor-like)", True, ["--scale-min", "10", "--scale-max", "10"]),
    ("scale", "9-11:1  SPEC ENVELOPE", True, ["--scale-min", "9", "--scale-max", "11"]),
    ("scale", "8-12:1  (beyond spec)", False, ["--scale-min", "8", "--scale-max", "12"]),
    # Rotation. Spec says 1-2 degrees.
    ("rotation", "0 deg", True, ["--rotation-max", "0"]),
    ("rotation", "+/-1 deg", True, ["--rotation-max", "1"]),
    ("rotation", "+/-2 deg  SPEC ENVELOPE", True, ["--rotation-max", "2"]),
    ("rotation", "+/-3 deg  (beyond spec)", False, ["--rotation-max", "3"]),
    ("rotation", "+/-5 deg  (beyond spec)", False, ["--rotation-max", "5"]),
    # Degradations the sponsor's generator leaves at zero, so they are untested by anyone who
    # validates only on it. The spec names every one of these as a possible degradation.
    ("other degradation", "gamma 0.7 + vignette 0.4", False,
     ["--gamma", "0.7", "--vignette-strength", "0.4"]),
    ("other degradation", "charging streaks", False,
     ["--charging-streak-prob", "0.3", "--charging-streak-intensity", "25"]),
    ("other degradation", "salt-and-pepper + speckle", False,
     ["--salt-pepper-prob", "0.01", "--speckle-sigma", "0.1"]),
    ("other degradation", "beam spot 12 nm (heavy blur)", False, ["--beam-spot-size-nm", "12"]),
    ("other degradation", "barrel distortion", False, ["--barrel-distortion-k", "0.05"]),
]


def generate(split: str, flags: list[str], pairs: int, seed: int, arch: str) -> Path:
    out = STRESS_DIR / split / "manifest.csv"
    if out.exists():
        return out
    cmd = [sys.executable, str(REPO_ROOT / "generate_dataset.py"),
           "--num-samples", str(pairs), "--split", split, "--seed", str(seed),
           "--output-dir", str(STRESS_DIR.parent / "_stress"), "--architectures", arch, *flags]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def score(manifest: Path, config) -> dict:
    errors, runtimes = [], []
    for row in read_manifest(manifest):
        ref = load_grayscale(resolve_manifest_path(manifest, row["reference_path"]))
        search = load_grayscale(resolve_manifest_path(manifest, row["search_path"]))
        started = time.perf_counter()
        try:
            match = localize(ref, search, config)
            errors.append(euclidean_error((match.x, match.y),
                                          (float(row["gt_x"]), float(row["gt_y"]))))
        except Exception:
            errors.append(float("inf"))
        runtimes.append((time.perf_counter() - started) * 1000.0)
    err = np.asarray(errors)
    finite = err[np.isfinite(err)]
    return {
        "mislock": float((err > MISLOCK_PX).mean()),
        "median": float(np.median(finite)) if finite.size else float("nan"),
        "pass1": float((err <= 1.0).mean()),
        "ms": float(np.median(runtimes)),
        "n": int(err.size),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=30)
    ap.add_argument("--arch", default="dram", choices=["dram", "finfet"])
    ap.add_argument("--out", default="results/robustness.csv")
    args = ap.parse_args()

    import argparse as _ap
    cfg = L.build_config(_ap.Namespace(config="driftlock"))
    base = L.build_config(_ap.Namespace(config="baseline"))

    rows = []
    print(f"\n  {'axis':<20}{'point':<30}{'env':>5}{'base':>8}{'ours':>8}{'median':>9}{'ms':>7}")
    print("  " + "-" * 87)
    for index, (axis, label, in_env, flags) in enumerate(LADDERS):
        split = f"s{index:02d}"
        manifest = generate(split, flags, args.pairs, SEED_BASE + index * 1000, args.arch)
        ours, theirs = score(manifest, cfg), score(manifest, base)
        rows.append({
            "axis": axis, "point": label, "in_spec_envelope": in_env, "n_pairs": ours["n"],
            "baseline_mislock": f"{theirs['mislock']:.4f}",
            "driftlock_mislock": f"{ours['mislock']:.4f}",
            "baseline_median_px": f"{theirs['median']:.3f}",
            "driftlock_median_px": f"{ours['median']:.3f}",
            "driftlock_pass1px": f"{ours['pass1']:.4f}",
            "driftlock_p50_ms": f"{ours['ms']:.1f}",
            "seed_base": SEED_BASE + index * 1000, "flags": " ".join(flags),
        })
        print(f"  {axis:<20}{label:<30}{'yes' if in_env else 'NO':>5}"
              f"{theirs['mislock'] * 100:>7.1f}%{ours['mislock'] * 100:>7.1f}%"
              f"{ours['median']:>9.3f}{ours['ms']:>7.0f}")

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        fh.write("\n# VALIDATION ONLY - nothing is tuned on these splits (rule R5).\n")
        fh.write(f"# Seeds {SEED_BASE}+, disjoint from bench/dev/holdout_finfet by construction.\n")
        fh.write(f"# architecture={args.arch}, {args.pairs} pairs per point.\n")
    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
