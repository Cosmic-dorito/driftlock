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

To produce a cross-validation split from it (run from inside that directory, with our venv
active - it depends on numpy and opencv, which we already pin):

    cd third_party/drift-sense-reference
    python generate_dataset.py --num-samples 100 --split sponsor \
        --architectures dram_1x dram_dense --output-dir ../../data/_sponsor --seed 20260811

Its manifest.csv is a subset of our schema, so our loader reads it unchanged
(see the manifest contract in CLAUDE.md).

Reminder: this is third-party code used for validation and attribution only. Do not copy it
into src/. See ADR-0004.
NOTE
