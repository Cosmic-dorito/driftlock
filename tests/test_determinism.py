"""Same seed in, byte-identical data out; same images in, identical coordinates out.

PROGRESS 3.8, and a literal item on the sponsor's checklist. Reproducibility is the whole
justification for shipping the large splits as seeds rather than as blobs (README): if the seed
does not reproduce the bytes, the dataset is not reproducible and that claim has to be withdrawn.

Two independent properties, tested separately because they fail for different reasons:

* **the generator** must be a pure function of its seed. The usual break is a global
  ``np.random`` call somewhere in the chain, which makes output depend on how many draws happened
  earlier - so the FIRST pair reproduces and a later one does not. Both pairs are compared here
  for that reason.
* **the localizer** must be a pure function of its two images. The usual break is thread
  scheduling in a parallel reduction changing a floating-point summation order.

Deliberately compared as BYTES, not as "close enough". A tolerance here would pass a pipeline that
is merely stable, which is a weaker claim than the README makes.

⚠️ **SCOPE: this asserts SAME-PLATFORM determinism only.** Both runs happen on one machine with one
set of library versions, so that is the whole of what it can establish. It is NOT a cross-platform
guarantee, and measurement says the stronger claim is false: regenerating `bench` with seed 1234 on
macOS/arm64 against images generated on Windows/x86-64 reproduces the ground-truth coordinates
exactly while leaving 93-98% of PIXELS differing. OpenCV's filtering differs slightly between SIMD
back-ends, which perturbs the input to `rng.poisson`, whose rejection sampler then consumes a
different number of variates and desynchronises the stream for everything after it.

The task is identical across platforms - same layout, same ground truth, same difficulty - but the
pixels are not. Anyone checking our reported numbers against our exact images should use the
committed `data/bench`. See README, "Regenerating every reported split".
"""

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from src.driftlock.io import resolve_manifest_path

REPO_ROOT = Path(__file__).resolve().parents[1]

SEED = 20260816
PAIRS = 2


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate(out_dir: Path, split: str) -> Path:
    """One generator run. Returns the split directory."""
    cmd = [sys.executable, str(REPO_ROOT / "generate_dataset.py"),
           "--num-samples", str(PAIRS), "--split", split, "--seed", str(SEED),
           "--output-dir", str(out_dir), "--architectures", "dram"]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    # Never put a colon immediately before a backslash escape in a string here. That byte sequence
    # matches the Windows drive-letter pattern and fails the no-hard-coded-paths check in
    # scripts/verify_submission.py, which is why this message does not read "generator failed".
    assert proc.returncode == 0, f"generator exited {proc.returncode}\n{proc.stderr[-2000:]}"
    return out_dir / split


@pytest.mark.slow
def test_same_seed_gives_byte_identical_images(tmp_path):
    """The generator is a pure function of its seed."""
    first = _generate(tmp_path / "a", "det")
    second = _generate(tmp_path / "b", "det")

    images_a = sorted((first / "reference").glob("*.png")) + \
        sorted((first / "search").glob("*.png"))
    images_b = sorted((second / "reference").glob("*.png")) + \
        sorted((second / "search").glob("*.png"))

    assert len(images_a) == 2 * PAIRS, f"expected {2 * PAIRS} images, got {len(images_a)}"
    assert [p.name for p in images_a] == [p.name for p in images_b]

    mismatched = [a.name for a, b in zip(images_a, images_b) if _digest(a) != _digest(b)]
    assert not mismatched, (
        f"{len(mismatched)} image(s) differ across two runs of the same seed: {mismatched}. "
        "A later pair differing while the first matches points at a global np.random draw "
        "rather than the threaded Generator."
    )


@pytest.mark.slow
def test_same_seed_gives_identical_ground_truth(tmp_path):
    """The manifest must reproduce too - the label is as much of the dataset as the pixels are.

    Kept separate from the image check because ADR-0028 is exactly this failure: the coordinate was
    frozen before a geometric stage ran, so the label described a different image than the one
    saved. Identical pixels with drifting labels is a real and silent failure mode.

    The two runs write to different directories, so the recorded paths legitimately differ; only
    the LABEL columns are compared. The paths get their own assertion below, because what the
    first version of this test actually caught was the generator emitting absolute ones.
    """
    first = _generate(tmp_path / "a", "det")
    second = _generate(tmp_path / "b", "det")

    def labels(split_dir):
        with (split_dir / "manifest.csv").open(newline="", encoding="utf-8") as fh:
            return [{k: v for k, v in row.items()
                     if k not in {"reference_path", "search_path"}}
                    for row in csv.DictReader(fh)]

    assert labels(first) == labels(second)


@pytest.mark.slow
def test_manifest_paths_are_never_absolute(tmp_path):
    """A literal item on the sponsor's checklist: no hard-coded local paths.

    Generating into a temp directory is the case that breaks it - inside the repo the recorded
    path is relative whatever the writer does. `scripts/verify_submission.py` cannot catch this
    either, since it only scans files that are in the tree.
    """
    split = _generate(tmp_path / "a", "det")
    with (split / "manifest.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert rows, "generator produced no rows"
    for row in rows:
        for column in ("reference_path", "search_path"):
            recorded = row[column]
            assert not Path(recorded).is_absolute(), f"{column} is absolute: {recorded}"
            assert "\\" not in recorded, f"{column} is not forward-slashed: {recorded}"
            # And it must still resolve, or portability was bought by breaking the reader.
            assert resolve_manifest_path(split / "manifest.csv", recorded).exists()


@pytest.mark.slow
def test_localizer_is_deterministic(tmp_path):
    """Same images, same config, identical coordinates - bit for bit, not merely close."""
    import localize as L
    from src.driftlock.io import load_grayscale, read_manifest, resolve_manifest_path
    from src.driftlock.match import localize as run

    split = _generate(tmp_path / "a", "det")
    manifest = split / "manifest.csv"

    import argparse
    cfg = L.build_config(argparse.Namespace(config="driftlock"))

    for row in read_manifest(manifest):
        reference = load_grayscale(resolve_manifest_path(manifest, row["reference_path"]))
        search = load_grayscale(resolve_manifest_path(manifest, row["search_path"]))
        first = run(reference, search, cfg)
        second = run(reference, search, cfg)
        # repr, not approx: a tolerance would pass a pipeline that is stable but not deterministic.
        assert (repr(first.x), repr(first.y)) == (repr(second.x), repr(second.y)), (
            f"pair {row['id']}: {first.x},{first.y} then {second.x},{second.y}"
        )
        assert repr(first.score) == repr(second.score)
