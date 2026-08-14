#!/usr/bin/env python3
"""How much of our own reported difference is real? Confidence intervals and a paired test.

    python scripts/significance.py

Why this exists. Every headline in this project is a proportion measured on 30-40 pairs, and we have
been quoting differences of 2-4 points as though they were resolved. Two facts force this analysis:

1. **The stress sweep accidentally ran the nominal configuration twice.** `s02` and `s06` draw from
   an identical generator parameter set and differ only in seed. They measured **20.0%** and
   **33.3%** mis-lock. That is 13 points of pure sampling noise between two samples of the same
   distribution, and it is a hard floor on how finely any single split can be read.

2. **Marginal and paired comparisons are not the same question,** and confusing them cuts both ways.
   Comparing two configurations by their overall rates throws away the fact that they ran on the
   *same pairs*. A paired test is far more powerful - and here it is also far more favourable, so
   reporting only the overlapping marginal intervals would have understated our own result.

Wilson intervals rather than normal-approximation ones: at n=30 and p near 0.15 the textbook
+/-1.96*sqrt(p(1-p)/n) interval extends below zero, which is not a probability.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from math import comb
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MISLOCK_PX = 5.0
SPLITS = {"sponsor": "data/_sponsor/verify",
          "bench": "data/bench",
          "finfet": "data/holdout_finfet"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact binomial p-value for the discordant pairs.

    The chi-square form is unreliable when b+c is small, and b+c is 4 here. The exact test asks:
    if each discordant pair were a coin flip, how surprising is this split?
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def load_gt(split: str) -> dict[str, tuple[float, float]]:
    path = REPO_ROOT / SPLITS[split] / "manifest.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["id"]: (float(r["gt_x"]), float(r["gt_y"])) for r in csv.DictReader(fh)}


def load_correct(path: Path, gt: dict) -> dict[str, bool]:
    """Per-pair pass/fail at the mis-lock threshold."""
    out: dict[str, bool] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["id"] in gt:
                gx, gy = gt[r["id"]]
                out[r["id"]] = math.hypot(float(r["pred_x"]) - gx,
                                          float(r["pred_y"]) - gy) <= MISLOCK_PX
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline-predictions", default=None,
                    help="predictions from the configuration to compare against, as "
                         "SPLIT=PATH pairs; enables the paired test")
    ap.add_argument("--out", default="results/significance.csv")
    args = ap.parse_args()

    rows = []
    total_k = total_n = 0
    print(f"\n  {'split':<10}{'mis-lock':>10}{'k/n':>9}{'Wilson 95% CI':>22}")
    print("  " + "-" * 51)
    for split in SPLITS:
        gt = load_gt(split)
        correct = load_correct(REPO_ROOT / "results" / f"predictions_{split}.csv", gt)
        if not correct:
            continue
        n = len(correct)
        k = sum(1 for v in correct.values() if not v)
        lo, hi = wilson(k, n)
        total_k += k
        total_n += n
        rows.append({"scope": split, "mislock_k": k, "n": n,
                     "mislock_rate": f"{k / n:.4f}",
                     "ci95_low": f"{lo:.4f}", "ci95_high": f"{hi:.4f}"})
        print(f"  {split:<10}{k / n * 100:>9.1f}%{f'{k}/{n}':>9}"
              f"{f'[{lo * 100:.1f}%, {hi * 100:.1f}%]':>22}")

    if total_n:
        lo, hi = wilson(total_k, total_n)
        rows.append({"scope": "aggregate", "mislock_k": total_k, "n": total_n,
                     "mislock_rate": f"{total_k / total_n:.4f}",
                     "ci95_low": f"{lo:.4f}", "ci95_high": f"{hi:.4f}"})
        print(f"  {'AGGREGATE':<10}{total_k / total_n * 100:>9.1f}%"
              f"{f'{total_k}/{total_n}':>9}{f'[{lo * 100:.1f}%, {hi * 100:.1f}%]':>22}")

    if args.baseline_predictions:
        mapping = dict(p.split("=", 1) for p in args.baseline_predictions.split(","))
        b = c = both_ok = both_bad = 0
        for split, path in mapping.items():
            gt = load_gt(split)
            other = load_correct(Path(path), gt)
            ours = load_correct(REPO_ROOT / "results" / f"predictions_{split}.csv", gt)
            for key in ours:
                if key not in other:
                    continue
                if other[key] and ours[key]:
                    both_ok += 1
                elif other[key] and not ours[key]:
                    b += 1
                elif ours[key] and not other[key]:
                    c += 1
                else:
                    both_bad += 1
        p_exact = exact_mcnemar(b, c)
        n_paired = both_ok + both_bad + b + c
        print(f"\n  PAIRED comparison on the same {n_paired} pairs")
        print(f"    baseline-only correct  b = {b}")
        print(f"    ours-only correct      c = {c}")
        print(f"    both correct {both_ok}, both wrong {both_bad}")
        print(f"    exact McNemar two-sided p = {p_exact:.3f}")
        verdict = ("strictly dominant (no regressions)" if b == 0 and c > 0
                   else "mixed" if b and c else "no discordant pairs")
        print(f"    verdict: {verdict}, {c - b:+d} pairs net")
        rows.append({"scope": "paired_vs_baseline", "mislock_k": b, "n": n_paired,
                     "mislock_rate": f"{c}", "ci95_low": f"{p_exact:.4f}",
                     "ci95_high": verdict})

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["scope", "mislock_k", "n", "mislock_rate",
                                                "ci95_low", "ci95_high"])
        writer.writeheader()
        writer.writerows(rows)
        fh.write("\n# Wilson score intervals; normal-approximation intervals go negative at n=30.\n")
        fh.write("# For scope=paired_vs_baseline: mislock_k=b, mislock_rate=c, ci95_low=exact p.\n")
        fh.write("# Two parameter-identical stress splits differing only by seed measured 20.0%\n")
        fh.write("# and 33.3% at n=30 - the sampling floor for reading any single split.\n")
    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
