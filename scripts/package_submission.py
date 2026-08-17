#!/usr/bin/env python3
"""Build the graded submission archive in the sponsor's recommended layout.

The working repository keeps docs/, tests/ and tooling at the root, which is right for a project
but is not the tree the problem statement recommends. This script emits exactly that tree:

    submission/
      solution_presentation.pptx
      README.md
      requirements.txt
      generate_dataset.py
      localize.py
      configs/  src/  model/  results/  references/

See ADR-0001. Output: dist/drift-lock-submission.zip

    python scripts/package_submission.py
    python scripts/package_submission.py --no-data     # omit data/ to shrink the archive

The archive is verified after writing: it must contain every mandatory deliverable, and it must not
contain caches, virtualenvs or vendored third-party code.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST = REPO_ROOT / "dist"
STAGE = DIST / "submission"

# Files copied to the root of submission/. (source relative to repo, destination name)
ROOT_FILES = [
    ("README.md", "README.md"),
    ("requirements.txt", "requirements.txt"),
    ("requirements-optional.txt", "requirements-optional.txt"),
    ("LICENSE", "LICENSE"),
    ("generate_dataset.py", "generate_dataset.py"),
    ("localize.py", "localize.py"),
    ("evaluate.py", "evaluate.py"),
]

DIRECTORIES = ["configs", "src", "model", "results", "scripts", "tests"]

# docs/ maps onto the recommended references/ folder: the sponsor asks for a references
# directory, and our supporting documentation is what belongs there.
DOCS_TO_REFERENCES = "references"

EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
                "third_party", "dist", "node_modules", "_scratch", "_smoke", "_sponsor"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

MANDATORY = ["README.md", "requirements.txt", "generate_dataset.py", "localize.py"]


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in EXCLUDE_DIRS or Path(n).suffix in EXCLUDE_SUFFIXES}


def stage(include_data: bool) -> list[str]:
    """Assemble dist/submission/ and return a list of warnings about missing deliverables."""
    warnings: list[str] = []

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    for src_name, dst_name in ROOT_FILES:
        src = REPO_ROOT / src_name
        if src.exists():
            shutil.copy2(src, STAGE / dst_name)
        elif src_name in MANDATORY:
            warnings.append(f"MISSING mandatory file: {src_name}")

    for dir_name in DIRECTORIES:
        src = REPO_ROOT / dir_name
        if src.is_dir():
            shutil.copytree(src, STAGE / dir_name, ignore=_ignore, dirs_exist_ok=True)

    docs = REPO_ROOT / "docs"
    if docs.is_dir():
        shutil.copytree(docs, STAGE / DOCS_TO_REFERENCES, ignore=_ignore, dirs_exist_ok=True)

    # The original problem statement travels with the submission for context.
    ref_pdf = next((REPO_ROOT / "reference").glob("*.pdf"), None) if (REPO_ROOT / "reference").is_dir() else None
    if ref_pdf:
        shutil.copy2(ref_pdf, STAGE / DOCS_TO_REFERENCES / ref_pdf.name)

    if include_data:
        bench = REPO_ROOT / "data" / "bench"
        if bench.is_dir():
            shutil.copytree(bench, STAGE / "data" / "bench", ignore=_ignore, dirs_exist_ok=True)
        else:
            warnings.append("MISSING data/bench/ - the >=30-pair validation evidence the spec requires")

    # By exact name, not by glob. `next(glob("*.pptx"))` returns whatever the filesystem lists
    # first, so a second deck in the tree could be shipped instead - silently, since both files
    # would be named plausibly and the zip would look complete. That was a live risk until the
    # superseded 12-slide deck was deleted on 18 Aug; naming it explicitly keeps it a non-risk.
    # The PDF ships too: the portal asks for it alongside the GitHub link.
    for name in ("Silli-Con Artists_PS02.pptx", "Silli-Con Artists_PS02.pdf"):
        deck = REPO_ROOT / name
        if deck.is_file():
            shutil.copy2(deck, STAGE / name)
        else:
            warnings.append(f"MISSING {name} - deliverable 1 is MANDATORY")

    return warnings


def write_zip() -> Path:
    archive = DIST / "drift-lock-submission.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(DIST).as_posix())
    return archive


def verify_zip(archive: Path) -> list[str]:
    """Re-open the archive and confirm what actually landed in it."""
    problems = []
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()

    for required in MANDATORY:
        if f"submission/{required}" not in names:
            problems.append(f"archive is missing submission/{required}")

    for name in names:
        parts = Path(name).parts
        if any(p in EXCLUDE_DIRS for p in parts):
            problems.append(f"archive contains excluded content: {name}")
        if Path(name).suffix in EXCLUDE_SUFFIXES:
            problems.append(f"archive contains compiled artefact: {name}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-data", action="store_true", help="omit data/bench from the archive")
    args = parser.parse_args()

    DIST.mkdir(exist_ok=True)
    warnings = stage(include_data=not args.no_data)
    archive = write_zip()
    problems = verify_zip(archive)

    file_count = sum(1 for p in STAGE.rglob("*") if p.is_file())
    size_mb = archive.stat().st_size / 1_048_576

    print(f"\n  Wrote {archive.relative_to(REPO_ROOT).as_posix()}")
    print(f"  {file_count} files, {size_mb:.1f} MB\n")

    for w in warnings:
        print(f"  WARNING  {w}")
    for p in problems:
        print(f"  ERROR    {p}")

    if problems:
        print("\n  Archive is not valid. Fix the errors above.\n")
        return 1

    if warnings:
        print("\n  Archive written, but deliverables are missing. Not submittable yet.\n")
    else:
        print("  All mandatory deliverables present.\n")

    print("  Final check before submitting: unzip this into an EMPTY directory on a machine that\n"
          "  has never seen this project, then run the commands in README.md. Identical numbers,\n"
          "  or it is not done.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
