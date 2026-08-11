#!/usr/bin/env python3
"""Locate a 100x reference pattern inside a 10x search image.

    # Single pair - prints EXACTLY one line to stdout: "312.42,489.07"
    python localize.py --reference ref.png --search search.png

    # Batch - the evaluator runs this against their own data with no source edits
    python localize.py --manifest data/test/manifest.csv --out results/predictions.csv
    python localize.py --input-dir data/test/            --out results/predictions.csv

Coordinate convention: origin (0,0) top-left, x right, y down; the output is the CENTRE of the
matched region in search-image pixels, as floats. See src/driftlock/io.py.

stdout carries the coordinate and nothing else - benchmark parsers break on chatty scripts. All
logging, progress and warnings go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.driftlock.io import (  # noqa: E402
    Match,
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
    validate_pair,
    write_predictions,
)
from src.driftlock.match import BASELINE, PipelineConfig, localize  # noqa: E402

EXIT_OK, EXIT_ERROR, EXIT_BAD_INPUT = 0, 1, 2


def log(message: str, verbose: bool = True) -> None:
    """Everything human-readable goes to stderr, never stdout."""
    if verbose:
        print(message, file=sys.stderr)


def build_config(args: argparse.Namespace) -> PipelineConfig:
    """Assemble the pipeline configuration from CLI flags.

    Defaults to BASELINE while the improved stages are still being built and measured; each stage
    is enabled here only once it has earned its place in the ablation table (R9).
    """
    return BASELINE


def run_pair(ref_path: Path, search_path: Path, config: PipelineConfig) -> Match:
    reference = load_grayscale(ref_path)
    search = load_grayscale(search_path)
    validate_pair(reference, search)
    return localize(reference, search, config)


def run_single(args: argparse.Namespace, config: PipelineConfig) -> int:
    started = time.perf_counter()
    match = run_pair(Path(args.reference), Path(args.search), config)
    wall_ms = (time.perf_counter() - started) * 1000.0

    log(f"score={match.score:.4f} runtime={wall_ms:.1f}ms", args.verbose)

    if args.json:
        payload = {
            "x": round(match.x, 4),
            "y": round(match.y, 4),
            "score": round(match.score, 6),
            "confidence_radius_px": match.confidence_radius_px,
            "runtime_ms": round(wall_ms, 2),
        }
        print(json.dumps(payload))
    else:
        # The one line of stdout this program is allowed to produce.
        print(match.as_stdout_line())

    if args.visualize:
        from src.driftlock.visualize import save_overlay
        save_overlay(Path(args.visualize), Path(args.reference), Path(args.search), match)
        log(f"wrote {args.visualize}", args.verbose)

    return EXIT_OK


def _discover_pairs(args: argparse.Namespace) -> list[tuple[str, Path, Path]]:
    """Resolve the batch input into (id, reference_path, search_path) triples."""
    if args.manifest:
        manifest = Path(args.manifest)
        pairs = []
        for row in read_manifest(manifest):
            pair_id = row.get("id") or row.get("pair_id") or str(len(pairs))
            pairs.append((
                str(pair_id),
                resolve_manifest_path(manifest, row["reference_path"]),
                resolve_manifest_path(manifest, row["search_path"]),
            ))
        return pairs

    root = Path(args.input_dir)
    ref_dir, search_dir = root / "reference", root / "search"
    if not (ref_dir.is_dir() and search_dir.is_dir()):
        raise ValueError(
            f"{root} must contain 'reference/' and 'search/' subdirectories, or use --manifest"
        )
    pairs = []
    for ref in sorted(ref_dir.iterdir()):
        search = search_dir / ref.name
        if search.exists():
            pairs.append((ref.stem, ref, search))
    return pairs


def run_batch(args: argparse.Namespace, config: PipelineConfig) -> int:
    pairs = _discover_pairs(args)
    if not pairs:
        log("error: no image pairs found")
        return EXIT_BAD_INPUT

    log(f"processing {len(pairs)} pairs")
    results: list[tuple[str, Match]] = []
    failures = 0

    for index, (pair_id, ref_path, search_path) in enumerate(pairs, 1):
        try:
            started = time.perf_counter()
            match = run_pair(ref_path, search_path, config)
            match = Match(match.x, match.y, match.score, match.confidence_radius_px,
                          (time.perf_counter() - started) * 1000.0)
            results.append((pair_id, match))
        except Exception as exc:
            # One unreadable pair must not abandon the rest of the evaluator's batch.
            failures += 1
            log(f"  [{index}/{len(pairs)}] id={pair_id} FAILED: {type(exc).__name__}: {exc}")
            continue
        if args.verbose:
            log(f"  [{index}/{len(pairs)}] id={pair_id} -> {match.x:.2f},{match.y:.2f} "
                f"score={match.score:.4f} {match.runtime_ms:.0f}ms")

    write_predictions(Path(args.out), results)
    log(f"wrote {args.out} ({len(results)} predictions"
        + (f", {failures} failures)" if failures else ")"))
    return EXIT_OK if not failures else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_argument_group("input (choose one)")
    mode.add_argument("--reference", help="path to the 100x reference image")
    mode.add_argument("--search", help="path to the 10x search image")
    mode.add_argument("--manifest", help="CSV with reference_path and search_path columns")
    mode.add_argument("--input-dir", help="directory containing reference/ and search/")

    parser.add_argument("--out", help="output CSV (required for batch modes)")
    parser.add_argument("--json", action="store_true", help="emit a JSON object instead of 'x,y'")
    parser.add_argument("--visualize", metavar="OUT.png", help="write a crosshair overlay")
    parser.add_argument("--no-rerank", action="store_true",
                        help="force the deterministic path (skip the optional learned re-ranker)")
    parser.add_argument("--verbose", action="store_true", help="stage timings to stderr")
    args = parser.parse_args(argv)

    # Force LF line endings on stdout. Python defaults to CRLF on Windows, which would make the
    # emitted coordinate differ byte-for-byte between our machine and a Linux evaluator - and the
    # reproducibility claim is that the output is identical everywhere.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(newline="\n")

    config = build_config(args)

    try:
        if args.reference and args.search:
            return run_single(args, config)
        if args.manifest or args.input_dir:
            if not args.out:
                log("error: --out is required with --manifest or --input-dir")
                return EXIT_BAD_INPUT
            return run_batch(args, config)
        parser.print_usage(sys.stderr)
        log("error: provide --reference and --search, or --manifest, or --input-dir")
        return EXIT_BAD_INPUT
    except FileNotFoundError as exc:
        log(f"error: {exc}")
        return EXIT_BAD_INPUT
    except ValueError as exc:
        log(f"error: {exc}")
        return EXIT_BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
