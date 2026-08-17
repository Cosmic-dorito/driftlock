#!/usr/bin/env python3
"""Is the MAXIMUM over the pose grid the wrong statistic?

    python scripts/pose_evidence.py --capture          # run the pipeline, cache every pose grid
    python scripts/pose_evidence.py                    # sweep selectors over the cache, offline

THE ARGUMENT, AND WHY IT IS NOT ANOTHER RE-RANKER. ADR-0024 says do not re-rank by a NEW criterion;
six attempts, six failures. This is not a new criterion. It is the *same* ZNCC, read off the *same*
pose grid the refit already computes, summarised by a different statistic.

And the reason to suspect the maximum comes from our own measurement, not from taste. FINDINGS 23f
found that handing a wide pose bracket to the whole candidate field is worse than handing it to ten
survivors - a wide search helps impostors MORE. That is a multiple-comparisons effect: every
candidate gets 25 attempts at a flattering pose, and a candidate whose pose surface is rough has
more opportunity to get lucky than one whose surface is flat and genuinely high. The maximum of 25
draws is a biased estimate of quality, and the bias grows with the roughness of the surface.

  truth     0.762 0.768 0.766 0.764 0.765   ->  max 0.768, consistently good
  impostor  0.751 0.752 0.769 0.753 0.750   ->  max 0.769, one lucky sample

Under a maximum the impostor wins. Under any statistic that reads the grid as evidence it does not.

SELECTORS COMPARED (all on the identical cached grids, so the comparison is exactly paired):

  max          what ships today
  top3         mean of the three best samples
  lse          (1/beta) log mean exp(beta * s)   - smooth interpolation between mean and max
  mean         the beta -> 0 limit, kept as the extreme case rather than as a serious proposal
  ev           max - lambda * std(grid)          - discount a max drawn from a rough surface

A fixed look-elsewhere correction cannot work here and it is worth saying why: every candidate is
scored on the same grid size, so ``-lambda*sqrt(2 log N)`` is a constant and constants do not
reorder anything. What differs between candidates is the *effective* number of independent
attempts, which is what the surface roughness stands in for.

HELD-OUT DISCIPLINE (R5). Any free parameter is chosen on the tuning family (``dev`` + ``dev2``,
200 pairs) and frozen before the reporting splits are looked at. The sweep prints both halves so
that cannot be fudged.

⚠️ **THE RATES PRINTED HERE ARE NOT THE PIPELINE'S RATES, and must never be quoted as them.**
``_capturing_refit`` stores only ``out[:10]``, while the shipped pipeline re-orders every
wide-refit survivor - up to ``refit_screen_top_n`` = 30 of them. So this sweep re-ranks a truncated
field and will report a *worse* number than the pipeline achieves with the same selector: on
16 Aug it put ``lse`` at 10.0% on sponsor where the pipeline measures 0.0%. If the truth sits at
score-rank 15 and evidence-rank 0, the pipeline finds it and this proxy cannot see it at all.

What the proxy IS good for is the *relative* ordering of selectors and of one selector's free
parameter, because every variant is scored on the identical cached field, so those comparisons are
exactly paired. Use it to shortlist; confirm any winner with ``scripts/param_sweep.py``, which runs
the real pipeline. Working rule 13: an offline proxy and the pipeline can disagree for reasons that
exist only in the pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import localize as L  # noqa: E402
import src.driftlock.refit as refit_mod  # noqa: E402
from src.driftlock.io import (  # noqa: E402
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)
from src.driftlock.match import localize  # noqa: E402

NEAR_PX = 5.0
REPORTING_SPLITS = ("sponsor", "bench", "finfet")
SPLITS = {
    "dev": "data/dev",
    # dev2 is the larger half of the tuning family (160 pairs against dev's 40) and was missing
    # here, so beta was originally chosen on 40 pairs while every other decision of this size used
    # 200. Added 16 Aug when beta came up for re-examination.
    "dev2": "data/dev2",
    "sponsor": "data/_sponsor/verify",
    "bench": "data/bench",
    "finfet": "data/holdout_finfet",
}
TUNING_SPLITS = ("dev", "dev2")

CAPTURED: dict = {}
_refit_candidates = refit_mod.refit_candidates


def _capturing_refit(search, reference, candidates, bt, cs, config):
    out = _refit_candidates(search, reference, candidates, bt, cs, config)
    rows = []
    for cand in out[:10]:
        grid = cand.extra.get("refit_grid")
        rows.append({
            "x": float(cand.x), "y": float(cand.y), "score": float(cand.score),
            "grid": np.asarray(grid[0]).tolist() if grid is not None else None,
        })
    CAPTURED["final"] = rows
    return out


refit_mod.refit_candidates = _capturing_refit


# ---------------------------------------------------------------------------------------
# Selectors. Each takes one candidate's pose grid and returns a scalar to rank by.
# ---------------------------------------------------------------------------------------

def _clean(grid: list | None) -> np.ndarray | None:
    """The grid with unscored cells removed. Poses whose template did not fit are stored as -2."""
    if grid is None:
        return None
    values = np.asarray(grid, dtype=np.float64).ravel()
    values = values[values > -1.5]
    return values if values.size else None


def select_max(values: np.ndarray, fallback: float, **_) -> float:
    return float(values.max()) if values is not None else fallback


def select_top3(values: np.ndarray, fallback: float, **_) -> float:
    if values is None:
        return fallback
    k = min(3, values.size)
    return float(np.sort(values)[-k:].mean())


def select_lse(values: np.ndarray, fallback: float, beta: float = 200.0, **_) -> float:
    if values is None:
        return fallback
    shifted = beta * (values - values.max())
    return float(values.max() + math.log(np.exp(shifted).mean()) / beta)


def select_mean(values: np.ndarray, fallback: float, **_) -> float:
    return float(values.mean()) if values is not None else fallback


def select_ev(values: np.ndarray, fallback: float, lam: float = 1.0, **_) -> float:
    if values is None:
        return fallback
    return float(values.max() - lam * values.std())


def _pose_probabilities(values: np.ndarray, beta: float) -> np.ndarray:
    """The pose grid read as a distribution over the nuisance parameter."""
    shifted = beta * (values - values.max())
    weights = np.exp(shifted)
    total = weights.sum()
    return weights / total if total > 0 else np.full(values.shape, 1.0 / values.size)


def select_entropy(values: np.ndarray, fallback: float, beta: float = 200.0,
                   gamma: float = 0.01, **_) -> float:
    """Peak height, discounted by how DIFFUSE the candidate's pose likelihood is.

    A true site should concentrate its evidence near one pose; a candidate that got lucky at one
    sample has a flat surface with a spike on it. Normalised by log(n) so the penalty is
    grid-size-independent and gamma keeps its units.
    """
    if values is None or values.size < 2:
        return fallback
    p = _pose_probabilities(values, beta)
    entropy = float(-(p * np.log(p + 1e-300)).sum() / math.log(values.size))
    return float(values.max() - gamma * entropy)


def _effective_trials(values: np.ndarray) -> float:
    """How many INDEPENDENT pose samples this candidate effectively drew.

    A fixed look-elsewhere correction cannot reorder anything - every candidate is scored on the
    same grid, so the count is a constant. What differs is smoothness: a surface whose neighbouring
    samples are highly correlated is really one or two independent draws, while a jagged one is
    closer to n. Estimated as ``n * (1 - rho)`` with rho the lag-1 autocorrelation, clipped to
    [1, n], which is the standard effective-sample-size correction for a correlated series.
    """
    n = values.size
    if n < 3:
        return float(n)
    centred = values - values.mean()
    denom = float((centred * centred).sum())
    if denom < 1e-15:
        return 1.0
    rho = float((centred[:-1] * centred[1:]).sum() / denom)
    return float(np.clip(n * (1.0 - rho), 1.0, n))


def select_ev_neff(values: np.ndarray, fallback: float, lam: float = 1.0, **_) -> float:
    """Extreme-value correction using the EFFECTIVE number of pose trials.

    ``max - lam * sigma * sqrt(2 log N_eff)`` is the Gumbel-style expectation of the maximum of
    ``N_eff`` draws, so this asks how surprising the peak is rather than how large it is. This is
    the principled version of ``select_ev``'s ``max - lam*std``, which used the spread directly and
    ignored that the spread and the number of chances are separate quantities.
    """
    if values is None or values.size < 3:
        return fallback
    n_eff = _effective_trials(values)
    return float(values.max() - lam * values.std() * math.sqrt(2.0 * math.log(max(n_eff, 1.0001))))


def select_peakiness(values: np.ndarray, fallback: float, gamma: float = 1.0, **_) -> float:
    """Peak height plus a reward for the peak standing above its own surface.

    The complement of the entropy selector: instead of penalising diffuseness it rewards contrast
    between the maximum and the bulk. Included because the two can disagree, and a hypothesis that
    only one of them captures the effect is worth being able to reject.
    """
    if values is None or values.size < 2:
        return fallback
    return float(values.max() + gamma * (values.max() - float(np.median(values))))


SELECTORS = {
    "max": (select_max, {}),
    "top3": (select_top3, {}),
    # The first sweep put the lse optimum at beta=50, the SMALLEST value tested, which is the
    # classic sign that the grid is in the wrong place rather than that 50 is special. Extended
    # downward until the optimum is interior; beta -> 0 is the mean, which is why 'mean' is listed
    # as its own row rather than as a straw man.
    "lse": (select_lse, {"beta": [5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0, 800.0]}),
    "mean": (select_mean, {}),
    "ev": (select_ev, {"lam": [0.1, 0.25, 0.5, 1.0, 2.0]}),
    # Experiment A, second round: the grid holds more than a location parameter. These read its
    # SHAPE - how concentrated the evidence is, and how many independent chances the candidate
    # really had at its peak - rather than only its height.
    "entropy": (select_entropy, {"gamma": [0.002, 0.005, 0.01, 0.02, 0.05]}),
    "ev_neff": (select_ev_neff, {"lam": [0.05, 0.1, 0.25, 0.5, 1.0]}),
    "peaky": (select_peakiness, {"gamma": [0.1, 0.25, 0.5, 1.0, 2.0]}),
}

# The shipped selector, so every row is compared against what actually runs today rather than
# against the maximum it already replaced.
SHIPPED = ("lse", {"beta": 5.0})


# ---------------------------------------------------------------------------------------

def capture(cache_path: Path) -> int:
    cfg = L.build_config(argparse.Namespace(config="driftlock"))
    out: dict[str, list] = {}
    for split, folder in SPLITS.items():
        manifest = REPO_ROOT / folder / "manifest.csv"
        if not manifest.exists():
            print(f"  skipping {split}: no manifest", file=sys.stderr)
            continue
        rows = []
        for rec in read_manifest(manifest):
            ref = load_grayscale(resolve_manifest_path(manifest, rec["reference_path"]))
            search = load_grayscale(resolve_manifest_path(manifest, rec["search_path"]))
            CAPTURED.clear()
            localize(ref, search, cfg)
            rows.append({
                "id": rec["id"],
                "gt": [float(rec["gt_x"]), float(rec["gt_y"])],
                # Cached so the sweep can ask WHEN integration helps, not just whether. The sponsor
                # split is fixed at 10:1 and 0 degrees (H9), so its pose grid is centred on the true
                # pose and every sample is near-optimal - averaging there is nearly free. Where the
                # pose genuinely varies, the grid spans poses that are wrong, and averaging dilutes
                # the peak with them. That predicts the split pattern and is testable within a split.
                "scale_ratio": float(rec.get("scale_ratio") or 10.0),
                "rotation_deg": float(rec.get("rotation_deg") or 0.0),
                "candidates": CAPTURED.get("final", []),
            })
        out[split] = rows
        print(f"  captured {split}: {len(rows)} pairs", file=sys.stderr)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out), encoding="utf-8")
    print(f"  wrote {cache_path}", file=sys.stderr)
    return 0


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar. Only the discordant pairs carry information."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = min(only_a, only_b)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(tail + 1)) / 2 ** n)


def evaluate(rows: list, selector, **kwargs) -> dict:
    """Compare one selector against the shipped maximum, PAIRED on the same candidate lists.

    Aggregates hide the thing that matters. A selector that fixes four pairs on one split and
    breaks four on another has an unchanged aggregate and is not a discovery - ADR-0012 and
    ADR-0021 each reversed a conclusion on exactly that. So fixed/broke are counted per split and
    tested with an exact McNemar.
    """
    bad = flipped = fixed = broke = 0
    n = 0
    for row in rows:
        cands = row["candidates"]
        if not cands:
            continue
        n += 1
        gx, gy = row["gt"]
        # ONLY the wide-refit survivors are re-ordered. refit_candidates merges the screened-out
        # candidates back in, and their grids come from the NARROW 2x2 screen rather than the 5x5
        # wide pass. A narrow grid is flat and high by construction, so its log-sum-exp sits close
        # to its maximum while a wide grid necessarily averages in poses that are wrong. Ranking the
        # two together compares statistics over different supports and promotes exactly the
        # candidates the screen rejected - in the pipeline that turned four sponsor failures from
        # 14.4/14.3/21.5/95.2 px into 57.6/57.4/37.5/271.7 px before it was caught.
        shapes = [np.asarray(c["grid"]).shape for c in cands if c["grid"] is not None]
        widest = max(shapes, key=lambda s: s[0] * s[1]) if shapes else None
        eligible = [c for c in cands
                    if c["grid"] is not None and np.asarray(c["grid"]).shape == widest] or cands
        scored = [(selector(_clean(c["grid"]), c["score"], **kwargs), c) for c in eligible]
        chosen = max(scored, key=lambda t: t[0])[1]
        # The reference is what SHIPS, not the maximum it already replaced. Comparing every new
        # statistic against the plain argmax would keep re-crediting the gain ADR-0032 already
        # banked and hide whether anything further is on the table.
        shipped_fn, shipped_kwargs = SELECTORS[SHIPPED[0]][0], SHIPPED[1]
        shipped_scored = [(shipped_fn(_clean(c["grid"]), c["score"], **shipped_kwargs), c)
                          for c in eligible]
        current = max(shipped_scored, key=lambda t: t[0])[1]
        ok = math.hypot(chosen["x"] - gx, chosen["y"] - gy) <= NEAR_PX
        was_ok = math.hypot(current["x"] - gx, current["y"] - gy) <= NEAR_PX
        bad += not ok
        flipped += chosen is not current
        fixed += (not was_ok) and ok
        broke += was_ok and (not ok)
    return {"n": n, "bad": bad, "flips": flipped, "fixed": fixed, "broke": broke,
            "p": mcnemar_exact(broke, fixed)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", action="store_true", help="re-run the pipeline and cache grids")
    ap.add_argument("--cache", type=Path,
                    default=REPO_ROOT / "results" / "pose_grids.json")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "results" / "pose_evidence.csv")
    args = ap.parse_args()

    if args.capture:
        return capture(args.cache)
    if not args.cache.exists():
        sys.exit(f"no cache at {args.cache} - run with --capture first")

    data = json.loads(args.cache.read_text(encoding="utf-8"))
    have_grid = sum(1 for rows in data.values() for r in rows
                    for c in r["candidates"] if c["grid"] is not None)
    total = sum(len(r["candidates"]) for rows in data.values() for r in rows)
    print(f"\n  {total} candidates cached, {have_grid} with a pose grid "
          f"({100 * have_grid / max(total, 1):.0f}%)")

    # --- Stage 1: choose every free parameter on the TUNING FAMILY, and only it (R5) ---
    # beta was originally chosen on dev's 40 pairs alone - the smallest sample any decision of this
    # size has rested on here, and two splits of 30 with identical parameters have measured several
    # points apart on this project (ADR-0029). Pooling dev + dev2 puts the choice on 200 pairs.
    # Neither split is ever reported.
    tuned: dict[str, dict] = {}
    tuning = [pair for split in TUNING_SPLITS for pair in data.get(split, [])]
    if tuning:
        print(f"\n  Stage 1 - tuning on {' + '.join(TUNING_SPLITS)} ({len(tuning)} pairs) only")
        for name, (fn, grid) in SELECTORS.items():
            if not grid:
                tuned[name] = {}
                res = evaluate(tuning, fn)
                print(f"    {name:<8} {'':<18} mis-lock {res['bad']}/{res['n']}")
                continue
            key = next(iter(grid))
            best, best_bad = None, None
            for value in grid[key]:
                res = evaluate(tuning, fn, **{key: value})
                marker = ""
                if best_bad is None or res["bad"] < best_bad:
                    best, best_bad, marker = value, res["bad"], "  <-"
                print(f"    {name:<8} {key}={value:<12} mis-lock {res['bad']}/"
                      f"{res['n']}{marker}")
            tuned[name] = {key: best}
        print("\n  frozen: " + ", ".join(f"{k}{v}" for k, v in tuned.items() if v))
    else:
        tuned = {name: {} for name in SELECTORS}

    # --- Stage 2: apply the frozen selectors to the reporting splits ---
    print("\n  Stage 2 - frozen selectors on the reporting splits\n")
    header = f"  {'selector':<10}" + "".join(f"{s:>12}" for s in REPORTING_SPLITS) + \
             f"{'aggregate':>12}{'flips':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    lines = [["selector", *REPORTING_SPLITS, "aggregate_mislock", "flips",
              "fixed_broke", "mcnemar_p"]]
    for name, (fn, _grid) in SELECTORS.items():
        kwargs = tuned.get(name, {})
        cells, total_bad, total_n, total_flips = [], 0, 0, 0
        total_fixed = total_broke = 0
        for split in REPORTING_SPLITS:
            rows = data.get(split, [])
            if not rows:
                cells.append("—")
                continue
            res = evaluate(rows, fn, **kwargs)
            cells.append(f"{100 * res['bad'] / res['n']:.1f}%  +{res['fixed']}/-{res['broke']}")
            total_bad += res["bad"]
            total_n += res["n"]
            total_flips += res["flips"]
            total_fixed += res["fixed"]
            total_broke += res["broke"]
        agg = f"{100 * total_bad / total_n:.1f}%" if total_n else "—"
        label = name + ("" if not kwargs else f" {list(kwargs.values())[0]:g}")
        p_value = mcnemar_exact(total_broke, total_fixed)
        print(f"  {label:<10}" + "".join(f"{c:>20}" for c in cells) +
              f"{agg:>10}{total_flips:>7}{p_value:>8.3f}")
        lines.append([label, *cells, agg, str(total_flips),
                      f"+{total_fixed}/-{total_broke}", f"{p_value:.4f}"])

    # --- Stage 3: WHEN does integrating beat maximising? ---
    #
    # The split pattern suggests a mechanism rather than noise: the sponsor split is fixed at 10:1
    # and 0 degrees (H9), so its pose grid straddles the true pose and every sample is near-optimal.
    # Where the pose genuinely varies, part of the grid covers poses that are wrong, and averaging
    # mixes them in. If that is the explanation, the advantage should track pose offset WITHIN the
    # splits that have pose variation - not just between splits, which is the weaker comparison
    # ADR-0029 warns about.
    best_name, best_kwargs = "lse", tuned.get("lse", {})
    varied = [r for split in ("bench", "finfet") for r in data.get(split, [])]
    if varied and best_kwargs:
        offsets = [max(abs(r["rotation_deg"]) / 2.0, abs(r["scale_ratio"] - 10.0)) for r in varied]
        cut = float(np.median(offsets))
        near = [r for r, o in zip(varied, offsets) if o <= cut]
        far = [r for r, o in zip(varied, offsets) if o > cut]
        print(f"\n  Stage 3 - within bench+finfet, split at the median pose offset ({cut:.2f})")
        print(f"  {'stratum':<22}{'n':>4}{'max':>8}{'lse':>8}{'fixed':>8}{'broke':>8}")
        print("  " + "-" * 58)
        for label, rows in (("near-nominal pose", near), ("far from nominal", far)):
            if not rows:
                continue
            base = evaluate(rows, select_max)
            alt = evaluate(rows, SELECTORS[best_name][0], **best_kwargs)
            print(f"  {label:<22}{alt['n']:>4}{base['bad']:>8}{alt['bad']:>8}"
                  f"{alt['fixed']:>8}{alt['broke']:>8}")
        print("  (mis-lock COUNTS, not rates, because these strata are small)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        import csv as _csv
        writer = _csv.writer(fh)
        writer.writerows(lines)
        fh.write("\n# Every selector reads the SAME cached pose grids, so the comparison is exactly\n")
        fh.write("# paired. 'flips' counts candidates chosen differently from the shipped maximum.\n")
        fh.write("# Free parameters were chosen on dev and frozen before these splits were scored.\n")
    print(f"\n  Wrote {args.out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
