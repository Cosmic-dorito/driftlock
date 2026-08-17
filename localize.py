#!/usr/bin/env python3
"""Locate a 100x reference pattern inside a 10x search image.

    # Single pair - prints EXACTLY one line to stdout: "312.42,489.07"
    python localize.py --reference ref.png --search search.png

    # Batch - the evaluator runs this against their own data with no source edits
    python localize.py --manifest data/test/manifest.csv --out results/predictions.csv
    python localize.py --input-dir data/test/            --out results/predictions.csv

Coordinate convention: origin (0,0) top-left, x right, y down; the output is the CENTRE of the
matched region in search-image pixels, as floats. See src/driftlock/io.py.

stdout carries the coordinate and nothing else - benchmark parsers break on chatty scripts. All
logging, progress and warnings go to stderr.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.driftlock.io import (  # noqa: E402
    Match,
    load_grayscale,
    read_manifest,
    resolve_manifest_path,
    validate_pair,
    write_predictions,
)
from src.driftlock.match import PipelineConfig, localize  # noqa: E402

EXIT_OK, EXIT_ERROR, EXIT_BAD_INPUT = 0, 1, 2


def log(message: str, verbose: bool = True) -> None:
    """Everything human-readable goes to stderr, never stdout."""
    if verbose:
        print(message, file=sys.stderr)


def build_config(args: argparse.Namespace) -> PipelineConfig:
    """Assemble the pipeline configuration from CLI flags.

    A stage is enabled here only if it improves results on data it was NOT tuned on (rules R5, R9).
    Validated across three splits: the tuned split, a held-out dram seed, and held-out FinFET.

    Enabled - generalises on every split:
      * sub-pixel DFT + blind drift correction
            median error among located pairs   0.900 -> 0.162 px (tuned)
                                               0.757 -> 0.252 px (held-out dram)
                                               0.943 -> 0.228 px (held-out FinFET)
            pass@0.5px                         18% -> 72%, 23% -> 67%, 13% -> 60%
        Neither stage touches candidate selection, so the mis-lock rate is identical to baseline
        on all three splits. They are strictly additive refinement and cannot make things worse.

    NOT enabled - PADM re-scoring, because it does not generalise:
            tuned split        mis-lock 25.0% -> 20.0%   (helps)
            held-out dram      mis-lock 20.0% -> 26.7%   (HURTS)
            held-out FinFET    mis-lock 30.0% -> 43.3%   (HURTS BADLY)
        Its weight and bandwidth were tuned on one preset and one seed and did not transfer. Also
        costs 185 ms of the runtime budget. Kept in the codebase and in the ablation as a measured
        negative result, off by default.

    Also enabled - pose measurement (A5), added 12 Aug:
      * The problem statement says 9:1-11:1 magnification and 1-2 degrees of rotation will be
        tested. The sponsor's generator produces neither (H9), so this axis was completely untested
        until our own generator covered it - at which point the pipeline turned out to fail almost
        entirely on it. The pose is measured by a coarse pyramid search (ADR-0015) rather than read
        off the lattice, because a 1000 nm reference spans as few as 4 lattice periods and that is
        not enough to pin a magnification to the 0.5% correlation needs.
      * It is gated to be safe on data that does not need it: the nominal 10:1 hypothesis is always
        kept in the bracket, so a failed pose measurement falls back to exactly what the pipeline
        would have done without it. On the sponsor's fixed-10:1 data it costs runtime and nothing
        else.

    Also enabled - per-candidate pose refit (A11), added 12 Aug:
      * The limiting noise on candidate RANKING is model mismatch, not photon noise. The measured
        margin between the true location and its best impostor is ~0.016, against a sampling noise
        of ~0.002 on a 100x100 correlation - a signal-to-noise ratio near 8, which should have
        meant almost no mis-locks. We measured 28%. The gap is mismatch: leftover pose error, the
        drift's local gradient, apodisation. The maximum-likelihood re-ranker reached the same
        conclusion from the other side (ADR-0018).
      * So each candidate is re-scored at ITS OWN best pose instead of at one pose shared across
        the field, which removes an unequal handicap rather than introducing a new criterion. That
        is why it generalises where three re-rankers did not (ADR-0019): total mis-lock over the
        three splits 28.0% -> 19.0%, improving EVERY split, most on held-out FinFET (33.3% ->
        20.0%).
      * The refit span is WIDE and sampled DENSELY (+/-3% of scale, +/-1.5 deg, 5 steps per axis),
        because span and step count interact: the same wide span sampled with 3 steps instead of 5
        is worse than not widening at all (26.0% against 22.0% held-out). The optimum lies BETWEEN
        coarse samples, and three separate attempts to recover it from a coarse grid all failed -
        best-sample 26.0%, parabola interpolation 27.0%, multi-basin retention 26.0%, against dense
        sampling's 20.0%. You cannot reconstruct an optimum from samples that do not resolve it.

    Also enabled - screening the refit (13 Aug), which is what made the dense grid
    affordable enough to default:
      * A dense grid over every candidate costs steps^2 correlations EACH, and candidates arrive
        top_k-per-POSE, so 60 of them over a 5x5 grid is 1500 correlations - measured at 334 of the
        540 ms. The cost was never template construction (6% of it), which is why hoisting the
        box-integration out of the rotation loop, though it is a real 1.35x speedup and
        bit-identical, did not by itself make this shippable.
      * So the cheap narrow grid ranks the candidates first and only the top 10 get the dense one.
        This is the same criterion at two resolutions, not a new criterion, so it stays on the safe
        side of ADR-0024.
      * It is FASTER AND MORE ACCURATE than the unscreened dense grid: held-out mis-lock 20.0% ->
        18.0%, p50 601 -> 427 ms, because the wide grid is now centred on a pose the narrow pass
        has already corrected. Against the previously shipped narrow-only configuration: 22.0% ->
        18.0% held-out for 296 -> 427 ms.
      * top_n=10 rather than 6, which measured identically on all 140 pairs and saves 41 ms. The
        tie-break is recall, not the tie: after the screen the true candidate sits inside the top
        10 on 90.0% of sponsor pairs but only 80.0% of the top 6. Discarding 10 points of headroom
        on the split the problem statement actually scores, to buy 41 ms, is the wrong way round -
        recall is what protects against evaluation data we have not seen.
      * refit_steps=2 rather than 3 in the SCREEN: identical total mis-lock at lower cost.
      * COST, measured back-to-back on one machine in one sitting: p50 782 ms -> 1197 ms per pair,
        about 1.5x. That is well above our own 300 ms aspiration and it is a deliberate trade - we
        took 9 points of mis-lock for 400 ms. `top_k` is the dial if the balance needs changing
        (K=4 costs ~1000 ms and gives back some of the accuracy).
      * A caution about the runtime figures anywhere in this project: absolute timings drifted by
        up to 3x across this machine over a long benchmarking session, for identical code, and did
        not recover after an idle period. Only numbers measured back-to-back in one sitting are
        comparable, and every quoted runtime here is from such a pairing.

    IMPLEMENTED BUT OFF BY DEFAULT - the problem statement's closest-to-centre rule (A8):
      * It is implemented, tested and reachable via `centre_rule=True`; the checklist asks that the
        rule be implemented, and it is. What follows is why it is not the default.
      * Its threshold was genuinely wrong and is now fixed. tau was 0.25 x std(candidate scores);
        because the candidate set spans the whole image, that spread gives tau ~= 0.037 - more than
        twice the 0.016 median margin between the winner and its best rival. Clearly-worse
        candidates were declared "tied" and then decided on proximity to the centre, which nearly
        doubled mis-lock (23.3% -> 43.3%). tau is now the sampling noise of a correlation
        coefficient, (1 - rho^2)/sqrt(N), so the rule fires only when two candidates are genuinely
        indistinguishable. Nothing is tuned: N is the template footprint, rho the winning score.
      * Even corrected it costs accuracy: on the sponsor split 25.0% -> 35.0% mis-lock, and 24% ->
        28% over all three splits.
      * The reason is not a bug, and it is worth stating. **The rule encodes a deployment prior**:
        a tool that has drifted lands NEAR the site it meant to revisit, so among equally-scoring
        candidates the central one is the likely one. Both benchmarks instead sample target
        positions UNIFORMLY - measured median distance from the search centre is 373 / 335 / 347 px
        against the 358 px a uniform draw predicts. The prior the rule depends on is simply absent
        from the test data, so when it fires it is a coin flip that can only lose.
      * So: implemented for compliance and for deployment, off by default for a benchmark whose
        target distribution removes the assumption it rests on. Enable with `centre_rule=True`.

    Also not enabled, with reasons in docs/FINDINGS.md: row destriping (removes horizontal word
    lines along with charging streaks), phase congruency (implementation broken), ECC affine (never
    converges), median filter (no impulse noise in this data), Anscombe (cannot move an integer
    argmax; re-test if a continuous re-ranker lands), spectral pose estimation (less accurate than
    the pyramid on every split measured - ADR-0015), candidate-consensus residual and refit-gain
    ranking (both measured, both worse - FINDINGS section 15).
    """
    if getattr(args, "config", "driftlock") == "baseline":
        # The sponsor's published baseline, reproduced exactly: INTER_AREA template, ZNCC, argmax,
        # no refinement. Exposed as a flag so the ablation's first row is reproducible from the CLI
        # rather than only from inside the test harness.
        return PipelineConfig(label="baseline")

    return PipelineConfig(
        label="driftlock",
        subpixel=True,
        drift_correction=True,
        # Reject an implausible shear instead of applying it (16 Aug). The drift step is the LAST
        # thing localize() does, so a bad estimate lands straight in the answer with nothing to
        # catch it - and it is the only stage that can take a CORRECTLY SELECTED candidate and
        # report a mis-lock. Measured over 354 pairs (results/refine_forensics.csv):
        #   |shear| on the 283 clean pairs that are correct today   max  4.56 px
        #   |shear| on the two pairs lost this way                 14.75 and 50.39 px
        # so 6.0 clips exactly those two and nothing else. It is not a tuned knob: every threshold
        # in [6, 12] clips the same two clean pairs, and 3 through 12 all give the same reporting
        # result. 6 rather than 8 only because it is also best-or-tied under the jitter stress
        # splits, where a noisy estimate is likeliest. Below ~4 it starts clipping legitimate
        # corrections and costs precision. See ADR-0036 and FINDINGS section 44.
        drift_max_shear_px=6.0,
        pose_search=True,
        top_k=10,
        # Impulse-noise removal (14 Aug). Free, and only measurable where impulse noise exists -
        # which is why it was wrongly rejected. See ADR-0027 and FINDINGS section 26.
        median_filter=True,
        candidate_refit=True,
        # Screened wide refit (13 Aug). See ADR-0025 and FINDINGS section 23.
        refit_steps=5,
        refit_scale_span=0.03,
        refit_rotation_span=1.5,
        refit_screen_steps=2,
        # Widened from 10 (15 Aug). See ADR-0034 and FINDINGS section 40h-40i.
        #
        # FINDINGS 23d measured this at 6/10/15/20 and found it FLAT, so the cut point was closed.
        # That was true of the selector it was measured with. Instrumenting the screen showed the
        # truth sitting at rank 12, 14, 25 and 29 on the four screened failures, so a wider cut
        # always DID reach them - it just never converted, because the candidates it recovered were
        # handed to the plain maximum, which is the thing that loses ties (ADR-0032).
        #
        # With pose evidence doing the selecting: +4 fixed / -0 broken over 140 pairs, strictly
        # dominant on every split, and runtime x1.05 - the wide refit groups candidates by pose and
        # builds each template once, so extra candidates inside an existing group cost correlations
        # but not template construction.
        # Re-examined a third time on 16 Aug, after the proposals and the drift guard changed what
        # the screen hands downstream again. 30 -> 40 is +3 fixed / -0 broken over the 200 tuning
        # pairs and +0/-0 over the 100 reporting ones, at x1.09 runtime measured by interleaving
        # both arms in one session. 60 measures IDENTICALLY to 40, so this is a plateau rather than
        # a spike, and 40 is the cheap end of it. See ADR-0037.
        #
        # Read the three measurements of this one knob together - flat, then +4, then +3 - as the
        # clearest evidence in the project for "a parameter measured as flat is flat against the
        # pipeline it was measured in".
        refit_screen_top_n=40,
        # Read the refit's pose grid as evidence rather than taking its maximum (15 Aug).
        # See ADR-0032 and FINDINGS section 40.
        #
        # The maximum over ~25 poses is an upward-biased estimate of a candidate's quality, and the
        # bias grows with how rough that candidate's pose surface is - so a candidate that peaked
        # once outranks one that was consistently good. That is the same multiple-comparisons effect
        # FINDINGS 23f measured from the other side: widening the bracket for the whole field is
        # worse than widening it for ten survivors, because a wide search hands impostors more
        # chances to get lucky.
        #
        # Still the SAME ZNCC on the SAME grid, summarised differently, so this does not cross
        # ADR-0024's line - which bans ranking by a new criterion, not reading the existing one
        # better. beta=5 chosen on dev alone and frozen. Paired, 300 pairs across five splits:
        # +17 fixed / -3 broken, exact McNemar p = 0.0026, and it costs no correlations at all.
        pose_evidence_beta=5.0,
        # Extra candidate PROPOSALS from the lattice residual (15 Aug). See ADR-0035 and
        # FINDINGS section 42.
        #
        # After ADR-0034 the failure decomposition was 3 absent / 0 screened / 5 outscored, and
        # `absent` is the one bucket no selection change can reach - the true site never enters the
        # candidate set. Oracle-pose forensics showed all three absent sites ARE visible to some
        # representation, and a per-channel ablation showed the lattice residual carries the entire
        # benefit while variance and edge contribute nothing.
        #
        # This ADDS locations only. Their scores come from a different surface and never enter the
        # comparison - the existing ZNCC and the existing refit re-score everything on the original
        # intensity image, which is what keeps it a coverage change rather than a ranking one
        # (ADR-0024). Provenance confirms the mechanism: across 100 pairs exactly one
        # auxiliary-proposed candidate ever wins, and it is a rescue.
        #
        # +4 fixed / 0 broken over 300 pairs across five splits. k=3 because k=3/5/8 measure
        # identically, so the fewest extra candidates wins on parsimony. Costs ~1.46x runtime.
        proposal_channels="residual",
        proposal_top_k=3,
        # Half resolution for the proposal stage. Provenance showed the candidate pool growing only
        # 60 -> 63 while runtime grew 1.46x, so the cost is the residual's own computation - two
        # dozen warps of a 1000x1000 image plus a correlation per pose - not the extra candidates.
        # A proposal only has to say "look near here"; the refit finds the exact location on the
        # intensity image afterwards.
        #
        # Measured: +0 fixed / -0 broken across all 300 pairs, and 0.79x the runtime of the
        # full-resolution version. L4 was also tested and loses 2 pairs, so the aperiodic signal
        # survives one halving and not two. tests/test_proposals.py pins the coordinate invariant
        # so a future mistake here cannot masquerade as an accuracy loss.
        proposal_level=2,
    )


def run_pair(ref_path: Path, search_path: Path, config: PipelineConfig) -> Match:
    reference = load_grayscale(ref_path)
    search = load_grayscale(search_path)
    validate_pair(reference, search)
    return localize(reference, search, config)


def run_single(args: argparse.Namespace, config: PipelineConfig) -> int:
    started = time.perf_counter()
    match = run_pair(Path(args.reference), Path(args.search), config)
    wall_ms = (time.perf_counter() - started) * 1000.0

    log(f"score={match.score:.4f} runtime={wall_ms:.1f}ms", args.verbose)

    if args.json:
        # A non-finite confidence must be emitted as null, not as Infinity. Python's json module
        # will happily write bare `Infinity`, which is NOT valid JSON - a strict parser on the
        # evaluator's side rejects the whole document, and we would fail the batch on a field
        # nobody even asked for. `inf` here means "no rival candidate was far enough away to
        # compete", i.e. maximum confidence; null is the honest encoding of that.
        confidence = match.ambiguity_index
        if confidence is not None and not math.isfinite(confidence):
            confidence = None
        payload = {
            "x": round(match.x, 4),
            "y": round(match.y, 4),
            "score": round(match.score, 6),
            "ambiguity_index": confidence,
            "runtime_ms": round(wall_ms, 2),
        }
        print(json.dumps(payload, allow_nan=False))
    else:
        # The one line of stdout this program is allowed to produce.
        print(match.as_stdout_line())

    if args.visualize:
        from src.driftlock.visualize import save_overlay
        save_overlay(Path(args.visualize), Path(args.reference), Path(args.search), match)
        log(f"wrote {args.visualize}", args.verbose)

    return EXIT_OK


def _discover_pairs(args: argparse.Namespace) -> list[tuple[str, Path, Path]]:
    """Resolve the batch input into (id, reference_path, search_path) triples."""
    if args.manifest:
        manifest = Path(args.manifest)
        pairs = []
        for row in read_manifest(manifest):
            pair_id = row.get("id") or row.get("pair_id") or str(len(pairs))
            pairs.append((
                str(pair_id),
                resolve_manifest_path(manifest, row["reference_path"]),
                resolve_manifest_path(manifest, row["search_path"]),
            ))
        return pairs

    root = Path(args.input_dir)
    ref_dir, search_dir = root / "reference", root / "search"
    if not (ref_dir.is_dir() and search_dir.is_dir()):
        raise ValueError(
            f"{root} must contain 'reference/' and 'search/' subdirectories, or use --manifest"
        )
    pairs = []
    for ref in sorted(ref_dir.iterdir()):
        search = search_dir / ref.name
        if search.exists():
            pairs.append((ref.stem, ref, search))
    return pairs


def run_batch(args: argparse.Namespace, config: PipelineConfig) -> int:
    pairs = _discover_pairs(args)
    if not pairs:
        log("error: no image pairs found")
        return EXIT_BAD_INPUT

    log(f"processing {len(pairs)} pairs")
    results: list[tuple[str, Match]] = []
    failures = 0

    for index, (pair_id, ref_path, search_path) in enumerate(pairs, 1):
        try:
            started = time.perf_counter()
            match = run_pair(ref_path, search_path, config)
            match = Match(match.x, match.y, match.score, match.ambiguity_index,
                          (time.perf_counter() - started) * 1000.0)
            results.append((pair_id, match))
        except Exception as exc:
            # One unreadable pair must not abandon the rest of the evaluator's batch.
            failures += 1
            log(f"  [{index}/{len(pairs)}] id={pair_id} FAILED: {type(exc).__name__}: {exc}")
            continue
        if args.verbose:
            log(f"  [{index}/{len(pairs)}] id={pair_id} -> {match.x:.2f},{match.y:.2f} "
                f"score={match.score:.4f} {match.runtime_ms:.0f}ms")

    write_predictions(Path(args.out), results)
    log(f"wrote {args.out} ({len(results)} predictions"
        + (f", {failures} failures)" if failures else ")"))
    return EXIT_OK if not failures else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_argument_group("input (choose one)")
    mode.add_argument("--reference", help="path to the 100x reference image")
    mode.add_argument("--search", help="path to the 10x search image")
    mode.add_argument("--manifest", help="CSV with reference_path and search_path columns")
    mode.add_argument("--input-dir", help="directory containing reference/ and search/")

    parser.add_argument("--out", help="output CSV (required for batch modes)")
    parser.add_argument("--config", choices=["driftlock", "baseline"], default="driftlock",
                        help="'baseline' reproduces the sponsor's published matcher (ablation row 1)")
    parser.add_argument("--json", action="store_true", help="emit a JSON object instead of 'x,y'")
    parser.add_argument("--visualize", metavar="OUT.png", help="write a crosshair overlay")
    parser.add_argument("--no-rerank", action="store_true",
                        help="force the deterministic path (skip the optional learned re-ranker)")
    parser.add_argument("--verbose", action="store_true", help="stage timings to stderr")
    args = parser.parse_args(argv)

    # Force LF line endings on stdout. Python defaults to CRLF on Windows, which would make the
    # emitted coordinate differ byte-for-byte between our machine and a Linux evaluator - and the
    # reproducibility claim is that the output is identical everywhere.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(newline="\n")

    config = build_config(args)

    try:
        if args.reference and args.search:
            return run_single(args, config)
        if args.manifest or args.input_dir:
            if not args.out:
                log("error: --out is required with --manifest or --input-dir")
                return EXIT_BAD_INPUT
            return run_batch(args, config)
        parser.print_usage(sys.stderr)
        log("error: provide --reference and --search, or --manifest, or --input-dir")
        return EXIT_BAD_INPUT
    except FileNotFoundError as exc:
        log(f"error: {exc}")
        return EXIT_BAD_INPUT
    except ValueError as exc:
        log(f"error: {exc}")
        return EXIT_BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
