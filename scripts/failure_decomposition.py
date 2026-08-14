#!/usr/bin/env python3
"""Split every mis-lock into the stage that actually lost it, and test the mechanism claim.

    python scripts/failure_decomposition.py

Two questions, one instrumented pass.

**Question 1 - which stage loses each failure?** "18% mis-lock" is one number covering three
different failures with three different fixes:

    ABSENT    the true location never became a candidate at all
              -> no selection rule of any kind can recover it; only proposal generation can
    SCREENED  it was a candidate, but the cheap screen ranked it outside the top 10
              -> the wide refit never sees it; the screen is a hard gate
    OUTSCORED it survived to the final comparison and lost on ZNCC
              -> the only bucket a better selection rule could address

Six re-ranking criteria were built and rejected (ADR-0024) on the implicit assumption that the
remaining failures were OUTSCORED. That assumption was never measured. If most failures are ABSENT,
those six experiments were aimed at the wrong stage.

**Question 2 - does the mechanism claim survive contact with the data?** FINDINGS 23f argues the
screen works because a wide pose search rewards periodic impostors more than the true candidate.
That is inferred from an ablation (A/B/C/D), not observed directly. It makes a falsifiable
prediction: *in an OUTSCORED failure, the winning impostor should have travelled further in pose
than the true candidate did.* This measures that per failure, so the claim can be checked rather
than repeated.
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
import src.driftlock.refit as refit_module  # noqa: E402
from src.driftlock.io import (  # noqa: E402
    euclidean_error,
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)
from src.driftlock.match import localize  # noqa: E402

MISLOCK_PX = 5.0
NEAR_PX = 5.0                    # a candidate this close to GT counts as "the true candidate"
SPLITS = [("sponsor", "data/_sponsor/verify"),
          ("bench", "data/bench"),
          ("finfet", "data/holdout_finfet")]

STATE: dict = {}
_original_refit_once = refit_module._refit_once


def _instrumented(search, reference, candidates, build_template, correlation_surface,
                  span, rot_span, steps, margin, pose_penalty):
    """Capture the candidate field entering and leaving the screen.

    The screen is the call with ``steps == 2`` (refit_screen_steps); the wide pass uses 5. Recording
    the field on BOTH sides is what separates ABSENT from SCREENED - a single snapshot cannot.
    """
    incoming = STATE.get("incoming")
    if incoming is None:
        gx, gy = STATE["gt"]
        STATE["incoming"] = [
            i for i, c in enumerate(candidates) if (c.x - gx) ** 2 + (c.y - gy) ** 2 <= NEAR_PX ** 2
        ]
        STATE["pool_size"] = len(candidates)
        # Stamp each candidate's ENTRY pose so travel can be measured later.
        #
        # The first version of this recorded abs(rotation_deg) at the end and called it "pose
        # travel". That is the final absolute pose, not displacement from where the candidate
        # started - so it did not measure the quantity it was named after, and the "refutation" it
        # produced meant nothing. Candidate objects are mutated in place by the refit rather than
        # rebuilt, so a value stashed here survives to the end and the difference is real travel.
        for c in candidates:
            c.extra["pose_in"] = (float(c.scale), float(c.rotation_deg))

    out = _original_refit_once(search, reference, candidates, build_template, correlation_surface,
                               span, rot_span, steps, margin, pose_penalty)

    if steps == STATE.get("screen_steps") and "screen_rank" not in STATE:
        gx, gy = STATE["gt"]
        hits = [i for i, c in enumerate(out) if (c.x - gx) ** 2 + (c.y - gy) ** 2 <= NEAR_PX ** 2]
        STATE["screen_rank"] = hits[0] if hits else -1
    # Always refresh: the last call is the wide pass, whose output is the final ranking.
    gx, gy = STATE["gt"]
    STATE["final"] = [
        (i, c) for i, c in enumerate(out) if (c.x - gx) ** 2 + (c.y - gy) ** 2 <= NEAR_PX ** 2
    ]
    STATE["winner"] = out[0] if out else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results/failure_decomposition.csv")
    # Arbitrary manifests, so a stress split can be decomposed with the same instrument as the
    # reported ones. "33% mis-lock under charging streaks" does not say whether a preprocessing fix
    # could help; "the streak failures are ABSENT, not OUTSCORED" does.
    ap.add_argument("--manifest", action="append",
                    help="NAME=PATH; repeat. Defaults to the three reported splits.")
    args = ap.parse_args()

    splits = SPLITS
    if args.manifest:
        splits = []
        for entry in args.manifest:
            name, _, path = entry.partition("=")
            splits.append((name, path) if path else (Path(entry).parent.name, entry))

    import argparse as _ap
    cfg = L.build_config(_ap.Namespace(config="driftlock"))
    screen_top_n = cfg.refit_screen_top_n
    refit_module._refit_once = _instrumented

    rows, mech = [], []
    print(f"\n  {'split':<10}{'n':>4}{'correct':>9}{'ABSENT':>8}{'SCREENED':>10}{'OUTSCORED':>11}")
    print("  " + "-" * 54)

    for name, folder in splits:
        candidate = Path(folder)
        manifest = candidate if candidate.suffix == ".csv" else REPO_ROOT / folder / "manifest.csv"
        counts = {"correct": 0, "absent": 0, "screened": 0, "outscored": 0}
        for row in read_manifest(manifest):
            gt = (float(row["gt_x"]), float(row["gt_y"]))
            STATE.clear()
            STATE.update({"gt": gt, "screen_steps": cfg.refit_screen_steps})
            match = localize(load_grayscale(resolve_manifest_path(manifest, row["reference_path"])),
                             load_grayscale(resolve_manifest_path(manifest, row["search_path"])),
                             cfg)
            error = euclidean_error((match.x, match.y), gt)

            if error <= MISLOCK_PX:
                bucket = "correct"
            elif not STATE.get("incoming"):
                bucket = "absent"
            elif STATE.get("screen_rank", -1) < 0 or STATE["screen_rank"] >= screen_top_n:
                bucket = "screened"
            else:
                bucket = "outscored"
            counts[bucket] += 1

            # Mechanism test: only meaningful when both candidates reached the final comparison.
            if bucket == "outscored" and STATE.get("final") and STATE.get("winner") is not None:
                truth = STATE["final"][0][1]
                winner = STATE["winner"]

                def travel(c) -> float:
                    """Distance moved in pose space, from the bracket pose to the refitted one.

                    Scale and rotation are different units, so they are normalised by the refit's
                    own search span before combining - a full-span move on either axis counts as 1.
                    """
                    s0, r0 = c.extra.get("pose_in", (c.scale, c.rotation_deg))
                    ds = (c.scale - s0) / max(s0 * cfg.refit_scale_span, 1e-9)
                    dr = (c.rotation_deg - r0) / max(cfg.refit_rotation_span, 1e-9)
                    return float((ds * ds + dr * dr) ** 0.5)

                mech.append({
                    "split": name, "id": row["id"],
                    "score_margin": float(winner.score - truth.score),
                    "winner_pose_travel": travel(winner),
                    "truth_pose_travel": travel(truth),
                    "winner_scale": float(winner.scale), "truth_scale": float(truth.scale),
                    "error_px": float(error),
                })

            rows.append({
                "split": name, "id": row["id"], "bucket": bucket,
                "error_px": f"{error:.3f}",
                "pool_size": STATE.get("pool_size", 0),
                "screen_rank_of_truth": STATE.get("screen_rank", -1),
            })

        n = sum(counts.values())
        print(f"  {name:<10}{n:>4}{counts['correct'] / n * 100:>8.1f}%"
              f"{counts['absent'] / n * 100:>7.1f}%{counts['screened'] / n * 100:>9.1f}%"
              f"{counts['outscored'] / n * 100:>10.1f}%")

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        fh.write("\n# bucket: correct | absent (never a candidate) | screened (cut by the screen)\n")
        fh.write("#         | outscored (survived to the final comparison and lost on ZNCC)\n")
        fh.write(f"# a candidate counts as 'the true one' within {NEAR_PX:.0f} px of ground truth\n")

    if mech:
        wt = np.array([m["winner_pose_travel"] for m in mech])
        tt = np.array([m["truth_pose_travel"] for m in mech])
        margin = np.array([m["score_margin"] for m in mech])
        print(f"\n  MECHANISM TEST on {len(mech)} outscored failures")
        print(f"    winner |rotation| mean {wt.mean():.3f} deg   truth {tt.mean():.3f} deg")
        print(f"    winner travelled further in {100 * (wt > tt).mean():.0f}% of them")
        print(f"    median score margin the truth lost by: {np.median(margin):.4f}")
        # Derive the companion filename from --out, not a fixed name. It was fixed, so running this
        # over a stress split silently overwrote the reported splits' mechanism file with four
        # unrelated rows - the analysis then described the wrong pairs and nothing complained.
        mech_out = out.with_name(out.stem.replace("failure_decomposition", "failure_mechanism")
                                 + out.suffix)
        with mech_out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(mech[0]))
            writer.writeheader()
            writer.writerows(mech)
        print(f"    wrote {mech_out.relative_to(REPO_ROOT).as_posix()}")

    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
