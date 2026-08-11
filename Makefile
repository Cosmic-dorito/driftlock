# DriftLock task runner (POSIX shells: Linux, macOS, Git Bash on Windows).
# Windows PowerShell users: .\make.ps1 <target> — same target names, same behaviour.

PY      := python
VENV    := .venv
VPY     := $(VENV)/bin/python
ifeq ($(OS),Windows_NT)
VPY     := $(VENV)/Scripts/python.exe
endif

SEED    ?= 1234
N       ?= 30
SPLIT   ?= bench

.DEFAULT_GOAL := help
.PHONY: help setup data bench test verify package lint fmt clean sponsor

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## Create .venv and install pinned dependencies
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPY) -m pip install -r requirements.txt
	@echo "Environment ready. Activate with: source $(VENV)/Scripts/activate (Windows) or source $(VENV)/bin/activate"

data:  ## Regenerate datasets from recorded seeds
	$(VPY) generate_dataset.py --num-samples $(N) --split $(SPLIT) --seed $(SEED) --output-dir data

bench:  ## Run localization over the bench manifest and score it
	$(VPY) localize.py --manifest data/$(SPLIT)/manifest.csv --out results/predictions.csv
	$(VPY) evaluate.py --manifest data/$(SPLIT)/manifest.csv --predictions results/predictions.csv --out results/

test:  ## Run the unit tests
	$(VPY) -m pytest

verify:  ## Spec checklist, no-absolute-paths scan, determinism check
	$(VPY) scripts/verify_submission.py

lint:  ## Ruff check
	$(VPY) -m ruff check .

fmt:  ## Ruff format
	$(VPY) -m ruff format .

sponsor:  ## Fetch the sponsor's reference generator into gitignored third_party/
	bash scripts/fetch_reference_generator.sh

package:  ## Build dist/drift-lock-submission.zip in the sponsor's required layout
	$(VPY) scripts/package_submission.py

clean:  ## Remove caches and packaging output
	rm -rf .pytest_cache .ruff_cache dist
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
