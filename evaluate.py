#!/usr/bin/env python3
"""Score predictions against ground truth and emit the metrics the problem statement requires.

    python evaluate.py --manifest data/bench/manifest.csv \
                       --predictions results/predictions.csv --out results/

Reports (docs/SPEC.md section 5):
  * Euclidean localization error: mean, median, worst case, p95
  * Pass rates at 5, 4, 2 and 1 px, plus sub-pixel
  * Runtime per pair, with hardware, Python version and timing method recorded
  * Results stratified across noise, scale, rotation, position and architecture
  * The MIS-LOCK RATE, reported separately

That last one is not in the spec, and it is the number that matters most here. On this problem the
error distribution is bimodal: a correctly-located pair is off by ~1 px, a mis-located one by tens
or hundreds. Any headline average smears those two regimes together and hides the failure mode the
problem is actually about (R9). The sponsor's own baseline has a 1.10 px median and a 25% mis-lock
rate - quoting only the median would be technically true and deeply misleading.
"""

from __future__ import annotations

import argparse
import csv
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.driftlock.io import read_manifest  # noqa: E402

# The spec asks for these thresholds explicitly.
THRESHOLDS_PX = (5.0, 4.0, 2.0, 1.0)
SUBPIXEL_PX = 0.5
# Beyond this a result is not "inaccurate", it is a different location entirely.
MISLOCK_PX = 5.0


@dataclass
class Row:
    pair_id: str
    error: float
    runtime_ms: float | None
    meta: dict[str, str]


def load_rows(manifest_path: Path, predictions_path: Path) -> list[Row]:
    truth = {str(r.get("id", i)): r for i, r in enumerate(read_manifest(manifest_path))}

    rows: list[Row] = []
    with predictions_path.open(newline="", encoding="utf-8") as fh:
        for pred in csv.DictReader(fh):
            pair_id = str(pred["id"])
            if pair_id not in truth:
                continue
            t = truth[pair_id]
            dx = float(pred["pred_x"]) - float(t["gt_x"])
            dy = float(pred["pred_y"]) - float(t["gt_y"])
            runtime = pred.get("runtime_ms") or ""
            rows.append(Row(
                pair_id=pair_id,
                error=float(np.hypot(dx, dy)),
                runtime_ms=float(runtime) if runtime else None,
                meta=t,
            ))
    return rows


def summarise(rows: list[Row]) -> dict[str, float]:
    errors = np.array([r.error for r in rows])
    runtimes = np.array([r.runtime_ms for r in rows if r.runtime_ms is not None])

    stats: dict[str, float] = {
        "n_pairs": float(len(errors)),
        "error_mean_px": float(errors.mean()),
        "error_median_px": float(np.median(errors)),
        "error_p95_px": float(np.percentile(errors, 95)),
        "error_worst_px": float(errors.max()),
        "mislock_rate": float((errors > MISLOCK_PX).mean()),
        "n_mislocks": float((errors > MISLOCK_PX).sum()),
    }
    for t in THRESHOLDS_PX:
        stats[f"pass@{t:g}px"] = float((errors <= t).mean())
    stats[f"pass@subpixel({SUBPIXEL_PX:g}px)"] = float((errors <= SUBPIXEL_PX).mean())

    # Accuracy among correctly-located pairs only. Reported alongside, never instead of, the
    # overall figures: it answers "how precise is it when it works" without hiding how often
    # it does not.
    located = errors[errors <= MISLOCK_PX]
    if located.size:
        stats["error_median_px_located_only"] = float(np.median(located))
        stats["error_mean_px_located_only"] = float(located.mean())

    if runtimes.size:
        stats["runtime_p50_ms"] = float(np.percentile(runtimes, 50))
        stats["runtime_p95_ms"] = float(np.percentile(runtimes, 95))
        stats["runtime_mean_ms"] = float(runtimes.mean())
    return stats


def stratify(rows: list[Row], key: str, bins: int = 4) -> list[tuple[str, dict[str, float]]]:
    """Group results by a manifest column so weaknesses are visible instead of averaged away."""
    values = []
    for r in rows:
        raw = r.meta.get(key)
        if raw is None or raw == "":
            return []
        values.append(raw)

    try:
        numeric = np.array([float(v) for v in values])
        if len(np.unique(numeric)) > bins:
            edges = np.percentile(numeric, np.linspace(0, 100, bins + 1))
            labels = []
            for v in numeric:
                idx = int(np.clip(np.searchsorted(edges, v, side="right") - 1, 0, bins - 1))
                labels.append(f"{edges[idx]:.3g}..{edges[idx + 1]:.3g}")
        else:
            labels = [f"{v:g}" for v in numeric]
    except ValueError:
        labels = values

    groups: dict[str, list[Row]] = {}
    for label, row in zip(labels, rows):
        groups.setdefault(label, []).append(row)
    return [(label, summarise(g)) for label, g in sorted(groups.items()) if g]


def environment() -> dict[str, str]:
    """The spec requires runtime to be reported WITH hardware, Python version and timing method."""
    try:
        import cv2
        cv_version = cv2.__version__
    except ImportError:
        cv_version = "n/a"
    return {
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "processor": platform.processor() or "unknown",
        "opencv_version": cv_version,
        "timing_method": "time.perf_counter() around load+localize, per pair, single-threaded",
    }


def write_metrics_csv(path: Path, stats: dict[str, float], env: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for k, v in stats.items():
            writer.writerow([k, f"{v:.6g}"])
        for k, v in env.items():
            writer.writerow([k, v])


def write_report(path: Path, stats: dict[str, float], env: dict[str, str],
                 strata: dict[str, list[tuple[str, dict[str, float]]]]) -> None:
    lines = ["# Evaluation report", ""]
    lines.append(f"Pairs evaluated: **{int(stats['n_pairs'])}**")
    lines.append("")

    lines += ["## Headline", "", "| Metric | Value |", "|---|---|"]
    lines.append(f"| Mis-lock rate (>{MISLOCK_PX:g} px) | **{stats['mislock_rate'] * 100:.1f}%** "
                 f"({int(stats['n_mislocks'])} pairs) |")
    lines.append(f"| Median error | {stats['error_median_px']:.3f} px |")
    lines.append(f"| Mean error | {stats['error_mean_px']:.3f} px |")
    lines.append(f"| p95 error | {stats['error_p95_px']:.3f} px |")
    lines.append(f"| Worst-case error | {stats['error_worst_px']:.2f} px |")
    if "error_median_px_located_only" in stats:
        lines.append(f"| Median error, correctly-located pairs only | "
                     f"{stats['error_median_px_located_only']:.3f} px |")
    lines.append("")
    lines.append("> The error distribution is bimodal: a correctly-located pair is off by about a "
                 "pixel, a mis-located one by tens or hundreds. The mis-lock rate is therefore "
                 "reported separately - a single average would hide the failure mode this problem "
                 "is about.")
    lines.append("")

    lines += ["## Threshold-wise pass rates", "", "| Threshold | Pass rate |", "|---|---|"]
    for t in THRESHOLDS_PX:
        lines.append(f"| {t:g} px | {stats[f'pass@{t:g}px'] * 100:.1f}% |")
    lines.append(f"| sub-pixel ({SUBPIXEL_PX:g} px) | "
                 f"{stats[f'pass@subpixel({SUBPIXEL_PX:g}px)'] * 100:.1f}% |")
    lines.append("")

    if "runtime_p50_ms" in stats:
        lines += ["## Runtime", "", "| Metric | Value |", "|---|---|"]
        lines.append(f"| Median (p50) | {stats['runtime_p50_ms']:.1f} ms |")
        lines.append(f"| p95 | {stats['runtime_p95_ms']:.1f} ms |")
        lines.append(f"| Mean | {stats['runtime_mean_ms']:.1f} ms |")
        lines.append("")

    lines += ["## Environment", "", "| Field | Value |", "|---|---|"]
    for k, v in env.items():
        lines.append(f"| {k.replace('_', ' ')} | {v} |")
    lines.append("")

    for key, groups in strata.items():
        if not groups or len(groups) < 2:
            continue
        lines += [f"## Stratified by `{key}`", "",
                  "| Group | n | Median err (px) | Mis-lock rate | Pass@1px |", "|---|---|---|---|---|"]
        for label, s in groups:
            lines.append(f"| {label} | {int(s['n_pairs'])} | {s['error_median_px']:.3f} | "
                         f"{s['mislock_rate'] * 100:.0f}% | {s['pass@1px'] * 100:.0f}% |")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--manifest", required=True, help="ground-truth manifest CSV")
    parser.add_argument("--predictions", required=True, help="predictions CSV from localize.py")
    parser.add_argument("--out", default="results", help="output directory")
    parser.add_argument("--label", default="", help="name for this run, used in filenames")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.manifest), Path(args.predictions))
    if not rows:
        print("error: no rows matched between manifest and predictions", file=sys.stderr)
        return 1

    stats = summarise(rows)
    env = environment()

    strata = {}
    for key in ("architecture", "dose_search", "scale_ratio", "rotation_deg",
                "ambiguity_level", "gt_x", "gt_y"):
        groups = stratify(rows, key)
        if groups:
            strata[key] = groups

    out = Path(args.out)
    suffix = f"_{args.label}" if args.label else ""
    write_metrics_csv(out / f"metrics{suffix}.csv", stats, env)
    write_report(out / f"report{suffix}.md", stats, env, strata)

    print(f"\n  Pairs: {int(stats['n_pairs'])}")
    print(f"  Mis-lock rate (>{MISLOCK_PX:g} px): {stats['mislock_rate'] * 100:.1f}% "
          f"({int(stats['n_mislocks'])} pairs)")
    print(f"  Median error: {stats['error_median_px']:.3f} px   "
          f"mean {stats['error_mean_px']:.3f}   worst {stats['error_worst_px']:.2f}")
    print("  Pass rates: " + "  ".join(
        f"@{t:g}px {stats[f'pass@{t:g}px'] * 100:.0f}%" for t in THRESHOLDS_PX))
    if "runtime_p50_ms" in stats:
        print(f"  Runtime: p50 {stats['runtime_p50_ms']:.1f} ms, p95 {stats['runtime_p95_ms']:.1f} ms")
    print(f"\n  Wrote {(out / f'metrics{suffix}.csv').as_posix()} and "
          f"{(out / f'report{suffix}.md').as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
