#!/usr/bin/env python3
"""Measure how far each POST-SELECTION stage moves the answer, and whether that ever loses a pair.

    python scripts/refine_forensics.py

The failure decomposition splits a mis-lock into ABSENT / SCREENED / OUTSCORED - three ways of
picking the wrong candidate. It has no bucket for picking the *right* candidate and then moving off
it, because until `refine_shift_px` was added to the mechanism file there was no evidence that
happened. It does: `bench 21` selects a candidate 1.07 px from ground truth and reports 6.54 px,
so the selection was correct and something after it moved the answer 7.57 px.

Three stages run after a candidate is committed to:

    pose_refine   `_refine_pose_local`  - polishes the measured pose
    subpixel      `subpixel.refine`     - upsampled-DFT peak location
    drift         `estimate_and_correct`- inverts raster drift, x only, deliberately last

This records the position after each one, for every pair, so the distribution of movement on
CORRECT pairs is visible next to the movement on failures. That ordering matters: a guard is only
well-posed if refinement normally moves a fraction of a pixel. If it routinely moves several,
there is nothing to guard.

`dev` and `dev2` are the tuning family and are reported here FIRST and separately, so any threshold
this motivates is derived off the reporting splits (rule R5).
"""

from __future__ import annotations

import csv
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import localize as L  # noqa: E402
import src.driftlock.drift as drift_module  # noqa: E402
import src.driftlock.match as match_module  # noqa: E402
import src.driftlock.subpixel as subpixel_module  # noqa: E402
from src.driftlock.io import (  # noqa: E402
    euclidean_error,
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)

MISLOCK_PX = 5.0

#: Tuning family first, then the three reporting splits. Any threshold read off this table must
#: come from the first two rows only.
SPLITS = [("dev", "data/dev"), ("dev2", "data/dev2"),
          ("sponsor", "data/_sponsor/verify"), ("bench", "data/bench"),
          ("finfet", "data/holdout_finfet"),
          # The regime the guard could HURT in: true shear is still 1.5 px, but heavy jitter makes
          # the ESTIMATE noisy, so a legitimately large reading is most likely here (rule 3 -
          # evaluate a stage in the regime it targets, and in the regime it endangers).
          ("jitter1.5", "data/_stress/jitter15"), ("jitter3.0", "data/_stress/jitter3")]
TUNING = {"dev", "dev2"}

TRACE: dict = {}

_orig_pose_local = match_module._refine_pose_local
_orig_subpixel = subpixel_module.refine
_orig_drift = drift_module.estimate_and_correct


def _traced_pose_local(ref, search, chosen, config):
    TRACE["selected"] = (float(chosen.x), float(chosen.y))
    out = _orig_pose_local(ref, search, chosen, config)
    TRACE["after_pose_refine"] = (float(out.x), float(out.y))
    return out


def _traced_subpixel(search, reference, candidate, **kwargs):
    # pose_refine may be disabled, so this is also the fallback point for the selected position.
    TRACE.setdefault("selected", (float(candidate.x), float(candidate.y)))
    TRACE.setdefault("after_pose_refine", (float(candidate.x), float(candidate.y)))
    out = _orig_subpixel(search, reference, candidate, **kwargs)
    TRACE["after_subpixel"] = (float(out.x), float(out.y))
    return out


def _traced_drift(search, x, y, **kwargs):
    TRACE.setdefault("selected", (float(x), float(y)))
    TRACE.setdefault("after_pose_refine", (float(x), float(y)))
    TRACE.setdefault("after_subpixel", (float(x), float(y)))
    out = _orig_drift(search, x, y, **kwargs)
    TRACE["after_drift"] = (float(out[0]), float(y))
    # Record the shear so a guard threshold can be simulated exactly rather than by re-running.
    # This stage is TERMINAL - nothing in localize() runs after it - so rejecting the correction
    # can only ever restore the pre-drift coordinate, which is already captured above. That makes
    # the simulation exact rather than a proxy. It is still confirmed by a real run before shipping.
    TRACE["shear"] = None if out[1] is None else float(out[1])
    return out


match_module._refine_pose_local = _traced_pose_local
subpixel_module.refine = _traced_subpixel
drift_module.estimate_and_correct = _traced_drift


def _dist(a, b) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def main() -> int:
    import argparse as _ap
    cfg = L.build_config(_ap.Namespace(config="driftlock"))
    # Measure the UNGUARDED pipeline whatever the shipped default is. With the guard active a
    # rejected estimate is reported as None, which would erase the very values this script exists
    # to characterise - and would make the table silently self-fulfilling once ADR-0036 shipped.
    guard_shipped = cfg.drift_max_shear_px
    cfg = replace(cfg, drift_max_shear_px=0.0)

    rows = []
    print(f"\n  {'split':<9}{'n':>4}{'sel err>5':>11}{'final err>5':>13}"
          f"{'med shift':>11}{'p95 shift':>11}{'max shift':>11}{'lost by refine':>16}")
    print("  " + "-" * 78)

    for name, folder in SPLITS:
        manifest = REPO_ROOT / folder / "manifest.csv"
        shifts, sel_bad, fin_bad, lost = [], 0, 0, 0
        for row in read_manifest(manifest):
            gt = (float(row["gt_x"]), float(row["gt_y"]))
            TRACE.clear()
            match = match_module.localize(
                load_grayscale(resolve_manifest_path(manifest, row["reference_path"])),
                load_grayscale(resolve_manifest_path(manifest, row["search_path"])),
                cfg)

            selected = TRACE.get("selected")
            if selected is None:            # no post-selection stage ran at all
                continue
            final = (float(match.x), float(match.y))
            sel_err = euclidean_error(selected, gt)
            fin_err = euclidean_error(final, gt)
            shift = _dist(selected, final)
            shifts.append(shift)
            sel_bad += sel_err > MISLOCK_PX
            fin_bad += fin_err > MISLOCK_PX
            # The bucket with no name: selection was right, the reported answer is not.
            lost += (sel_err <= MISLOCK_PX) and (fin_err > MISLOCK_PX)

            after_pr = TRACE.get("after_pose_refine", selected)
            after_sp = TRACE.get("after_subpixel", after_pr)
            after_dr = TRACE.get("after_drift", after_sp)
            rows.append({
                "split": name, "id": row["id"],
                "sel_err_px": f"{sel_err:.4f}", "final_err_px": f"{fin_err:.4f}",
                "shift_total_px": f"{shift:.4f}",
                "shift_pose_refine_px": f"{_dist(selected, after_pr):.4f}",
                "shift_subpixel_px": f"{_dist(after_pr, after_sp):.4f}",
                "shift_drift_px": f"{_dist(after_sp, after_dr):.4f}",
                "shear_px": ("" if TRACE.get("shear") is None else f"{TRACE['shear']:.4f}"),
                "predrift_err_px": f"{euclidean_error(after_sp, gt):.4f}",
                "lost_by_refinement": int((sel_err <= MISLOCK_PX) and (fin_err > MISLOCK_PX)),
            })

        arr = np.array(shifts) if shifts else np.array([0.0])
        tag = "  <- tuning" if name in TUNING else ""
        print(f"  {name:<9}{len(shifts):>4}{sel_bad:>11}{fin_bad:>13}"
              f"{np.median(arr):>11.3f}{np.percentile(arr, 95):>11.3f}"
              f"{arr.max():>11.3f}{lost:>16}{tag}")

    # --- Guard simulation -------------------------------------------------------------------
    # Exact, not a proxy: the drift step is the last thing localize() does, so rejecting it can
    # only restore the pre-drift coordinate, which is recorded above. Confirmed against a real
    # pipeline run before ADR-0036 shipped.
    def simulate(subset, thr):
        mis = 0
        for r in subset:
            rejected = thr > 0 and r["shear_px"] != "" and abs(float(r["shear_px"])) > thr
            err = float(r["predrift_err_px"] if rejected else r["final_err_px"])
            mis += err > MISLOCK_PX
        return mis

    legit = [abs(float(r["shear_px"])) for r in rows
             if r["shear_px"] != "" and float(r["final_err_px"]) <= MISLOCK_PX]
    broken = sorted(abs(float(r["shear_px"])) for r in rows
                    if r["shear_px"] != "" and int(r["lost_by_refinement"]) == 1)
    print(f"  |shear| on pairs that are correct today : max {max(legit):.3f} px  (n={len(legit)})")
    print("  |shear| on pairs lost by refinement      : "
          + ", ".join(f"{v:.3f}" for v in broken) + " px")
    print(f"  shipped guard: {guard_shipped:.1f} px\n")

    print(f"  {'guard':>7}{'dev+dev2':>10}{'reporting':>11}{'jitter1.5':>11}{'jitter3.0':>11}")
    print("  " + "-" * 50)
    groups = {"tune": [r for r in rows if r["split"] in TUNING],
              "rep": [r for r in rows if r["split"] in {"sponsor", "bench", "finfet"}],
              "j15": [r for r in rows if r["split"] == "jitter1.5"],
              "j30": [r for r in rows if r["split"] == "jitter3.0"]}
    for thr in (0.0, 3.0, 4.0, 6.0, 8.0, 12.0, 20.0):
        label = "off" if thr == 0 else f"{thr:.0f} px"
        cells = "".join(f"{simulate(g, thr):>11}" for g in groups.values())
        print(f"  {label:>7}{cells}")
    print("  (cells are mis-lock COUNTS; 'off' is the pre-guard pipeline)\n")

    out = REPO_ROOT / "results" / "refine_forensics.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        fh.write("\n# shift_* are Euclidean movement in search-image px, stage by stage.\n")
        fh.write("# lost_by_refinement: selection was within 5 px of GT, the reported answer"
                 " was not.\n")
        fh.write("# dev and dev2 are the tuning family - any threshold must be read off those.\n")
    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
