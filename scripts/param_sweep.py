#!/usr/bin/env python3
"""Sweep one PipelineConfig field over a set of values, paired, with the tuning family separated.

    python scripts/param_sweep.py --param refit_screen_top_n --values 30,40,50,60
    python scripts/param_sweep.py --param pose_evidence_beta --values 2,5,10,20 --splits dev,dev2

Why a generic sweeper exists at all. Three shipped decisions here (ADR-0034, ADR-0035, ADR-0036) are
single-parameter changes, and each was measured with a script written for it and thrown away. That
is how `refit_screen_top_n` came to be measured as "flat" in one pipeline (FINDINGS 23d) and worth
four pairs in another (ADR-0034) with no standing way to re-ask the question. **A parameter measured
as flat is flat against the pipeline it was measured in**, so re-asking has to be cheap.

What this enforces, because the answers are worthless otherwise:

* **Paired, not marginal.** Every value runs on the same pairs as the reference value (the first in
  `--values`), and the output is fixed/broken counts, not two rates to eyeball. Two splits with
  identical parameters have measured several points apart here from seed alone (ADR-0029).
* **The tuning family is printed separately and first.** `dev` and `dev2` are where a value may be
  chosen; the reporting splits are there to confirm the choice, never to make it (R5). The two
  blocks are labelled so a value cannot be quietly picked off the reporting half.
* **No value is "best" on the strength of the aggregate.** A change that fixes two pairs on one
  split and breaks two on another is not an improvement, and summing hides that.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

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
from src.driftlock.match import localize  # noqa: E402

MISLOCK_PX = 5.0

KNOWN_SPLITS = {
    "dev": "data/dev",
    "dev2": "data/dev2",
    "sponsor": "data/_sponsor/verify",
    "bench": "data/bench",
    "finfet": "data/holdout_finfet",
}
TUNING = ("dev", "dev2")


def coerce(text: str, current) -> object:
    """Parse a CLI value into the type the config field already holds."""
    if isinstance(current, bool):
        return text.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(text)
    if isinstance(current, float):
        return float(text)
    return text


def run_split(manifest: Path, cfg) -> dict[str, float]:
    """Euclidean error per id for one split under one configuration."""
    out = {}
    for row in read_manifest(manifest):
        gt = (float(row["gt_x"]), float(row["gt_y"]))
        match = localize(
            load_grayscale(resolve_manifest_path(manifest, row["reference_path"])),
            load_grayscale(resolve_manifest_path(manifest, row["search_path"])),
            cfg)
        out[row["id"]] = euclidean_error((match.x, match.y), gt)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--param", required=True, help="a PipelineConfig field name")
    ap.add_argument("--values", required=True,
                    help="comma-separated; the FIRST is the reference everything is paired against")
    ap.add_argument("--splits", default="dev,dev2,sponsor,bench,finfet")
    ap.add_argument("--out", default=None, help="defaults to results/param_sweep_<param>.csv")
    args = ap.parse_args()

    import argparse as _ap
    base_cfg = L.build_config(_ap.Namespace(config="driftlock"))
    if not hasattr(base_cfg, args.param):
        print(f"error: PipelineConfig has no field '{args.param}'", file=sys.stderr)
        return 2
    current = getattr(base_cfg, args.param)
    values = [coerce(v, current) for v in args.values.split(",")]

    splits = []
    for name in args.splits.split(","):
        name = name.strip()
        if name not in KNOWN_SPLITS:
            print(f"error: unknown split '{name}'", file=sys.stderr)
            return 2
        splits.append((name, REPO_ROOT / KNOWN_SPLITS[name] / "manifest.csv"))

    print(f"\n  sweeping {args.param}: {values}")
    print(f"  shipped value is {current!r}; reference for pairing is {values[0]!r}\n")

    # errors[value][split] = {id: error}
    errors: dict[object, dict[str, dict[str, float]]] = {}
    for value in values:
        cfg = replace(base_cfg, **{args.param: value})
        errors[value] = {}
        for name, manifest in splits:
            errors[value][name] = run_split(manifest, cfg)
            n = len(errors[value][name])
            bad = sum(1 for e in errors[value][name].values() if e > MISLOCK_PX)
            print(f"    {args.param}={value!r:<8} {name:<9} {bad}/{n}", flush=True)

    reference = values[0]
    rows = []
    for group, label in ((TUNING, "TUNING FAMILY - a value may be chosen here"),
                         (tuple(s for s in KNOWN_SPLITS if s not in TUNING),
                          "REPORTING SPLITS - confirmation only, never selection")):
        present = [(n, m) for n, m in splits if n in group]
        if not present:
            continue
        print(f"\n  {label}")
        print(f"    {'value':<10}" + "".join(f"{n:>11}" for n, _ in present)
              + f"{'total':>9}{'fixed':>7}{'broke':>7}")
        for value in values:
            cells, tot_bad, fixed, broke = "", 0, 0, 0
            for name, _ in present:
                err = errors[value][name]
                ref = errors[reference][name]
                bad = sum(1 for e in err.values() if e > MISLOCK_PX)
                cells += f"{bad:>11}"
                tot_bad += bad
                fixed += sum(1 for i in err if ref[i] > MISLOCK_PX >= err[i])
                broke += sum(1 for i in err if err[i] > MISLOCK_PX >= ref[i])
            mark = "  <- reference" if value == reference else ""
            print(f"    {value!r:<10}{cells}{tot_bad:>9}{fixed:>7}{broke:>7}{mark}")
            rows.append({"param": args.param, "value": value, "group": group[0],
                         "mislocks": tot_bad, "fixed_vs_reference": fixed,
                         "broken_vs_reference": broke})

    out = Path(args.out) if args.out else REPO_ROOT / "results" / f"param_sweep_{args.param}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        fh.write("\n# group 'dev' = the tuning family (dev + dev2); 'sponsor' = the reporting\n")
        fh.write("# splits. fixed/broken are paired against the FIRST value swept.\n")
        fh.write("# A value chosen on the reporting rows would kill the benchmark (R5).\n")
    print(f"\n  Wrote {out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
