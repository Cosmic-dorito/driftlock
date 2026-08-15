#!/usr/bin/env python3
"""Does correcting the scanner globally, before any candidate exists, actually help?

    python scripts/global_jitter.py --splits dev
    python scripts/global_jitter.py --splits sponsor,bench,finfet

The frozen pipeline is run twice per pair on the same images: once as shipped, once on a search
image that has had its per-row scan jitter measured and removed by ``src/driftlock/scanfield.py``.
Nothing else changes - same config, same candidates, same scoring - so any difference is caused by
the acquisition correction and by nothing else.

WHY THIS IS NOT THE EXPERIMENT THAT WAS ALREADY TRIED. FINDINGS 36c estimated a per-row offset from
each CANDIDATE's own patch, which hands every candidate its own deformation; two implementations of
that idea disagreed about the sign of the effect (37d), and the project's own evidence says extra
per-candidate freedom flows to whichever candidate has more mismatch to absorb. The field here is
measured once from the whole search image before any candidate is proposed, so it is the same
correction for the truth and for every impostor. It cannot express a preference.

WHAT IS BEING CORRECTED. The generator applies ``shear * y/(H-1) + jitter_y`` with jitter drawn per
row. On these splits that is a 1.5 px shear - 0.15 px across a 100 px footprint, and the drift stage
already removes its linear part - and a 0.5 px per-row jitter that is WHITE in y and that no smooth
model can reach. The reference carries its own jitter at 1 nm/px, which is 0.05 px after decimation.
So the search image's per-row jitter is the largest uncorrected geometric error in the pipeline.

Emits ``results/global_jitter.csv`` before anything is interpreted. Rule ADR-0030.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import localize as L  # noqa: E402
from src.driftlock.drift import correct_for_drift, estimate_drift_shear  # noqa: E402
from src.driftlock.io import (  # noqa: E402
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)
from src.driftlock.match import build_template, localize  # noqa: E402
from src.driftlock.scanfield import calibrate  # noqa: E402

NEAR_PX = 5.0
SPLITS = {
    "dev": "data/dev",
    "dev2": "data/dev2",
    "sponsor": "data/_sponsor/verify",
    "bench": "data/bench",
    "finfet": "data/holdout_finfet",
    # The regime this stage actually targets. Every reporting split is generated at the same
    # nominal 0.5 px jitter, so measuring a jitter corrector only there repeats the mistake that
    # kept the median filter switched off for three days on a "no effect" measured against data
    # with no impulse noise (ADR-0027). A stage is judged in the regime it was written for.
    #
    # jitter15 sits at the EDGE OF FEASIBILITY, and the edge is not a tuning choice. A per-row lag
    # search has to stay below half the lattice period or the row locks onto the neighbouring
    # repeat; the DRAM bit-line pitch is 96 nm = 9.6 px at 10:1, so half a period is ~4.8 px. At
    # sigma = 1.5 px that is 3 sigma of coverage; at sigma = 3.0 (jitter3) the displacements run
    # past it and the gates decline every pair. The correctable range is bounded by exactly the
    # periodicity that makes the localization problem hard in the first place.
    "jitter3": "data/_stress/jitter3",
    "jitter15": "data/_stress/jitter15",
}


def zncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / denom) if denom > 1e-9 else 0.0


def score_at(image: np.ndarray, template: np.ndarray, x: float, y: float) -> float | None:
    size = template.shape[0]
    y0, x0 = int(round(y - size / 2.0)), int(round(x - size / 2.0))
    if not (y0 >= 0 and y0 + size <= image.shape[0] and x0 >= 0 and x0 + size <= image.shape[1]):
        return None
    return zncc(template, image[y0:y0 + size, x0:x0 + size].astype(np.float32))


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar on the discordant pairs. The concordant ones carry no information."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = min(only_a, only_b)
    total = sum(math.comb(n, i) for i in range(tail + 1))
    return min(1.0, 2.0 * total / 2 ** n)


def write_summary(rows: list[dict], per_pair_path: Path) -> Path:
    """Emit the aggregates beside the per-pair rows, so a slide can quote one.

    R2 rejects any deck number absent from ``results/``, and it caught this: the two mean ZNCC lifts
    were first computed inside the deck builder, which is precisely the pattern that produced the
    §37 retraction. Deriving them here - from the same rows a reader can check - is the fix.
    """
    summary_path = per_pair_path.with_name(per_pair_path.stem + "_summary.csv")
    applied = [r for r in rows if r["applied"]]
    lifted = [r for r in applied if r["zncc_lift_truth"] != "" and r["zncc_lift_winner"] != ""]
    both_ok = [r for r in rows if r["ok_base"] and r["ok_cal"]]

    out: list[tuple[str, object, str]] = [
        ("n_pairs", len(rows), "pairs measured"),
        ("mislock_base", round(sum(1 for r in rows if not r["ok_base"]) / len(rows), 4),
         "shipped pipeline"),
        ("mislock_calibrated", round(sum(1 for r in rows if not r["ok_cal"]) / len(rows), 4),
         "with the global scan-field correction"),
        ("fixed", sum(1 for r in rows if not r["ok_base"] and r["ok_cal"]), "base wrong, calib right"),
        ("broke", sum(1 for r in rows if r["ok_base"] and not r["ok_cal"]), "base right, calib wrong"),
        ("applied", len(applied), "pairs where the gates let the correction run"),
    ]
    if lifted:
        truth = sum(r["zncc_lift_truth"] for r in lifted) / len(lifted)
        winner = sum(r["zncc_lift_winner"] for r in lifted) / len(lifted)
        out += [
            ("zncc_lift_truth", round(truth, 4), "mean ZNCC lift at the TRUE location"),
            ("zncc_lift_winner", round(winner, 4), "mean ZNCC lift at the CHOSEN location"),
            ("zncc_lift_differential", round(truth - winner, 4),
             "truth minus winner - the only form that changes a decision"),
            ("truth_lifted_more_in",
             sum(1 for r in lifted if r["zncc_lift_truth"] > r["zncc_lift_winner"]),
             f"of {len(lifted)}"),
        ]
    if applied:
        out.append(("calibration_ms_median",
                    round(float(np.median([r["calibration_ms"] for r in applied])), 1),
                    "cost of measuring and applying the field"))
        out.append(("field_rms_px_median",
                    round(float(np.median([r["field_rms_px"] for r in applied])), 4),
                    "measured field RMS; the generator's jitter sigma is the number to compare"))
    if both_ok:
        out.append(("median_error_base_px",
                    round(float(np.median([r["err_base_px"] for r in both_ok])), 4),
                    f"on the {len(both_ok)} pairs both arms locate"))
        out.append(("median_error_calibrated_px",
                    round(float(np.median([r["err_cal_px"] for r in both_ok])), 4), ""))

    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value", "note"])
        writer.writerows(out)
    return summary_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--splits", default="dev",
                    help=f"comma-separated, from {', '.join(SPLITS)}")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "results" / "global_jitter.csv",
                    help="relative paths are resolved against the repo root, not the shell's cwd")
    ap.add_argument("--limit", type=int, default=0, help="first N pairs per split, for a smoke run")
    ap.add_argument("--summarise", type=Path, default=None,
                    help="re-derive the summary from an existing per-pair CSV, without re-running "
                         "the pipeline. The aggregates are a pure function of those rows, and the "
                         "deck must quote a number that exists in results/ rather than one computed "
                         "while the slide is drawn (R2, ADR-0030).")
    args = ap.parse_args()

    out_path = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    wanted = [s.strip() for s in args.splits.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in SPLITS]
    if unknown:
        sys.exit(f"unknown split(s): {unknown}")

    if args.summarise is not None:
        source = args.summarise if args.summarise.is_absolute() else REPO_ROOT / args.summarise
        with source.open(newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if r.get("split") and not r["split"].startswith("#")]
        for row in rows:                       # DictReader gives strings; the report expects numbers
            for key in ("err_base_px", "err_cal_px", "zncc_lift_truth", "zncc_lift_winner",
                        "field_rms_px", "calibration_ms"):
                row[key] = float(row[key]) if row.get(key) not in (None, "") else ""
            for key in ("ok_base", "ok_cal", "applied"):
                row[key] = int(row[key])
        summary = write_summary(rows, out_path)
        report(rows, sorted({r["split"] for r in rows}))
        print(f"  Wrote {summary.relative_to(REPO_ROOT).as_posix()}\n")
        return 0

    cfg = L.build_config(argparse.Namespace(config="driftlock"))
    # Same configuration with the drift stage off, because the calibrated arm supplies the drift
    # correction itself from the uncorrected image. Everything else is identical.
    cfg_nodrift = replace(cfg, drift_correction=False)
    rows: list[dict] = []

    for split in wanted:
        manifest = REPO_ROOT / SPLITS[split] / "manifest.csv"
        if not manifest.exists():
            sys.exit(f"missing {manifest.relative_to(REPO_ROOT).as_posix()}")
        records = list(read_manifest(manifest))
        if args.limit:
            records = records[:args.limit]

        for rec in records:
            gt_x, gt_y = float(rec["gt_x"]), float(rec["gt_y"])
            ref = load_grayscale(resolve_manifest_path(manifest, rec["reference_path"]))
            search = load_grayscale(resolve_manifest_path(manifest, rec["search_path"]))

            base = localize(ref, search, cfg)
            err_base = math.hypot(base.x - gt_x, base.y - gt_y)

            started = time.perf_counter()
            corrected, measured = calibrate(search)
            calib_ms = (time.perf_counter() - started) * 1000.0

            # The drift shear is measured on the ORIGINAL image and applied to the coordinate found
            # in the CORRECTED one. That is not a convenience - it is required, and measuring it the
            # obvious way is a trap worth recording. estimate_drift_shear takes a MEDIAN over row
            # pairs whose displacement is shear*gap/(H-1) plus the difference of two per-row
            # jitters. At a 1.5 px shear the signal in one pair is ~0.15 px and the jitter
            # difference is ~0.7 px, so the estimator works precisely BECAUSE the jitter is
            # zero-median noise it can average away. Remove the jitter first and that noise is
            # replaced by the calibration's own correlated residual, which does not cancel:
            # measured on ten dev pairs, the estimate went to -3.9 and +17.0 against a true 1.50,
            # and the position error moved 0.139 -> 1.173 px. The shear is untouched by the
            # correction, so reading it off the original image is both correct and exact.
            #
            # When the gates DECLINE, the two arms must be identical by construction, so the base
            # result is reused rather than recomputed down a different path. Recomputing it was a
            # real defect in this experiment: the shipped drift stage sizes its row separation with
            # gap_for_rotation(measured_rotation), while the reroute below calls
            # estimate_drift_shear at its default gap. On the jitter3 stress split the calibration
            # declined on all 30 pairs and the two arms still differed by 2 fixed and 3 broke -
            # entirely from that gap difference, and it would have been reported as an effect of a
            # calibration that never ran.
            if not measured.applied:
                cal_x, cal_y, err_cal = base.x, base.y, err_base
            else:
                shear = estimate_drift_shear(search)
                cal = localize(ref, corrected, cfg_nodrift)
                cal_x, cal_y = (correct_for_drift(cal.x, cal.y, shear, search.shape[0])
                                if shear is not None else cal.x), cal.y
                err_cal = math.hypot(cal_x - gt_x, cal_y - gt_y)

            # THE MEASUREMENT THAT EXPLAINS THE OUTCOME. A correction that lifts the true site is
            # not automatically useful - the impostor is a real lattice site too, imaged through the
            # same scanner, so the same correction may sharpen it by the same amount. Only the
            # DIFFERENCE can change a decision. Scored at the generator's exact pose so the two
            # sites are compared on equal geometric terms.
            oracle = build_template(ref.astype(np.float32),
                                    float(rec.get("scale_ratio") or 10.0),
                                    float(rec.get("rotation_deg") or 0.0))
            lifts = {}
            for who, (px, py) in (("truth", (gt_x, gt_y)), ("winner", (base.x, base.y))):
                before = score_at(search, oracle, px, py)
                after = score_at(corrected, oracle, px, py)
                lifts[who] = (round(after - before, 5)
                              if before is not None and after is not None else "")

            rows.append({
                "split": split, "id": rec["id"],
                "err_base_px": round(err_base, 4), "err_cal_px": round(err_cal, 4),
                "zncc_lift_truth": lifts["truth"], "zncc_lift_winner": lifts["winner"],
                "ok_base": int(err_base <= NEAR_PX), "ok_cal": int(err_cal <= NEAR_PX),
                "applied": int(measured.applied), "reason": measured.reason,
                "period_px": round(measured.period_px, 3),
                "confidence": round(measured.confidence, 4),
                "agreement_px": round(measured.agreement_px, 4)
                if np.isfinite(measured.agreement_px) else "",
                "field_rms_px": round(measured.diagnostics.get("rms_px", 0.0), 4),
                "accepted_rows": measured.accepted_rows,
                "calibration_ms": round(calib_ms, 1),
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        fh.write("\n# The frozen pipeline, run twice on the same pair. The only difference is that\n")
        fh.write("# the search image has had its per-row scan jitter measured and removed FIRST,\n")
        fh.write("# from the whole image, before any candidate exists - so the same correction\n")
        fh.write("# applies to the true site and to every impostor.\n")

    summary_path = write_summary(rows, out_path)
    report(rows, wanted)
    print(f"  Wrote {out_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"  Wrote {summary_path.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


def report(rows: list[dict], wanted: list[str]) -> None:
    """Print the comparison. Shared by the measuring path and by ``--summarise``."""
    print(f"\n  {'split':<9}{'n':>4}{'base':>9}{'calib':>9}{'fixed':>7}{'broke':>7}"
          f"{'applied':>9}{'p':>8}")
    print("  " + "-" * 62)
    for split in wanted:
        sub = [r for r in rows if r["split"] == split]
        if not sub:
            continue
        n = len(sub)
        base_bad = sum(1 for r in sub if not r["ok_base"])
        cal_bad = sum(1 for r in sub if not r["ok_cal"])
        fixed = sum(1 for r in sub if not r["ok_base"] and r["ok_cal"])
        broke = sum(1 for r in sub if r["ok_base"] and not r["ok_cal"])
        applied = sum(r["applied"] for r in sub)
        print(f"  {split:<9}{n:>4}{100 * base_bad / n:>8.1f}%{100 * cal_bad / n:>8.1f}%"
              f"{fixed:>7}{broke:>7}{applied:>6}/{n:<3}{mcnemar_exact(broke, fixed):>8.3f}")

    n_all = len(rows)
    base_bad = sum(1 for r in rows if not r["ok_base"])
    cal_bad = sum(1 for r in rows if not r["ok_cal"])
    fixed = sum(1 for r in rows if not r["ok_base"] and r["ok_cal"])
    broke = sum(1 for r in rows if r["ok_base"] and not r["ok_cal"])
    print("  " + "-" * 62)
    print(f"  {'TOTAL':<9}{n_all:>4}{100 * base_bad / n_all:>8.1f}%{100 * cal_bad / n_all:>8.1f}%"
          f"{fixed:>7}{broke:>7}{'':>9}{mcnemar_exact(broke, fixed):>8.3f}")

    applied_rows = [r for r in rows if r["applied"]]
    if applied_rows:
        print(f"\n  calibration applied on {len(applied_rows)}/{n_all}, "
              f"median field RMS {np.median([r['field_rms_px'] for r in applied_rows]):.3f} px, "
              f"median cost {np.median([r['calibration_ms'] for r in applied_rows]):.0f} ms")
    declined = {r["reason"] for r in rows if not r["applied"]}
    if declined:
        print(f"  declined on {n_all - len(applied_rows)}: {'; '.join(sorted(declined))}")

    lifted = [r for r in rows if r["applied"] and r["zncc_lift_truth"] != ""
              and r["zncc_lift_winner"] != ""]
    if lifted:
        lt = float(np.mean([r["zncc_lift_truth"] for r in lifted]))
        lw = float(np.mean([r["zncc_lift_winner"] for r in lifted]))
        ahead = sum(1 for r in lifted if r["zncc_lift_truth"] > r["zncc_lift_winner"])
        print(f"\n  ZNCC lift from the correction, on the {len(lifted)} pairs it was applied to:")
        print(f"    at the TRUE location    : {lt:+.4f}")
        print(f"    at the CHOSEN location  : {lw:+.4f}")
        print(f"    DIFFERENTIAL            : {lt - lw:+.4f}   truth lifted more in "
              f"{ahead}/{len(lifted)}")

    # Located-only median, so a change in precision is visible separately from a change in mis-lock.
    both_ok = [r for r in rows if r["ok_base"] and r["ok_cal"]]
    if both_ok:
        print(f"\n  median error on the {len(both_ok)} pairs both configurations locate: "
              f"{np.median([r['err_base_px'] for r in both_ok]):.4f} -> "
              f"{np.median([r['err_cal_px'] for r in both_ok]):.4f} px")
    print()


if __name__ == "__main__":
    sys.exit(main())
