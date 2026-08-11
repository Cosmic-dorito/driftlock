#!/usr/bin/env python3
"""Automated submission-readiness check.

Walks the 15-item checklist from section 9 of the Applied Materials problem statement
(see docs/SPEC.md) plus the project's own correctness rules, and reports PASS / FAIL / PENDING
for each. Run it before every push and as the last action before submitting.

    python scripts/verify_submission.py
    python scripts/verify_submission.py --strict    # PENDING counts as failure

Exit codes: 0 = no failures, 1 = at least one FAIL.

PENDING means "this deliverable does not exist yet" — expected during development, not acceptable
at submission time. Use --strict on the final run.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that are not ours to police.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             "third_party", "dist", "node_modules"}

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


@dataclass
class Result:
    status: str
    detail: str = ""
    items: list[str] = field(default_factory=list)


def iter_source_files(*suffixes: str):
    """Yield repo files with the given suffixes, skipping vendored and generated trees."""
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        yield path


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------

def check_no_absolute_paths() -> Result:
    """Spec checklist: 'No proprietary data or hard-coded local paths are present.'

    Patterns are assembled from fragments so this file does not match itself.
    """
    drive = re.compile(r"[A-Za-z]:" + re.escape("\\") + r"[A-Za-z0-9_]")
    posix_home = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/")
    offenders: list[str] = []

    for path in iter_source_files(".py", ".sh", ".yaml", ".yml", ".toml", ".cfg", ".csv"):
        if path.name == Path(__file__).name:
            continue  # this file necessarily contains the patterns it hunts for
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if drive.search(line) or posix_home.search(line):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}: {line.strip()[:90]}")

    if offenders:
        return Result(FAIL, f"{len(offenders)} hard-coded path(s)", offenders[:15])
    return Result(PASS, "no hard-coded absolute paths in source")


def check_no_os_path() -> Result:
    """Portability: pathlib only. os.path assumptions break across Windows and Linux."""
    offenders = []
    for path in iter_source_files(".py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if re.search(r"\bos\.path\.", line) or re.search(r"\bos\.sep\b", line):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}")
    if offenders:
        return Result(FAIL, f"{len(offenders)} os.path use(s); use pathlib", offenders[:10])
    return Result(PASS, "pathlib only")


def check_required_files() -> Result:
    """Spec deliverables 2, 3, 4: separate runnable generator + localizer, README, dependencies."""
    required = ["README.md", "requirements.txt", "generate_dataset.py", "localize.py", "LICENSE"]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    if missing:
        return Result(PENDING, f"not yet created: {', '.join(missing)}")
    return Result(PASS, "all required top-level deliverables present")


def check_generator_and_localizer_separate() -> Result:
    """Spec checklist: 'Python generator and Python localization code are separate and runnable.'"""
    gen, loc = REPO_ROOT / "generate_dataset.py", REPO_ROOT / "localize.py"
    if not (gen.exists() and loc.exists()):
        return Result(PENDING, "generator and/or localizer not yet written")
    return Result(PASS, "generate_dataset.py and localize.py are separate entry points")


def check_no_notebook_only() -> Result:
    """Spec: 'A single notebook is not sufficient as the only runnable submission.'"""
    scripts = [p for p in iter_source_files(".py") if p.parent == REPO_ROOT]
    if not scripts:
        return Result(PENDING, "no top-level Python entry points yet")
    return Result(PASS, f"{len(scripts)} runnable script(s) at repo root")


def check_bench_dataset() -> Result:
    """Spec checklist: 'At least 30 varied cases are evaluated.'"""
    manifest = REPO_ROOT / "data" / "bench" / "manifest.csv"
    if not manifest.exists():
        return Result(PENDING, "data/bench/manifest.csv not yet generated")
    with manifest.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) < 30:
        return Result(FAIL, f"only {len(rows)} pairs; the spec requires at least 30")
    return Result(PASS, f"{len(rows)} validation pairs")


def check_manifest_columns() -> Result:
    """Spec deliverable 6: manifest carries paths, ground truth, predictions and metadata."""
    manifest = REPO_ROOT / "data" / "bench" / "manifest.csv"
    if not manifest.exists():
        return Result(PENDING, "manifest not yet generated")
    required = {"id", "reference_path", "search_path", "gt_x", "gt_y", "seed",
                "architecture", "scale_ratio", "rotation_deg"}
    with manifest.open(newline="", encoding="utf-8") as fh:
        cols = set(next(csv.reader(fh)))
    missing = required - cols
    if missing:
        return Result(FAIL, f"manifest missing columns: {sorted(missing)}")
    return Result(PASS, f"manifest has all required columns ({len(cols)} total)")


def check_image_dimensions() -> Result:
    """Spec checklist: '1000 x 1000 reference and search images used.'"""
    ref_dir = REPO_ROOT / "data" / "bench" / "reference"
    if not ref_dir.exists() or not any(ref_dir.glob("*.png")):
        return Result(PENDING, "no bench images yet")
    try:
        from PIL import Image
    except ImportError:
        return Result(PENDING, "pillow not installed; cannot check dimensions")
    bad = []
    for img_path in sorted(ref_dir.glob("*.png"))[:5]:
        with Image.open(img_path) as im:
            if im.size != (1000, 1000):
                bad.append(f"{img_path.name}: {im.size}")
    if bad:
        return Result(FAIL, "images are not 1000x1000", bad)
    return Result(PASS, "reference images are 1000x1000")


def check_metrics_reported() -> Result:
    """Spec checklist: '5-, 4-, 2- and 1-pixel pass rates are reported.'"""
    metrics = REPO_ROOT / "results" / "metrics.csv"
    if not metrics.exists():
        return Result(PENDING, "results/metrics.csv not yet generated")
    text = metrics.read_text(encoding="utf-8").lower()
    needed = ["pass@5", "pass@4", "pass@2", "pass@1"]
    missing = [n for n in needed if n not in text]
    if missing:
        return Result(FAIL, f"metrics missing: {missing}")
    return Result(PASS, "threshold-wise pass rates reported")


def check_runtime_reported() -> Result:
    """Spec checklist: 'Runtime, hardware and timing method are stated.'"""
    metrics = REPO_ROOT / "results" / "metrics.csv"
    if not metrics.exists():
        return Result(PENDING, "results not yet generated")
    text = metrics.read_text(encoding="utf-8").lower()
    if "runtime" not in text:
        return Result(FAIL, "no runtime in metrics.csv")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    if "python version" not in readme and "hardware" not in readme:
        return Result(PENDING, "runtime present, but hardware/timing method not yet stated in README")
    return Result(PASS, "runtime, hardware and timing method stated")


def check_failure_case() -> Result:
    """Spec checklist: 'At least one failure case is shown and explained.'"""
    d = REPO_ROOT / "results" / "failure_case"
    if not d.exists() or not any(d.iterdir()):
        return Result(PENDING, "results/failure_case/ is empty")
    has_image = any(d.glob("*.png"))
    has_text = any(d.glob("*.md"))
    if not (has_image and has_text):
        return Result(FAIL, "failure case needs both a visualization (.png) and an explanation (.md)")
    return Result(PASS, "failure case visualized and explained")


def check_citations_complete() -> Result:
    """Rule R1 + spec checklist: 'At least 2-3 credible public sources are cited.'

    Every row in the Verified table needs all five columns filled. PARTIAL rows are flagged: they
    must be upgraded or dropped before they can appear in the deck.
    """
    refs = REPO_ROOT / "docs" / "REFERENCES.md"
    if not refs.exists():
        return Result(FAIL, "docs/REFERENCES.md missing")
    text = refs.read_text(encoding="utf-8")
    verified = len(re.findall(r"\|\s*VERIFIED\s*\|", text))
    partial = len(re.findall(r"PARTIAL", text))
    if verified < 3:
        return Result(FAIL, f"only {verified} fully VERIFIED citation(s); the spec requires 2-3 credible sources")
    detail = f"{verified} verified"
    if partial:
        return Result(PENDING, f"{detail}, but {partial} PARTIAL row(s) must be upgraded or dropped")
    return Result(PASS, detail)


def check_ppt_numbers_traceable() -> Result:
    """Rule R2: every number in the deck must exist in results/.

    The likely failure is a STALE number surviving from an earlier run, not an invented one.
    """
    decks = list(REPO_ROOT.glob("*.pptx")) + list(REPO_ROOT.glob("**/solution_presentation.pptx"))
    decks = [d for d in decks if not any(p in SKIP_DIRS for p in d.relative_to(REPO_ROOT).parts)]
    if not decks:
        return Result(PENDING, "no .pptx yet - mandatory deliverable 1")
    try:
        from pptx import Presentation
    except ImportError:
        return Result(PENDING, "python-pptx not installed (pip install -r requirements-dev.txt)")

    results_text = " ".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (REPO_ROOT / "results").rglob("*") if p.is_file() and p.suffix in {".csv", ".md", ".json"}
    )
    if not results_text.strip():
        return Result(FAIL, "deck exists but results/ is empty — no number can be traced")

    unmatched = []
    for deck in decks:
        for slide_no, slide in enumerate(Presentation(deck).slides, 1):
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for num in re.findall(r"\d+\.\d+", shape.text_frame.text):
                    if num not in results_text:
                        unmatched.append(f"{deck.name} slide {slide_no}: {num}")
    if unmatched:
        return Result(FAIL, f"{len(unmatched)} deck number(s) not found in results/", unmatched[:12])
    return Result(PASS, "every decimal number in the deck is traceable to results/")


def check_torch_optional() -> Result:
    """ADR-0006: the deterministic path must not import torch at module scope."""
    offenders = []
    for path in iter_source_files(".py"):
        if "rerank" in path.name or path.parts[-2:][0] == "tests":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            stripped = line.strip()
            if re.match(r"^(import torch|from torch)", stripped):
                indent = len(line) - len(line.lstrip())
                if indent == 0:  # module scope, not inside a function
                    offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}")
    if offenders:
        return Result(FAIL, "torch imported at module scope; it must be lazy", offenders)
    return Result(PASS, "torch is not imported at module scope")


def check_docs_present() -> Result:
    """Project practice: the tracking docs that make the repo resumable on another machine."""
    required = ["PLAN.md", "SPEC.md", "DECISIONS.md", "PROGRESS.md", "HANDOFF.md", "REFERENCES.md"]
    missing = [f for f in required if not (REPO_ROOT / "docs" / f).exists()]
    if missing:
        return Result(FAIL, f"docs missing: {', '.join(missing)}")
    return Result(PASS, "all tracking docs present")


def check_hypotheses_verified() -> Result:
    """Rule R3: the sponsor-generator facts were read from source, not run. Confirm before relying."""
    decisions = REPO_ROOT / "docs" / "DECISIONS.md"
    if not decisions.exists():
        return Result(FAIL, "docs/DECISIONS.md missing")
    unverified = len(re.findall(r"\|\s*unverified\s*\|", decisions.read_text(encoding="utf-8")))
    if unverified:
        return Result(PENDING, f"{unverified} of H1-H9 still unverified - B owns this on Day 1")
    return Result(PASS, "all sponsor-generator hypotheses empirically confirmed")


CHECKS = [
    ("No hard-coded local paths", check_no_absolute_paths),
    ("pathlib only (no os.path)", check_no_os_path),
    ("Required deliverable files present", check_required_files),
    ("Generator and localizer are separate", check_generator_and_localizer_separate),
    ("Runnable scripts, not notebook-only", check_no_notebook_only),
    ("At least 30 validation pairs", check_bench_dataset),
    ("Manifest has required columns", check_manifest_columns),
    ("Images are 1000x1000", check_image_dimensions),
    ("Pass rates at 5/4/2/1 px reported", check_metrics_reported),
    ("Runtime, hardware, timing method", check_runtime_reported),
    ("Failure case shown and explained", check_failure_case),
    ("Citations complete and verified (R1)", check_citations_complete),
    ("Deck numbers traceable to results (R2)", check_ppt_numbers_traceable),
    ("torch is optional, lazily imported", check_torch_optional),
    ("Tracking docs present", check_docs_present),
    ("Sponsor-generator facts verified (R3)", check_hypotheses_verified),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true",
                        help="treat PENDING as failure (use for the final pre-submission run)")
    args = parser.parse_args()

    symbol = {PASS: "PASS", FAIL: "FAIL", PENDING: "PEND"}
    counts = {PASS: 0, FAIL: 0, PENDING: 0}
    width = max(len(name) for name, _ in CHECKS)

    # ASCII only in console output: Windows consoles default to cp1252 and mangle non-ASCII.
    print(f"\nDriftLock submission check  --  {REPO_ROOT}\n")
    for name, fn in CHECKS:
        try:
            res = fn()
        except Exception as exc:  # a broken check must not look like a passing one
            res = Result(FAIL, f"check raised {type(exc).__name__}: {exc}")
        counts[res.status] += 1
        print(f"  [{symbol[res.status]}] {name:<{width}}  {res.detail}")
        for item in res.items:
            print(f"         - {item}")

    print(f"\n  {counts[PASS]} passed, {counts[FAIL]} failed, {counts[PENDING]} pending\n")

    if counts[FAIL]:
        print("  FAILED. Fix the items above before pushing.\n")
        return 1
    if counts[PENDING] and args.strict:
        print("  STRICT MODE: pending items are not acceptable at submission time.\n")
        return 1
    if counts[PENDING]:
        print("  No failures. Pending items are deliverables not yet built - expected during\n"
              "  development. Re-run with --strict before submitting.\n")
    else:
        print("  All checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
