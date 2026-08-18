#!/usr/bin/env bash
# Fetch the sponsor's published starter generator for CROSS-GENERATOR VALIDATION.
#
# Why: evaluating our matcher only on our own generator proves nothing about generalization.
# Running it against an independently written generator - the one Applied Materials themselves
# published - is the honest evidence that we have not overfit to our own data distribution.
# It is also the source of the baseline we measure against.
#
# This code is NOT vendored into the repository. It is cloned into third_party/, which is
# gitignored, and attributed in README.md and docs/REFERENCES.md. All generator code in
# src/synth/ is our own (see ADR-0004).
#
# Usage:  bash scripts/fetch_reference_generator.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/third_party/drift-sense-reference"
SPACE_URL="https://huggingface.co/spaces/aayushraina21/drift-sense-synthetic-data"

if ! command -v git >/dev/null 2>&1; then
    echo "error: git is required but not found on PATH" >&2
    exit 1
fi

mkdir -p "${REPO_ROOT}/third_party"

if [ -d "${DEST}/.git" ]; then
    echo "Reference generator already present at third_party/drift-sense-reference - updating."
    git -C "${DEST}" pull --ff-only
else
    echo "Cloning the sponsor's starter generator into third_party/ (not vendored, gitignored)..."
    git clone --depth 1 "${SPACE_URL}" "${DEST}"
fi

cat <<'NOTE'

Done. The reference generator is in third_party/drift-sense-reference/.

YOU PROBABLY DO NOT NEED TO RUN THIS. The sponsor split we report on is COMMITTED at
data/_sponsor/verify/ - 40 pairs with ground truth - so every reported figure can be
recomputed with `python scripts/audit_results.py` and no fetch at all. This script is here
for attribution, and for anyone who wants fresh sponsor-style data.

To reproduce the EXACT split behind the reported sponsor figures (run from inside that
directory, with our venv active - it depends on numpy and opencv, which we already pin):

    cd third_party/drift-sense-reference
    python generate_dataset.py --num-samples 40 --split verify \
        --architectures dram_1x --output-dir ../../data/_sponsor --seed 20260811

Those arguments are read off the committed manifest, not remembered: 40 rows, every row
seed 20260811 and architecture dram_1x, under the split name `verify`. An earlier version of
this note said `--num-samples 100 --split sponsor --architectures dram_1x dram_dense`, which
produces a differently named and differently sized dataset from the one the reported 0.0%
mis-lock was measured on.

Its manifest.csv is a subset of our schema, so our loader reads it unchanged; the manifest
contract is documented in docs/SPEC.md and enforced by scripts/verify_submission.py.

Reminder: this is third-party code used for validation and attribution only. Do not copy it
into src/. See ADR-0004.
NOTE
