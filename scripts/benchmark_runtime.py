#!/usr/bin/env python3
"""Measure per-pair runtime in a way that is actually comparable across splits.

    python scripts/benchmark_runtime.py

Why this is separate from evaluate.py. Runtime measured during an accuracy run is taken split by
split, one after another, over many minutes. On this machine the same code drifted by up to 3x over
a long session and did not recover after idling, so a batch that walks the splits sequentially
attributes that drift to whichever split happened to run late. We observed exactly that: 1228 ms for
sponsor against 354 ms for FinFET inside a single batch, from identical code.

The fix is methodological, not a faster machine:

* **warm up first**, and discard it - the first call pays import, allocation and cache costs;
* **interleave the splits** round-robin, so any drift during the run is spread evenly across all of
  them rather than landing on the last one;
* **report the median**, which a slow tail cannot move;
* record the thread count and hardware alongside, since those change the answer.

The result is a runtime comparison between splits that means something. The absolute number still
depends on the machine's state, and that is stated rather than hidden.
"""

from __future__ import annotations

import argparse
import csv
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import localize as L  # noqa: E402
from src.driftlock.io import load_grayscale, read_manifest, resolve_manifest_path  # noqa: E402
from src.driftlock.match import localize  # noqa: E402

SPLITS = [
    ("sponsor", "data/_sponsor/verify/manifest.csv"),
    ("bench", "data/bench/manifest.csv"),
    ("finfet", "data/holdout_finfet/manifest.csv"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs-per-split", type=int, default=12)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--out", default="results/runtime.csv")
    args = ap.parse_args()

    cfg = L.build_config(argparse.Namespace(config="driftlock"))
    baseline_cfg = L.build_config(argparse.Namespace(config="baseline"))

    loaded: dict[str, list] = {}
    for name, manifest in SPLITS:
        path = Path(manifest)
        if not path.exists():
            continue
        rows = read_manifest(path)[:args.pairs_per_split]
        loaded[name] = [
            (load_grayscale(resolve_manifest_path(path, r["reference_path"])),
             load_grayscale(resolve_manifest_path(path, r["search_path"])))
            for r in rows
        ]

    if not loaded:
        sys.exit("no splits found - generate data first")

    print(f"\n  Warm-up: {args.warmup} calls, discarded")
    first = next(iter(loaded.values()))
    for _ in range(args.warmup):
        localize(*first[0], cfg)

    # Round-robin so drift during the run is shared evenly rather than charged to the last split.
    timings: dict[str, dict[str, list[float]]] = {
        n: {"driftlock": [], "baseline": []} for n in loaded
    }
    depth = max(len(v) for v in loaded.values())
    for i in range(depth):
        for name, pairs in loaded.items():
            if i >= len(pairs):
                continue
            ref, search = pairs[i]
            for label, config in (("driftlock", cfg), ("baseline", baseline_cfg)):
                start = time.perf_counter()
                localize(ref, search, config)
                timings[name][label].append((time.perf_counter() - start) * 1000.0)

    print(f"\n  {'split':<12}{'config':<12}{'p50 ms':>9}{'p95 ms':>9}{'n':>5}")
    out_rows = []
    for name, per_config in timings.items():
        for label, values in per_config.items():
            if not values:
                continue
            arr = np.array(values)
            print(f"  {name:<12}{label:<12}{np.median(arr):>9.0f}{np.percentile(arr, 95):>9.0f}"
                  f"{len(arr):>5}")
            out_rows.append({
                "split": name, "config": label, "n": len(arr),
                "p50_ms": f"{np.median(arr):.1f}",
                "p95_ms": f"{np.percentile(arr, 95):.1f}",
                "mean_ms": f"{arr.mean():.1f}",
            })

    env = {
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "processor": platform.processor() or "unknown",
        "python_version": platform.python_version(),
        "opencv_version": cv2.__version__,
        "cv2_threads": cv2.getNumThreads(),
        "method": ("interleaved round-robin across splits, "
                   f"{args.warmup} warm-up calls discarded, median of per-pair perf_counter"),
    }

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["split", "config", "n", "p50_ms", "p95_ms",
                                                "mean_ms"])
        writer.writeheader()
        writer.writerows(out_rows)
        fh.write("\n")
        for key, value in env.items():
            fh.write(f"# {key},{value}\n")

    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}")
    print(f"  {env['platform']} · Python {env['python_version']} · OpenCV {env['opencv_version']} "
          f"· {env['cv2_threads']} thread(s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
