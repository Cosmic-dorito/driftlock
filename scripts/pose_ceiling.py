#!/usr/bin/env python3
"""The pose ceiling: at the generator's EXACT pose, is the true site even recoverable?

    python scripts/pose_ceiling.py

Every remaining failure had been treated as a SELECTION error, on the unexamined assumption that the
true site would win if only it were scored better. Selection operates on templates built at an
ESTIMATED pose, so the assumption is testable: hand the matcher the generator's own recorded
``scale_ratio`` and ``rotation_deg`` and see what survives.

WHY THIS SCRIPT EXISTS. FINDINGS 35 and 36 were the submission's headline argument and they lived
only as prose - measured once in a scratchpad file that was later overwritten, never written into
``results/``. Writing them down properly re-measured them, and the winner side did not come back:
the published figure turned out to be the MAXIMUM of the correlation surface rather than the score
at the location the pipeline chose. A maximum over ~810,000 positions exceeds any nominated point
almost by construction, so that comparison was upward-biased and merely restated 35a. Retraction and
corrected numbers: FINDINGS 37. The lesson is the reason this file is committed - **a result with no
script is not a result.**

What the corrected measurement says: at the exact pose the true site (0.7661) and the site the
pipeline chose (0.7696) are statistically indistinguishable - the truth is ahead in 7 of 15. The
margin between them is about 0.01 of correlation, which is why six re-ranking criteria failed to
resolve it.

Part two (FINDINGS 36) asks the natural follow-up: is the refit silently compensating for physics
the forward model is missing? Three degrees of freedom are added as ORACLES - never in the pipeline -
and scored as a DIFFERENTIAL, truth minus winner. A gain that lifts both candidates equally changes
no decision and is worth nothing.

BOTH SIDES OF EVERY COMPARISON HERE ARE NOMINATED THE SAME WAY. That is not a stylistic preference;
it is the whole content of the correction above.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from math import comb
from pathlib import Path

import cv2
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
from src.driftlock.match import (  # noqa: E402
    build_template,
    correlation_surface,
    integrate_reference,
    localize,
)

NEAR_PX = 5.0
SPLITS = {"sponsor": "data/_sponsor/verify", "bench": "data/bench",
          "finfet": "data/holdout_finfet"}

# Captured from the pipeline's own refit, so the poses analysed here are the ones it actually used.
CAPTURED: dict = {}
_refit_candidates = refit_mod.refit_candidates


def _capturing_refit(search, reference, candidates, bt, cs, config):
    out = _refit_candidates(search, reference, candidates, bt, cs, config)
    CAPTURED["final"] = [(c.x, c.y, c.score, c.scale, c.rotation_deg) for c in out[:10]]
    return out


refit_mod.refit_candidates = _capturing_refit


# ---------------------------------------------------------------------------------------
# Correlation helpers
# ---------------------------------------------------------------------------------------

def zncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / denom) if denom > 1e-9 else 0.0


def patch_at(search: np.ndarray, x: float, y: float, size: int) -> np.ndarray | None:
    """The size x size window centred on (x, y), or None if it runs off the image."""
    y0, x0 = int(round(y - size / 2.0)), int(round(x - size / 2.0))
    if not (y0 >= 0 and y0 + size <= search.shape[0] and x0 >= 0 and x0 + size <= search.shape[1]):
        return None
    return search[y0:y0 + size, x0:x0 + size].astype(np.float32)


def score_at(search: np.ndarray, template: np.ndarray, x: float, y: float) -> float | None:
    patch = patch_at(search, x, y, template.shape[0])
    return None if patch is None else zncc(template, patch)


def sign_test(wins: int, n: int) -> float:
    """Exact two-sided binomial p, for the paired 'which candidate is better' counts."""
    if n == 0:
        return 1.0
    tail = min(wins, n - wins)
    return min(1.0, 2.0 * sum(comb(n, i) for i in range(tail + 1)) / 2 ** n)


# ---------------------------------------------------------------------------------------
# The three added degrees of freedom (FINDINGS 36) - oracles, never pipeline stages
# ---------------------------------------------------------------------------------------

def gain_psf(ref: np.ndarray, patch: np.ndarray, scale: float, rot: float,
             base: float) -> tuple[float, float]:
    """36a. The reference is rendered sharper than the search image. Sweep a blur over it.

    If the template is systematically too sharp, correlation may prefer a wrong site whose texture
    happens to suit that sharpness. Returns (best gain over the unblurred template, best sigma).
    """
    best, best_sigma = base, 0.0
    for sigma in (0.15, 0.30, 0.45, 0.60, 0.80, 1.05):
        blurred = cv2.GaussianBlur(ref, (0, 0), sigmaX=sigma, sigmaY=sigma,
                                   borderType=cv2.BORDER_REFLECT)
        value = zncc(build_template(blurred, scale, rot, out_size=patch.shape[0]), patch)
        if value > best:
            best, best_sigma = value, sigma
    return best - base, best_sigma


def warp_template(integrated: np.ndarray, scale: float, rot: float, out_size: int,
                  aniso: float, shear: float) -> np.ndarray:
    """The shipped forward model plus anisotropic scale and shear, as one affine.

    At ``aniso = shear = 0`` this reproduces ``build_template`` exactly (checked to
    max |difference| = 0.000000), so the comparison isolates the added freedom and nothing else.
    """
    h, w = integrated.shape[:2]
    theta = math.radians(rot)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    sx, sy = scale * (1.0 + aniso), scale * (1.0 - aniso)
    # A = R(theta) @ [[sx, sx*shear], [0, sy]] - rotation composed with an anisotropic scale and a
    # shear of x per unit y. At aniso = shear = 0 this collapses to scale * R(theta), which is
    # exactly the shipped matrix.
    a11, a12 = cos_t * sx, cos_t * sx * shear - sin_t * sy
    a21, a22 = sin_t * sx, sin_t * sx * shear + cos_t * sy
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    uc = vc = (out_size - 1) / 2.0
    m = np.array([
        [a11, a12, cx - (a11 * uc + a12 * vc)],
        [a21, a22, cy - (a21 * uc + a22 * vc)],
    ], dtype=np.float32)
    return cv2.warpAffine(integrated, m, (out_size, out_size),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


def gain_microwarp(ref: np.ndarray, patch: np.ndarray, scale: float, rot: float,
                   base: float) -> tuple[float, float]:
    """36b. Anisotropic scale plus shear on top of the rigid pose.

    A low-order stand-in for smooth acquisition distortion the rigid model cannot express.
    """
    integrated = integrate_reference(ref, scale)
    out_size = patch.shape[0]
    best, best_mag = base, 0.0
    for aniso in (-0.004, -0.002, 0.0, 0.002, 0.004):
        for shear in (-0.004, -0.002, 0.0, 0.002, 0.004):
            if aniso == 0.0 and shear == 0.0:
                continue
            value = zncc(warp_template(integrated, scale, rot, out_size, aniso, shear), patch)
            if value > best:
                best, best_mag = value, math.hypot(aniso, shear)
    return best - base, best_mag


def gain_linejitter(template: np.ndarray, patch: np.ndarray, base: float) -> tuple[float, float]:
    """36c. Undo the generator's per-row shear and jitter on the PATCH before correlating.

    The pipeline's drift stage corrects the reported coordinate, not the image, so the template is
    correlated against a patch that is still geometrically distorted. Estimated blind: per-row
    horizontal offset by 1D correlation against the corresponding template row, then a QUADRATIC fit
    in y - a scan-drift prior, three degrees of freedom - so noise cannot drive individual rows.
    """
    h, w = patch.shape
    max_lag = 2
    offsets = np.zeros(h, dtype=np.float64)
    for row in range(h):
        t_row = template[row] - template[row].mean()
        best_lag, best_val = 0, -2.0
        for lag in range(-max_lag, max_lag + 1):
            shifted = np.roll(patch[row], -lag)
            if lag > 0:
                shifted = shifted[:-lag] if lag < w else shifted
                t_cmp = t_row[:len(shifted)]
            elif lag < 0:
                shifted = shifted[-lag:]
                t_cmp = t_row[:len(shifted)]
            else:
                t_cmp = t_row
            s = shifted - shifted.mean()
            denom = math.sqrt(float((t_cmp * t_cmp).sum()) * float((s * s).sum()))
            val = float((t_cmp * s).sum() / denom) if denom > 1e-9 else 0.0
            if val > best_val:
                best_lag, best_val = lag, val
        offsets[row] = best_lag

    ys = np.arange(h, dtype=np.float64)
    fitted = np.clip(np.polyval(np.polyfit(ys, offsets, 2), ys), -2.0, 2.0)

    corrected = np.empty_like(patch)
    for row in range(h):
        m = np.array([[1.0, 0.0, -fitted[row]], [0.0, 1.0, 0.0]], dtype=np.float32)
        corrected[row] = cv2.warpAffine(patch[row][None, :], m, (w, 1),
                                        flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_REFLECT)[0]
    return zncc(template, corrected) - base, float(np.abs(fitted).max())


# ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "results" / "pose_ceiling.csv")
    args = ap.parse_args()

    cfg = L.build_config(argparse.Namespace(config="driftlock"))

    n_pairs = shipped_ok = oracle_ok = 0
    oracle_rescued = oracle_broke = 0
    # 35b: at the exact GT pose, how does the truth's correlation compare with the winner's?
    fixed_truth: list[float] = []
    fixed_winner: list[float] = []
    # 35c / 36: the paired subset - failures where the truth IS a candidate, so both sides have a
    # refitted pose and the same pair can be measured before and after.
    paired: list[dict] = []

    for split, folder in SPLITS.items():
        manifest = REPO_ROOT / folder / "manifest.csv"
        if not manifest.exists():
            sys.exit(f"missing {manifest.relative_to(REPO_ROOT).as_posix()}")
        for rec in read_manifest(manifest):
            gt_x, gt_y = float(rec["gt_x"]), float(rec["gt_y"])
            ref = load_grayscale(resolve_manifest_path(manifest, rec["reference_path"]))
            search = load_grayscale(resolve_manifest_path(manifest, rec["search_path"]))
            searchf = search.astype(np.float32)
            reff = ref.astype(np.float32)

            CAPTURED.clear()
            match = localize(ref, search, cfg)
            n_pairs += 1
            correct = math.hypot(match.x - gt_x, match.y - gt_y) <= NEAR_PX
            shipped_ok += correct

            # --- 35a: the generator's own pose, then one plain correlation, nothing else ---
            scale = float(rec.get("scale_ratio") or 10.0)
            rot = float(rec.get("rotation_deg") or 0.0)
            oracle_tpl = build_template(reff, scale, rot)
            surface = correlation_surface(searchf, oracle_tpl)
            _, _, _, loc = cv2.minMaxLoc(surface)
            size = oracle_tpl.shape[0]
            ox, oy = loc[0] + size / 2.0, loc[1] + size / 2.0
            o_correct = math.hypot(ox - gt_x, oy - gt_y) <= NEAR_PX
            oracle_ok += o_correct
            oracle_rescued += (o_correct and not correct)
            oracle_broke += (correct and not o_correct)

            if correct:
                continue

            # --- 35b: truth against the shipped answer, both at the exact GT pose ---
            s_truth = score_at(searchf, oracle_tpl, gt_x, gt_y)
            s_winner = score_at(searchf, oracle_tpl, match.x, match.y)
            if s_truth is not None and s_winner is not None:
                fixed_truth.append(s_truth)
                fixed_winner.append(s_winner)

            # --- 35c / 36: only where the truth survived to the final comparison ---
            final = CAPTURED.get("final") or []
            t_idx = next((i for i, c in enumerate(final)
                          if math.hypot(c[0] - gt_x, c[1] - gt_y) <= NEAR_PX), -1)
            if t_idx <= 0:
                continue
            t_cand, w_cand = final[t_idx], final[0]
            f_truth = score_at(searchf, oracle_tpl, t_cand[0], t_cand[1])
            f_winner = score_at(searchf, oracle_tpl, w_cand[0], w_cand[1])
            if f_truth is None or f_winner is None:
                continue

            row: dict = {
                "split": split, "id": rec["id"],
                "fixed_pose_truth": f_truth, "fixed_pose_winner": f_winner,
                "refit_truth": t_cand[2], "refit_winner": w_cand[2],
            }

            # 36: each candidate is given the extra freedom at its OWN refitted pose.
            for who, cand in (("truth", t_cand), ("winner", w_cand)):
                _x, _y, base, c_scale, c_rot = cand
                tpl = build_template(reff, c_scale, c_rot)
                patch = patch_at(searchf, _x, _y, tpl.shape[0])
                if patch is None:
                    row = {}
                    break
                base_here = zncc(tpl, patch)
                g_psf, sigma = gain_psf(reff, patch, c_scale, c_rot, base_here)
                g_warp, _mag = gain_microwarp(reff, patch, c_scale, c_rot, base_here)
                g_jit, _amp = gain_linejitter(tpl, patch, base_here)
                row[f"psf_gain_{who}"] = g_psf
                row[f"psf_sigma_{who}"] = sigma
                row[f"warp_gain_{who}"] = g_warp
                row[f"jitter_gain_{who}"] = g_jit
            if row:
                paired.append(row)

    if not paired:
        sys.exit("no paired failures found - nothing to measure")

    # ------------------------------------------------------------------ summarise
    n_fix = len(fixed_truth)
    truth_wins_fixed = sum(1 for a, b in zip(fixed_truth, fixed_winner) if a > b)
    n_pair = len(paired)

    def mean(key: str) -> float:
        return float(np.mean([r[key] for r in paired]))

    deficit_fixed = mean("fixed_pose_winner") - mean("fixed_pose_truth")
    deficit_refit = mean("refit_winner") - mean("refit_truth")
    closed = (1.0 - deficit_refit / deficit_fixed) if deficit_fixed else 0.0
    reduced = sum(1 for r in paired
                  if (r["refit_winner"] - r["refit_truth"])
                  < (r["fixed_pose_winner"] - r["fixed_pose_truth"]))

    dof = []
    for name, key in (("psf blur", "psf"), ("anisotropic scale + shear", "warp"),
                      ("line-jitter, quadratic in y", "jitter")):
        g_t, g_w = mean(f"{key}_gain_truth"), mean(f"{key}_gain_winner")
        wins = sum(1 for r in paired if r[f"{key}_gain_truth"] > r[f"{key}_gain_winner"])
        dof.append((name, key, g_t, g_w, g_t - g_w, wins, sign_test(wins, n_pair)))

    rows = [
        ("n_pairs", n_pairs, "pairs across all three splits"),
        ("shipped_correct", shipped_ok, "shipped pipeline within 5 px"),
        ("oracle_pose_correct", oracle_ok, "35a: exact GT pose + plain argmax, no refit or screen"),
        ("oracle_rescued", oracle_rescued, "shipped failures the oracle pose recovers"),
        ("oracle_broke", oracle_broke, "pairs the oracle loses that the shipped pipeline gets"),
        ("n_fixed_pose", n_fix, "35b: failures where both windows fit inside the image"),
        ("zncc_truth_fixed_pose", round(float(np.mean(fixed_truth)), 4),
         "ZNCC at the TRUE location, exact GT pose"),
        ("zncc_winner_fixed_pose", round(float(np.mean(fixed_winner)), 4),
         "ZNCC at the WINNING location, exact GT pose"),
        ("truth_wins_fixed_pose", truth_wins_fixed, "of n_fixed_pose"),
        ("truth_wins_fixed_pose_p", round(sign_test(truth_wins_fixed, n_fix), 4),
         "exact two-sided sign test"),
        ("n_paired", n_pair, "35c: failures where the truth reached the final comparison"),
        ("deficit_fixed_pose", round(deficit_fixed, 4), "winner minus truth, at the exact GT pose"),
        ("deficit_after_refit", round(deficit_refit, 4), "winner minus truth, after the refit"),
        ("deficit_closed_fraction", round(closed, 4), "fraction of the deficit geometry recovers"),
        ("deficit_reduced_in", reduced, f"of {n_pair} paired failures"),
    ]
    for name, key, g_t, g_w, diff, wins, p in dof:
        rows.append((f"dof_{key}_gain_truth", round(g_t, 4), f"36: {name}, ZNCC gain for the truth"))
        rows.append((f"dof_{key}_gain_winner", round(g_w, 4), f"36: {name}, ZNCC gain for the winner"))
        rows.append((f"dof_{key}_differential", round(diff, 4),
                     f"36: {name}, truth minus winner - the only form that changes a decision"))
        rows.append((f"dof_{key}_truth_better_in", wins, f"of {n_pair}"))
        rows.append((f"dof_{key}_p", round(p, 4), "exact two-sided sign test"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value", "note"])
        writer.writerows(rows)
        writer.writerow([])
        for line in [
            "# 35a  Template built at the generator's recorded scale_ratio/rotation_deg, then one",
            "#      plain correlation over the whole search image. No pose search, refit or screen.",
            "# 35b  The same oracle template, correlated at the true location and at the location",
            "#      the shipped pipeline chose. Pose is correct by construction on both sides.",
            "# 35c  The paired subset, measured twice: at the oracle pose, and at each candidate's",
            "#      own refitted pose. The difference is what the refit contributes.",
            "# 36   Three degrees of freedom added as ORACLES, never as pipeline stages, at each",
            "#      candidate's own refitted pose. Scored as a DIFFERENTIAL: a gain that lifts both",
            "#      candidates equally changes no decision and is worth nothing.",
        ]:
            fh.write(line + "\n")

    # ------------------------------------------------------------------ report
    print(f"\n  {n_pairs} pairs")
    print(f"    shipped pipeline correct     : {shipped_ok}/{n_pairs}")
    print(f"    oracle pose + plain argmax   : {oracle_ok}/{n_pairs}"
          f"   (rescues {oracle_rescued}, loses {oracle_broke})")
    print(f"\n  35b  at the exact GT pose, on {n_fix} failures")
    print(f"    ZNCC at the TRUE location    : {np.mean(fixed_truth):.4f}")
    print(f"    ZNCC at the WINNING location : {np.mean(fixed_winner):.4f}")
    print(f"    truth out-correlates winner  : {truth_wins_fixed}/{n_fix}"
          f"   p = {sign_test(truth_wins_fixed, n_fix):.3f}")
    print(f"\n  35c  paired on {n_pair} failures            deficit = winner - truth")
    print(f"    at the exact GT pose         : {deficit_fixed:+.4f}")
    print(f"    after the per-candidate refit: {deficit_refit:+.4f}")
    print(f"    the refit closes             : {100 * closed:.1f}%   (reduced in {reduced}/{n_pair})")
    print("\n  36   added freedom, differential gain (truth - winner)")
    print(f"    {'degree of freedom':<28}{'truth':>9}{'winner':>9}{'diff':>10}{'truth better':>15}")
    print("    " + "-" * 71)
    for name, _key, g_t, g_w, diff, wins, p in dof:
        print(f"    {name:<28}{g_t:>+9.4f}{g_w:>+9.4f}{diff:>+10.4f}"
              f"{f'{wins}/{n_pair}  p={p:.3f}':>15}")
    print(f"\n  Wrote {args.out.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
