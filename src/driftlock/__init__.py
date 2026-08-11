"""DriftLock localization pipeline.

Importing this package must NOT pull in torch. The deterministic path — which produces the
submitted coordinates — depends only on numpy / opencv / scipy / scikit-image. torch is imported
lazily inside `rerank.py`, guarded by try/except, and only when the flag-gated re-ranker runs.
See ADR-0006 and tests/test_deps_api.py::test_torch_is_not_required.
"""

__all__ = []
