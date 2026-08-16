"""Independent re-derivation of the headline metrics straight from the raw CSVs.

Why this exists as a separate script: `evaluate.py` both computes the metrics and writes
them, so re-running it can only ever confirm itself. This module imports **nothing** from
`src/` or `evaluate.py` -- plain `csv` and `math` -- so a defect in the project's own metric
code cannot reproduce itself here. It reads `predictions_*.csv` and the manifests and
recomputes mis-lock, median error, pass rates and the paired-vs-baseline counts from scratch.

Rule 8 in docs/STATE.md: a result with no script is not a result. This is the script behind
the claim "the headline numbers were independently re-derived".

    python scripts/audit_results.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (label, manifest, shipped predictions, baseline predictions) -- the three reporting splits.
SPLITS: list[tuple[str, str, str, str]] = [
    ("sponsor", "data/_sponsor/verify/manifest.csv",
     "results/predictions_sponsor.csv", "results/predictions_sponsor_baseline.csv"),
    ("bench", "data/bench/manifest.csv",
     "results/predictions_bench.csv", "results/predictions_bench_baseline.csv"),
    ("finfet", "data/holdout_finfet/manifest.csv",
     "results/predictions_finfet.csv", "results/predictions_finfet_baseline.csv"),
]

MISLOCK_PX = 5.0


def _load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh)
                if r.get("id", "").strip() and not r["id"].lstrip().startswith("#")]


def _errors(manifest: Path, predictions: Path) -> dict[str, float]:
    """Euclidean error per id, in search-image pixels."""
    truth = {r["id"]: (float(r["gt_x"]), float(r["gt_y"])) for r in _load(manifest)}
    out = {}
    for row in _load(predictions):
        gx, gy = truth[row["id"]]
        out[row["id"]] = math.hypot(float(row["pred_x"]) - gx, float(row["pred_y"]) - gy)
    return out


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2])


def _rate(k: int, n: int) -> float:
    return 100.0 * k / n if n else float("nan")


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial test on the discordant pairs of a paired comparison."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval -- the normal approximation goes negative at n=30."""
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - half) / denom, (centre + half) / denom)


def main() -> int:
    header = (f"{'split':10s} {'n':>4s} {'mis-lock':>9s} {'median':>8s} {'p@1px':>7s} "
              f"{'p@0.5px':>8s} | {'baseline':>9s} {'fixed':>6s} {'broke':>6s}")
    print(header)
    print("-" * len(header))

    total_n = total_mis = total_fixed = total_broke = 0
    for label, manifest, predictions, baseline in SPLITS:
        err = _errors(ROOT / manifest, ROOT / predictions)
        base = _errors(ROOT / manifest, ROOT / baseline)
        n = len(err)
        mis = sum(1 for e in err.values() if e > MISLOCK_PX)
        fixed = sum(1 for i in err if base[i] > MISLOCK_PX >= err[i])
        broke = sum(1 for i in err if err[i] > MISLOCK_PX >= base[i])
        base_mis = sum(1 for e in base.values() if e > MISLOCK_PX)

        total_n += n
        total_mis += mis
        total_fixed += fixed
        total_broke += broke

        print(f"{label:10s} {n:4d} {_rate(mis, n):8.1f}% {_median(list(err.values())):8.3f} "
              f"{_rate(sum(1 for e in err.values() if e <= 1.0), n):6.1f}% "
              f"{_rate(sum(1 for e in err.values() if e <= 0.5), n):7.1f}% | "
              f"{_rate(base_mis, n):8.1f}% {fixed:6d} {broke:6d}")

    print("-" * len(header))
    lo, hi = wilson(total_mis, total_n)
    print(f"AGGREGATE  {total_n:4d} {_rate(total_mis, total_n):8.1f}%   "
          f"({total_mis}/{total_n} mis-locks, Wilson 95% CI "
          f"[{100 * lo:.2f}%, {100 * hi:.2f}%])")
    print(f"vs baseline: fixed {total_fixed}, broke {total_broke}, "
          f"exact McNemar p = {mcnemar_exact(total_fixed, total_broke):.3g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
