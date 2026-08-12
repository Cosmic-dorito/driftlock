#!/usr/bin/env python3
"""Measure the failure case and the ambiguity stratification for the CURRENT pipeline.

    python scripts/failure_analysis.py --manifest data/bench/manifest.csv

Writes results/failure_case/analysis.csv, which the deck reads. These numbers were previously
hardcoded into the slide from an earlier pipeline; after the per-candidate refit landed they were
silently stale - the split no longer had the same number of failures, let alone the same worst pair.
Deriving them from a run is the only way rule R2 actually binds.
"""

from __future__ import annotations

import argparse
import csv
import sys
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
from src.driftlock.match import (  # noqa: E402
    _preprocess,
    _resolve_poses,
    build_template,
    correlation_surface,
    extract_peaks,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="data/bench/manifest.csv")
    ap.add_argument("--predictions", default="results/predictions_bench.csv")
    ap.add_argument("--out", default="results/failure_case")
    ap.add_argument("--top-k", type=int, default=20)
    args = ap.parse_args()

    manifest = Path(args.manifest)
    rows = read_manifest(manifest)
    with Path(args.predictions).open(newline="", encoding="utf-8") as fh:
        preds = {r["id"]: r for r in csv.DictReader(fh)}

    cfg = L.build_config(argparse.Namespace(config="driftlock"))

    records = []
    for row in rows:
        pred = preds.get(row["id"])
        if pred is None:
            continue
        gt = (float(row["gt_x"]), float(row["gt_y"]))
        err = euclidean_error((float(pred["pred_x"]), float(pred["pred_y"])), gt)
        records.append({
            "id": row["id"], "err": err, "gt": gt,
            "ambiguity": row.get("ambiguity_level", "unknown"),
            "row": row,
        })

    n = len(records)
    failures = [r for r in records if r["err"] > 5.0]
    worst = max(records, key=lambda r: r["err"])

    # --- candidate recall and the worst pair's ranking, under the CURRENT pipeline ---
    recall_hits = 0
    worst_rank = None
    worst_margin = None
    worst_top = None
    for rec in records:
        row = rec["row"]
        ref = load_grayscale(resolve_manifest_path(manifest, row["reference_path"]))
        search = load_grayscale(resolve_manifest_path(manifest, row["search_path"]))
        rp, sp = _preprocess(ref, search, cfg)
        poses, _, _ = _resolve_poses(rp, sp, cfg)

        best = None
        for scale, rotation in poses:
            template = build_template(rp, scale, rotation)
            if template.shape[0] >= sp.shape[0] or template.shape[1] >= sp.shape[1]:
                continue
            cands = extract_peaks(correlation_surface(sp, template), template.shape,
                                  args.top_k, cfg.nms_radius_px, scale, rotation)
            if cands and (best is None or cands[0].score > best[0].score):
                best = cands
        if not best:
            continue

        gx, gy = rec["gt"]
        hit = [i for i, c in enumerate(best) if np.hypot(c.x - gx, c.y - gy) <= 5.0]
        if hit:
            recall_hits += 1
        if rec["id"] == worst["id"]:
            worst_top = best[0]
            if hit:
                worst_rank = hit[0] + 1
                worst_margin = best[0].score - best[hit[0]].score

    # --- stratification by the generator's own ambiguity label ---
    strata = {}
    for rec in records:
        s = strata.setdefault(rec["ambiguity"], {"n": 0, "fail": 0, "p1": 0})
        s["n"] += 1
        s["fail"] += rec["err"] > 5.0
        s["p1"] += rec["err"] <= 1.0

    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "analysis.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["split", manifest.parent.name])
        w.writerow(["n_pairs", n])
        w.writerow(["n_failures", len(failures)])
        w.writerow(["worst_id", worst["id"]])
        w.writerow(["worst_error_px", f"{worst['err']:.2f}"])
        w.writerow(["worst_ambiguity", worst["ambiguity"]])
        w.writerow(["worst_rank_of_truth", worst_rank if worst_rank else "not in top-K"])
        if worst_margin is not None:
            w.writerow(["worst_margin_zncc", f"{worst_margin:.4f}"])
            w.writerow(["worst_margin_pct", f"{100 * worst_margin / worst_top.score:.2f}"])
        w.writerow(["candidate_recall_topk", f"{recall_hits}/{n}"])
        w.writerow(["candidate_recall_pct", f"{100 * recall_hits / n:.1f}"])
        w.writerow(["top_k", args.top_k])
        for name, s in sorted(strata.items()):
            w.writerow([f"strata_{name}_n", s["n"]])
            w.writerow([f"strata_{name}_mislock_pct", f"{100 * s['fail'] / s['n']:.0f}"])
            w.writerow([f"strata_{name}_pass1_pct", f"{100 * s['p1'] / s['n']:.0f}"])
            w.writerow([f"strata_{name}_failures", s["fail"]])

    print(f"\n  split {manifest.parent.name}: {n} pairs, {len(failures)} failures")
    print(f"  worst: id={worst['id']} err={worst['err']:.2f} px "
          f"ambiguity={worst['ambiguity']} rank-of-truth={worst_rank}")
    if worst_margin is not None:
        print(f"  the truth lost by {worst_margin:.4f} ZNCC "
              f"({100 * worst_margin / worst_top.score:.2f}% of the winning score)")
    print(f"  candidate recall @top-{args.top_k}: {recall_hits}/{n} "
          f"= {100 * recall_hits / n:.1f}%")
    for name, s in sorted(strata.items()):
        print(f"  strata {name:<8} n={s['n']:<3} mis-lock {100 * s['fail'] / s['n']:>3.0f}%  "
              f"@1px {100 * s['p1'] / s['n']:>3.0f}%  ({s['fail']} failures)")
    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
