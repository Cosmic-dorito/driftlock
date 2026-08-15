#!/usr/bin/env python3
"""Is there periodic structure ABOVE the primitive lattice — a supercell?

    python scripts/supercell.py

The whole difficulty of this problem is that one cell looks like every other. If the array were
secretly ``A B A C A B A D`` rather than ``A A A A``, then a site would carry a *context* even
though the cell does not, and identity would be readable from structure rather than from the
aperiodic fingerprint that sits near the noise floor. That would attack the failure mechanism
without inventing a new final score, which is the one shape of idea this project has not exhausted.

It is also cheap enough that not measuring it would be indefensible: one FFT-based autocorrelation
per image and a look at how the peak heights behave.

THE STATISTIC. Along each lattice axis, correlate the image with itself displaced by ``k`` primitive
periods, for k = 1..K. In a plain lattice ``r(k)`` decays smoothly - the further you slide, the less
the aperiodic content agrees. A supercell of order N adds a *modulation*: ``r(k)`` is systematically
higher whenever ``k`` is a multiple of N, because those displacements land on the same cell type.

So the question is not "are there peaks at multiples of the period" - there always are. It is
whether ``r(k)`` carries periodic structure of its own once the decay is removed. That is answered
by the spectrum of the detrended ``r(k)``, tested against the largest modulation an aperiodic array
produces by chance.

WHAT THE GENERATOR SAYS TO EXPECT. Line positions are laid down as a random walk
(``pos += pitch + N(0, 1.5 nm)``, H7 - empirically confirmed), and a random walk has no repeating
motif. So the honest prior is that there is NO supercell and this measurement will say so. It is run
anyway because the sponsor's evaluation data is not ours, because H7 was confirmed on the published
generator rather than on the held-out set, and because this project has already paid once for
treating a plausible argument as a measurement (FINDINGS 37).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.driftlock.io import (  # noqa: E402
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
)

SPLITS = {
    "sponsor": "data/_sponsor/verify",
    "bench": "data/bench",
    "finfet": "data/holdout_finfet",
}
MAX_MULTIPLE = 24            # how many primitive periods to slide before the overlap gets thin
MIN_PERIOD_PX = 3.0
# The reference is at 1 nm/px where the DRAM bit-line pitch is 96 nm, so a 60 px cap forces the
# search onto a harmonic and reports ~45 px for a 96 px lattice. The search image is the same
# structure after the 10x decimation, so one window has to span both.
MAX_PERIOD_PX = 140.0
SURROGATES = 400             # permutations used to calibrate the null


def modulation_p_value(residual: np.ndarray, observed: float,
                       rng: np.random.Generator) -> float:
    """How often does a SHUFFLED residual produce a modulation this strong?

    Without this the statistic is uninterpretable. For a 24-point series the largest of ~12 spectral
    components is naturally about one RMS, so a "modulation strength of 0.94" is the null, not a
    finding - the smoke run reported exactly that and it would have been easy to over-read.
    Permuting the residual destroys any periodic structure while preserving the value distribution
    exactly, which is the right null for "is the ORDER of these numbers periodic".
    """
    if residual.size < 8:
        return 1.0
    hits = 0
    for _ in range(SURROGATES):
        shuffled = rng.permutation(residual)
        spectrum = np.abs(np.fft.rfft(shuffled - shuffled.mean()))
        if spectrum.size < 2:
            continue
        amplitude = 2.0 * float(np.max(spectrum[1:])) / shuffled.size
        rms = float(np.sqrt(np.mean(shuffled ** 2)))
        if rms > 1e-12 and amplitude / rms >= observed:
            hits += 1
    return (hits + 1) / (SURROGATES + 1)


def primitive_period(profile: np.ndarray) -> float:
    """The dominant period of a 1D profile, by its power spectrum with a parabolic vertex."""
    work = profile - profile.mean()
    power = np.abs(np.fft.rfft(work)) ** 2
    n = work.size
    lo = max(int(np.ceil(n / MAX_PERIOD_PX)), 2)
    hi = min(int(np.floor(n / MIN_PERIOD_PX)), power.size - 1)
    if hi <= lo:
        return 0.0
    peak = int(np.argmax(power[lo:hi + 1])) + lo
    if 0 < peak < power.size - 1:
        a, b, c = (float(np.log(max(power[peak + off], 1e-30))) for off in (-1, 0, 1))
        denom = a - 2.0 * b + c
        peak = peak + (float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5)) if abs(denom) > 1e-12
                       else 0.0)
    return float(n / peak) if peak > 0 else 0.0


def shifted_correlation(image: np.ndarray, period: float, axis: int,
                        max_multiple: int = MAX_MULTIPLE) -> np.ndarray:
    """``r(k)`` = correlation of the image with itself displaced by k primitive periods.

    Whole-pixel displacements only. A sub-pixel period means the k-th displacement is off by up to
    half a pixel, which lowers every ``r(k)`` a little; it cannot manufacture a modulation with a
    period of its own, which is what is being looked for.
    """
    work = image.astype(np.float64)
    out = np.empty(max_multiple, dtype=np.float64)
    for k in range(1, max_multiple + 1):
        shift = int(round(k * period))
        if shift <= 0 or shift >= work.shape[axis]:
            out[k - 1] = np.nan
            continue
        a = np.take(work, range(0, work.shape[axis] - shift), axis=axis)
        b = np.take(work, range(shift, work.shape[axis]), axis=axis)
        a = a - a.mean()
        b = b - b.mean()
        denom = np.sqrt((a * a).sum() * (b * b).sum())
        out[k - 1] = float((a * b).sum() / denom) if denom > 1e-12 else np.nan
    return out


def modulation_strength(r: np.ndarray) -> tuple[float, int, float, np.ndarray]:
    """Detrend r(k), then ask how strong its strongest periodic component is.

    Returns ``(strength, best order N, residual RMS, the detrended residual)``. The strength is
    the amplitude of the largest spectral component of the detrended series divided by that
    series' own RMS. It is scale-free but NOT self-calibrating: on 24 points the null sits near
    1.0, so it means nothing without :func:`modulation_p_value`.
    """
    good = np.isfinite(r)
    if good.sum() < 8:
        return 0.0, 0, 0.0, np.empty(0)
    k = np.arange(1, r.size + 1)[good]
    values = r[good]

    # A plain lattice decays smoothly with k; a quadratic in log-k removes that without being
    # flexible enough to absorb an oscillation.
    trend = np.polyval(np.polyfit(np.log(k), values, 2), np.log(k))
    residual = values - trend
    rms = float(np.sqrt(np.mean(residual ** 2)))
    if rms < 1e-12:
        return 0.0, 0, 0.0, residual

    spectrum = np.abs(np.fft.rfft(residual - residual.mean()))
    if spectrum.size < 3:
        return 0.0, 0, rms, residual
    bin_index = int(np.argmax(spectrum[1:])) + 1
    amplitude = 2.0 * float(spectrum[bin_index]) / residual.size
    order = int(round(residual.size / bin_index)) if bin_index else 0
    return amplitude / rms, order, rms, residual


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--splits", default="sponsor,bench,finfet")
    ap.add_argument("--limit", type=int, default=10, help="pairs per split")
    ap.add_argument("--out", type=Path, default=Path("results/supercell.csv"))
    args = ap.parse_args()

    out_path = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    # Seeded, because a p-value that moves between runs is not a p-value.
    rng = np.random.default_rng(20260815)
    rows: list[dict] = []

    for split in [s.strip() for s in args.splits.split(",") if s.strip()]:
        if split not in SPLITS:
            sys.exit(f"unknown split {split!r}")
        manifest = REPO_ROOT / SPLITS[split] / "manifest.csv"
        if not manifest.exists():
            sys.exit(f"missing {manifest.relative_to(REPO_ROOT).as_posix()}")

        for rec in list(read_manifest(manifest))[:args.limit]:
            for which, column in (("reference", "reference_path"), ("search", "search_path")):
                image = load_grayscale(resolve_manifest_path(manifest, rec[column]))
                for axis, name in ((0, "y"), (1, "x")):
                    # Profile along the OTHER axis, so the period measured is the one this axis
                    # will be slid along.
                    profile = image.astype(np.float64).mean(axis=1 - axis)
                    period = primitive_period(profile)
                    if not (MIN_PERIOD_PX <= period <= MAX_PERIOD_PX):
                        continue
                    r = shifted_correlation(image, period, axis)
                    strength, order, rms, residual = modulation_strength(r)
                    p_value = modulation_p_value(residual, strength, rng)
                    rows.append({
                        "split": split, "id": rec["id"], "image": which, "axis": name,
                        "period_px": round(period, 3),
                        "r_1": round(float(r[0]), 4) if np.isfinite(r[0]) else "",
                        "r_last": round(float(r[-1]), 4) if np.isfinite(r[-1]) else "",
                        "modulation_strength": round(strength, 4),
                        "best_order": order,
                        "p_value": round(p_value, 4),
                        "residual_rms": round(rms, 5),
                    })

    if not rows:
        sys.exit("no usable images - nothing measured")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        for line in [
            "# r(k) is the self-correlation of the image displaced by k primitive periods.",
            "# modulation_strength is the amplitude of the strongest periodic component of the",
            "# DETRENDED r(k), divided by that series' RMS. A real supercell of order N shows a",
            "# strength near 1 with best_order stable at N across images. Values scattered near the",
            "# noise floor with best_order jumping around mean there is no higher-order period -",
            "# which is what a random-walk line placement (H7) predicts.",
        ]:
            fh.write(line + "\n")

    print(f"\n  {'split':<9}{'image':<11}{'axis':<6}{'n':>4}{'period':>9}"
          f"{'r(1)':>8}{'r(24)':>8}{'modulation':>12}{'orders':>16}")
    print("  " + "-" * 84)
    for split in sorted({r["split"] for r in rows}):
        for which in ("reference", "search"):
            for axis in ("y", "x"):
                sub = [r for r in rows if r["split"] == split and r["image"] == which
                       and r["axis"] == axis]
                if not sub:
                    continue
                strengths = [r["modulation_strength"] for r in sub]
                orders = sorted({r["best_order"] for r in sub})
                print(f"  {split:<9}{which:<11}{axis:<6}{len(sub):>4}"
                      f"{np.median([r['period_px'] for r in sub]):>9.2f}"
                      f"{np.median([r['r_1'] for r in sub if r['r_1'] != '']):>8.3f}"
                      f"{np.median([r['r_last'] for r in sub if r['r_last'] != '']):>8.3f}"
                      f"{np.median(strengths):>12.3f}"
                      f"{str(orders[:4]):>16}")

    all_strength = [r["modulation_strength"] for r in rows]
    stable = len({r["best_order"] for r in rows}) <= 3
    print("  " + "-" * 84)
    print(f"\n  median modulation strength over {len(rows)} measurements: "
          f"{np.median(all_strength):.3f}")
    print(f"  distinct best orders: {len({r['best_order'] for r in rows})} "
          f"({'stable - investigate' if stable else 'scattered - no supercell'})")
    print(f"\n  Wrote {out_path.relative_to(REPO_ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
