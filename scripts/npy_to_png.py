#!/usr/bin/env python3
"""Convert ``.npy`` arrays to ``.png`` images, so results can be inspected visually.

    python scripts/npy_to_png.py --input data/test               # every .npy in the tree
    python scripts/npy_to_png.py --input ref.npy --output ref.png
    python scripts/npy_to_png.py --input data/test --output png/ --recursive

**Why this is a separate script.** The organiser asked for the conversion to be kept as its own
module and for the main workflow to document how it is invoked, on the grounds that PNGs let
evaluators inspect results quickly. It is deliberately *not* a step the inference path depends on:
``localize.py`` reads ``.npy`` directly (see ``src/driftlock/io.py::_load_npy``), because the
problem statement is explicit that an inference script which needs manual preparation cannot be
scored. Conversion is for humans; the pipeline does not need it.

**The conversion is lossy in one specific way, and it is stated rather than hidden.** A float array
is rescaled to 8-bit for display. If the analysis that produced the array cares about values outside
[0, 255], convert for viewing only and keep the ``.npy`` as the source of truth. The scaling rule
matches ``_load_npy`` exactly, so what you see in the PNG is what the matcher received.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.driftlock.io import _load_npy  # noqa: E402


def convert(source: Path, destination: Path) -> tuple[int, int]:
    """Write one ``.npy`` as a PNG. Returns the image shape for the caller's log."""
    image = _load_npy(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), image):
        raise OSError(f"could not write {destination}")
    return image.shape[:2]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True,
                    help="a .npy file, or a directory to convert")
    ap.add_argument("--output",
                    help="output .png (single file) or directory. Defaults to alongside the input.")
    ap.add_argument("--recursive", action="store_true",
                    help="descend into sub-directories when --input is a directory")
    args = ap.parse_args(argv)

    source = Path(args.input)
    if not source.exists():
        print(f"error: {source} does not exist", file=sys.stderr)
        return 2

    if source.is_file():
        if source.suffix.lower() != ".npy":
            print(f"error: {source} is not a .npy file", file=sys.stderr)
            return 2
        destination = Path(args.output) if args.output else source.with_suffix(".png")
        if destination.is_dir():
            destination = destination / f"{source.stem}.png"
        height, width = convert(source, destination)
        print(f"  {source} -> {destination}  ({width}x{height})")
        return 0

    pattern = "**/*.npy" if args.recursive else "*.npy"
    files = sorted(source.glob(pattern))
    if not files:
        print(f"error: no .npy files under {source}"
              f"{'' if args.recursive else ' (try --recursive)'}", file=sys.stderr)
        return 2

    out_root = Path(args.output) if args.output else source
    for npy in files:
        # Mirror the input tree under --output so a recursive run cannot collide two files that
        # share a basename in different directories.
        relative = npy.relative_to(source).with_suffix(".png")
        height, width = convert(npy, out_root / relative)
        print(f"  {npy} -> {out_root / relative}  ({width}x{height})")
    print(f"\n  Converted {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
