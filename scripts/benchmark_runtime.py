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

# The baseline's p50 on a quiet machine, measured repeatedly. It is a fixed, simple computation,
# so its runtime is a proxy for how fast this machine currently is - which makes it a control.
BASELINE_QUIET_MS = 22.0

# p95/p50 of the DriftLock timings on a steady machine. Measured at 1.10 in steady state and
# 1.28 on the first heavy run after idle, which the baseline control could not distinguish.
MAX_P95_RATIO = 1.18

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

    # The ratio divides by the baseline median over the WHOLE run, not each split's own.
    #
    # Per-split denominators looked natural and were wrong: the baseline does essentially identical
    # work on every split, so its per-split medians differ only by noise, and dividing by a noisy
    # denominator injects that noise into the ratio it was supposed to remove. Measured on a
    # recovering machine, per-split ratios read 13.5 / 25.4 / 22.7 for three splits whose true cost
    # is the same to within a few percent - which would have appeared in the table as sponsor being
    # twice as fast as bench. Pooling the denominator uses all 36 baseline samples instead of 12.
    all_base_values = [v for per in timings.values() for v in per.get("baseline", [])]
    pooled_base = float(np.median(all_base_values)) if all_base_values else float("nan")

    print(f"\n  {'split':<12}{'config':<12}{'p50 ms':>9}{'p95 ms':>9}{'n':>5}{'x base':>8}")
    out_rows = []
    for name, per_config in timings.items():
        base_p50 = pooled_base
        for label, values in per_config.items():
            if not values:
                continue
            arr = np.array(values)
            ratio = np.median(arr) / base_p50 if base_p50 == base_p50 and base_p50 > 0 else float("nan")
            print(f"  {name:<12}{label:<12}{np.median(arr):>9.0f}{np.percentile(arr, 95):>9.0f}"
                  f"{len(arr):>5}{ratio:>8.1f}")
            out_rows.append({
                "split": name, "config": label, "n": len(arr),
                "p50_ms": f"{np.median(arr):.1f}",
                "p95_ms": f"{np.percentile(arr, 95):.1f}",
                "mean_ms": f"{arr.mean():.1f}",
                "x_baseline": f"{ratio:.2f}",
            })

    # The baseline is a CONTROL, and reporting it alongside is not decoration.
    #
    # This machine thermally throttles after a long session and does not recover on idling - a
    # documented 3x drift for identical code (FINDINGS 19). Measured across three machine states in
    # one day, the absolute numbers moved 20 -> 34 -> 67 ms for the baseline and 400 -> 630 -> 1262
    # for ours, while the RATIO held at 20.0, 18.5, 18.8. The ratio is the machine-independent
    # quantity; the milliseconds are a property of this laptop's thermal state at one moment.
    #
    # So the absolute figure is only quotable when the control is near its own best, and this gate
    # says so out loud rather than letting a throttled number be written into results/ and then
    # into the deck.
    base_median = pooled_base

    # SECOND gate, because the baseline control has a blind spot it cannot see past.
    #
    # The baseline runs for ~19 ms. A DriftLock call runs for ~400. A short task can complete
    # entirely inside the CPU's boost window while a long one drops into the sustained-clock regime,
    # so the control can read perfectly normal while the thing being measured is not. That is not
    # hypothetical: on a genuinely cold machine the first run gave baseline 20-24 ms (a clean pass)
    # with DriftLock at 577-629 ms, and an immediate second run in steady state gave the same
    # baseline with DriftLock at 388-406 ms. The control passed both times; the measurement moved
    # by 1.6x. Counter-intuitively the FIRST heavy run after idle is the unreliable one.
    #
    # What did separate them was the dispersion of the measurement itself: p95/p50 was 1.28 in the
    # bad run and 1.10 in the good one. A steady machine produces a tight distribution regardless of
    # its absolute speed, so this catches instability the baseline structurally cannot.
    drift_values = [v for per in timings.values() for v in per.get("driftlock", [])]
    spread = (float(np.percentile(drift_values, 95)) / float(np.median(drift_values))
              if drift_values else 1.0)
    unstable = spread > MAX_P95_RATIO

    suspect = base_median > BASELINE_QUIET_MS * 1.5 or unstable
    if unstable and base_median <= BASELINE_QUIET_MS * 1.5:
        print(f"\n  ** WARNING: baseline control is normal ({base_median:.0f} ms) but the measured "
              f"distribution is not:")
        print(f"     p95/p50 = {spread:.2f} against a steady-machine {MAX_P95_RATIO:.2f}. The first "
              "heavy run after idle does this.")
        print("     Re-run; a second pass in steady state is usually the trustworthy one.")
    if suspect:
        print(f"\n  ** WARNING: baseline control at {base_median:.0f} ms against a quiet-machine "
              f"{BASELINE_QUIET_MS:.0f} ms.")
        print("     The machine is throttled or loaded; the absolute milliseconds below are NOT "
              "representative.")
        print("     The x-baseline column is unaffected. Re-run when the control returns to "
              "normal before quoting p50.")

    env = {
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "processor": platform.processor() or "unknown",
        "python_version": platform.python_version(),
        "opencv_version": cv2.__version__,
        "cv2_threads": cv2.getNumThreads(),
        "method": ("interleaved round-robin across splits, "
                   f"{args.warmup} warm-up calls discarded, median of per-pair perf_counter"),
        "baseline_control_ms": f"{base_median:.1f}",
        "p95_over_p50": f"{spread:.3f}",
        "absolute_ms_representative": "no - machine throttled or unstable" if suspect else "yes",
    }

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["split", "config", "n", "p50_ms", "p95_ms",
                                                "mean_ms", "x_baseline"])
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
