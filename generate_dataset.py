#!/usr/bin/env python3
"""Generate a synthetic Drift-Sense dataset: reference/search pairs with exact ground truth.

    python generate_dataset.py --num-samples 30 --split bench --seed 1234 --output-dir data

Writes::

    data/<split>/reference/00000.png     1000x1000 uint8, 100x view at 1 nm/px
    data/<split>/search/00000.png        1000x1000 uint8, 10x view at ~10 nm/px
    data/<split>/meta/00000.json         every parameter used for this pair
    data/<split>/manifest.csv            paths, ground truth, and full per-pair metadata

Fully reproducible: the same ``--seed`` regenerates byte-identical images, so datasets travel as
seeds rather than as gigabytes of PNGs.

What this models that the sponsor's published generator does not:

* **secondary-electron edge brightening** - theirs paints flat grey levels per material
* **rotation (up to 2 degrees) and scale variation (9:1 to 11:1)** - the spec says both will be
  tested; theirs produces neither
* **continuous ground truth** from fractional crop origins - theirs quantises to a 0.1 px grid
* **genuine per-mat geometry variation** - in theirs, every DRAM preset renders identically
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.synth.pipeline import GenerationParams, generate_sample  # noqa: E402

MANIFEST_COLUMNS = [
    "id", "reference_path", "search_path", "gt_x", "gt_y",
    "gt_box_x", "gt_box_y", "gt_box_w", "gt_box_h",
    "architecture", "modality", "preset", "scale_ratio", "rotation_deg",
    "beam_spot_size_nm", "dose_reference", "dose_search",
    "detector_noise_sigma_ref", "detector_noise_sigma_search",
    "shear_amplitude_px", "drift_jitter_px", "astigmatism_ratio",
    "vignette_strength", "gamma", "barrel_distortion_k",
    "charging_streak_prob", "charging_streak_intensity",
    "speckle_sigma", "salt_pepper_prob",
    "edge_brightness_A", "edge_sigma_nm",
    "linewidth_bias_nm", "corner_rounding_px",
    "mat_size_nm", "strip_width_nm", "boundary_bias",
    "ambiguity_level", "seed",
]


def build_params(args: argparse.Namespace) -> GenerationParams:
    return GenerationParams(
        scale_min=args.scale_min, scale_max=args.scale_max,
        rotation_deg_max=args.rotation_max,
        architectures=tuple(args.architectures),
        dose_reference=args.dose_reference, dose_search=args.dose_search,
        detector_noise_sigma_ref=args.detector_noise_sigma_ref,
        detector_noise_sigma_search=args.detector_noise_sigma_search,
        shear_amplitude_px=args.shear_amplitude_px,
        drift_jitter_px=args.drift_jitter_px,
        gamma=args.gamma, vignette_strength=args.vignette_strength,
        barrel_distortion_k=args.barrel_distortion_k,
        speckle_sigma=args.speckle_sigma, salt_pepper_prob=args.salt_pepper_prob,
        charging_streak_prob=args.charging_streak_prob,
        charging_streak_intensity=args.charging_streak_intensity,
        astigmatism_ratio=args.astigmatism_ratio,
        linewidth_bias_nm=args.linewidth_bias_nm,
        mat_size_nm=args.mat_size_nm, strip_width_nm=args.strip_width_nm,
        boundary_bias=args.boundary_bias,
        edge_gain_min=args.edge_gain_min, edge_gain_max=args.edge_gain_max,
        beam_spot_size_nm=args.beam_spot_size_nm,
        modality=getattr(args, "modality", "sem"),
    )


def _record_path(path: Path, manifest_dir: Path) -> str:
    """The path to record in the manifest: forward-slashed, and never absolute.

    CLAUDE.md fixes the contract as "relative to the repo root, always forward-slashed", and the
    no-hard-coded-paths rule is a literal item on the sponsor's checklist. The previous version
    recorded ``ref_path.as_posix()`` directly, which satisfies both only when ``--output-dir``
    happens to sit inside the repo. Point it anywhere else and the manifest filled up with
    ``C:/Users/...`` - found by tests/test_determinism.py, which generates into a temp directory
    and so was the first thing here ever to run the generator from outside the tree.

    Repo-relative is preferred, so manifests generated the normal way are byte-identical to the
    ones already committed. Outside the repo, manifest-relative is both portable and resolvable:
    :func:`src.driftlock.io.resolve_manifest_path` already tries the manifest's own directory.
    """
    resolved = path.resolve()
    for base in (REPO_ROOT, manifest_dir.resolve()):
        try:
            return resolved.relative_to(base).as_posix()
        except ValueError:
            continue
    # Unreachable in practice: the images are always written under manifest_dir. Kept rather than
    # raising, because a generator that aborts after painting the canvases would be worse.
    return path.name


def _for_png(img: np.ndarray) -> np.ndarray:
    """RGB -> BGR for OpenCV's writer; grayscale passes through untouched."""
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if img.ndim == 3 else img


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--num-samples", type=int, default=30)
    p.add_argument("--split", default="bench")
    p.add_argument("--output-dir", default="data")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--architectures", nargs="+", default=["dram"], choices=["dram", "finfet"])
    p.add_argument("--modality", default="sem", choices=["sem", "optical"],
                   help="'optical' emits 3-channel RGB brightfield pairs - the spec's bonus "
                        "modality. Different physics, not a colourised SEM: see src/synth/optical.py")

    g = p.add_argument_group("magnification and pose (the sponsor's generator has neither)")
    g.add_argument("--scale-min", type=float, default=9.0)
    g.add_argument("--scale-max", type=float, default=11.0)
    g.add_argument("--rotation-max", type=float, default=2.0, help="degrees, +/-")

    o = p.add_argument_group("optics and SE response")
    o.add_argument("--beam-spot-size-nm", type=float, default=5.0)
    o.add_argument("--astigmatism-ratio", type=float, default=1.0)
    o.add_argument("--edge-gain-min", type=float, default=0.35)
    o.add_argument("--edge-gain-max", type=float, default=0.75)

    n = p.add_argument_group("dose and noise")
    n.add_argument("--dose-reference", type=float, default=2000.0)
    n.add_argument("--dose-search", type=float, default=200.0)
    # Exposed so the robustness sweep can vary BOTH halves of the Poisson-Gaussian model
    # independently. Dose sets the shot-noise term (variance proportional to signal); this sets the
    # read-noise term (variance constant). They degrade an image differently - shot noise hurts the
    # bright contacts most, read noise hurts the dark background - so a sweep over dose alone would
    # only cover one of the two axes the spec asks about.
    n.add_argument("--detector-noise-sigma-ref", type=float, default=2.0)
    n.add_argument("--detector-noise-sigma-search", type=float, default=5.0)
    n.add_argument("--speckle-sigma", type=float, default=0.0)
    n.add_argument("--salt-pepper-prob", type=float, default=0.0)

    s = p.add_argument_group("scan artefacts")
    s.add_argument("--shear-amplitude-px", type=float, default=1.5)
    s.add_argument("--drift-jitter-px", type=float, default=0.5)
    s.add_argument("--barrel-distortion-k", type=float, default=0.0)
    s.add_argument("--vignette-strength", type=float, default=0.0)
    s.add_argument("--gamma", type=float, default=1.0)
    s.add_argument("--charging-streak-prob", type=float, default=0.0)
    s.add_argument("--charging-streak-intensity", type=float, default=0.0)

    t = p.add_argument_group("structure")
    t.add_argument("--mat-size-nm", type=float, default=2600.0)
    t.add_argument("--strip-width-nm", type=float, default=320.0)
    t.add_argument("--boundary-bias", type=float, default=0.35)
    t.add_argument("--linewidth-bias-nm", type=float, default=0.0)

    args = p.parse_args(argv)
    params = build_params(args)

    split_dir = Path(args.output_dir) / args.split
    ref_dir, search_dir, meta_dir = (split_dir / "reference", split_dir / "search",
                                     split_dir / "meta")
    for d in (ref_dir, search_dir, meta_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = split_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        writer.writeheader()

        for i in range(args.num_samples):
            # Per-sample seed derived from the split seed, so any single pair can be regenerated
            # in isolation without replaying the whole dataset.
            sample = generate_sample(args.seed * 100_003 + i, params)

            ref_path = ref_dir / f"{i:05d}.png"
            search_path = search_dir / f"{i:05d}.png"
            # The optical renderer works in RGB channel order (index 0 is the 610 nm band) while
            # cv2.imwrite expects BGR, so a straight write would save a colour-swapped file. The
            # task would still be self-consistent, but the PNGs would not be true-colour and every
            # figure in the deck would be wrong in a way nobody would notice.
            cv2.imwrite(str(ref_path), _for_png(sample.reference))
            cv2.imwrite(str(search_path), _for_png(sample.search))

            row = {
                "id": i,
                # Forward-slashed and never absolute, so manifests work on any machine.
                "reference_path": _record_path(ref_path, manifest_path.parent),
                "search_path": _record_path(search_path, manifest_path.parent),
                "gt_x": f"{sample.gt_x:.6f}",
                "gt_y": f"{sample.gt_y:.6f}",
                **sample.metadata,
            }
            writer.writerow(row)
            (meta_dir / f"{i:05d}.json").write_text(
                json.dumps(row, indent=2, default=str), encoding="utf-8"
            )

            print(f"[{i + 1}/{args.num_samples}] {sample.metadata['architecture']:>6} "
                  f"scale={sample.metadata['scale_ratio']:.2f} "
                  f"rot={sample.metadata['rotation_deg']:+.2f} "
                  f"amb={sample.metadata['ambiguity_level']:<4} "
                  f"gt=({sample.gt_x:.2f}, {sample.gt_y:.2f})", file=sys.stderr)

    print(f"Wrote {args.num_samples} pairs to {split_dir.as_posix()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
