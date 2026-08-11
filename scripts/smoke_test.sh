#!/usr/bin/env bash
# End-to-end smoke test: exactly the commands the README tells an evaluator to run.
#
# This is the cheapest insurance available. A script that fails on the evaluator's machine scores
# zero no matter how good the method is, and environment failure is what eliminates teams.
# Run this on a CLEAN machine (or a fresh container) before submitting - not just on the laptop
# where everything was written.
#
# Usage:  bash scripts/smoke_test.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"          # Windows
elif [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"                  # Linux / macOS
else
    PY="python"
    echo "note: no .venv found, using system python"
fi

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1" >&2; exit 1; }
skip() { echo "  [SKIP] $1"; }

echo
echo "DriftLock smoke test"
echo "  python: $(${PY} --version 2>&1)"
echo

# ---------------------------------------------------------------- imports
echo "1. Dependencies import"
${PY} - <<'EOF' || exit 1
import numpy, scipy, cv2, skimage, pandas, yaml, PIL  # noqa: F401
EOF
pass "numpy, scipy, cv2, skimage, pandas, yaml, PIL"

# ---------------------------------------------------------------- tests
echo
echo "2. Unit tests"
if ${PY} -m pytest -q >/dev/null 2>&1; then
    pass "pytest"
else
    fail "pytest - run '${PY} -m pytest' to see why"
fi

# ---------------------------------------------------------------- generator
echo
echo "3. Dataset generation"
if [ -f generate_dataset.py ]; then
    TMP_SPLIT="_smoke"
    ${PY} generate_dataset.py --num-samples 2 --split "${TMP_SPLIT}" --seed 4242 --output-dir data \
        >/dev/null || fail "generate_dataset.py returned non-zero"
    MANIFEST="data/${TMP_SPLIT}/manifest.csv"
    [ -f "${MANIFEST}" ] || fail "generator did not write ${MANIFEST}"
    pass "generated 2 pairs + manifest"
else
    skip "generate_dataset.py not written yet"
fi

# ---------------------------------------------------------------- localizer
echo
echo "4. Localization"
if [ -f localize.py ]; then
    REF=$(ls data/*/reference/*.png 2>/dev/null | head -1 || true)
    SEARCH=$(ls data/*/search/*.png 2>/dev/null | head -1 || true)
    if [ -n "${REF}" ] && [ -n "${SEARCH}" ]; then
        OUT=$(${PY} localize.py --reference "${REF}" --search "${SEARCH}" 2>/dev/null) \
            || fail "localize.py returned non-zero"

        # stdout discipline: EXACTLY one line, "x,y", and nothing else.
        LINES=$(printf '%s' "${OUT}" | wc -l | tr -d ' ')
        [ "${LINES}" -le 1 ] || fail "localize.py printed ${LINES} extra lines to stdout; logs belong on stderr"
        echo "${OUT}" | grep -Eq '^-?[0-9]+(\.[0-9]+)?,-?[0-9]+(\.[0-9]+)?$' \
            || fail "stdout was '${OUT}', expected exactly 'x,y'"
        pass "single-pair mode printed exactly one coordinate line: ${OUT}"
    else
        skip "no images available to localize"
    fi
else
    skip "localize.py not written yet"
fi

# ---------------------------------------------------------------- torch optional
echo
echo "5. torch is genuinely optional"
${PY} - <<'EOF' || exit 1
import sys
sys.modules["torch"] = None          # simulate torch being absent
import importlib
try:
    importlib.import_module("src.driftlock")
except Exception as exc:
    raise SystemExit(f"src.driftlock failed to import without torch: {exc}")
EOF
pass "src.driftlock imports with torch unavailable"

# ---------------------------------------------------------------- submission checklist
echo
echo "6. Submission checklist"
${PY} scripts/verify_submission.py >/dev/null || fail "verify_submission.py reported failures"
pass "no failures (run scripts/verify_submission.py for the full report)"

# ---------------------------------------------------------------- cleanup
rm -rf "data/_smoke" 2>/dev/null || true

echo
echo "Smoke test passed."
echo
