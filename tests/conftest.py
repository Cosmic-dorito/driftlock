"""Make the repo root importable so `import src.driftlock` works without installing the package.

Uses pathlib and a path derived from this file's location — never an absolute path (see CLAUDE.md
portability rules; `scripts/verify_submission.py` fails the build on hard-coded paths).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
