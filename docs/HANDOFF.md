# HANDOFF — cold start on a new machine

Goal: someone who has never seen this project (or you, on a different laptop, at 2 a.m.) gets from
zero to a working environment and correct output in **under ten minutes**.

---

## 1. Get the code and environment

```bash
git clone <repo-url> semicon
cd semicon
make setup                 # Windows PowerShell: .\make.ps1 setup
```

`make setup` creates `.venv` at the repo root and installs the pinned dependencies from
`requirements.txt`. Python **3.14** is what the team targets (ADR-0002); the code declares
`requires-python = ">=3.11"` so an older interpreter also works.

Activate it:

```bash
source .venv/Scripts/activate     # Git Bash on Windows
source .venv/bin/activate         # Linux / macOS
.\.venv\Scripts\Activate.ps1      # PowerShell
```

## 2. Prove it works

```bash
make test        # unit tests, including the asymmetric geometry test
make verify      # spec checklist, no-absolute-paths scan, determinism check
```

Both green means the environment is sound. If `make verify` complains about absolute paths, someone
hard-coded a `C:\` or `/home/` path — that is a literal item on the sponsor's grading checklist, so
fix it rather than skipping the check.

## 3. Read yourself in — in this order

| Read | For |
|---|---|
| `CLAUDE.md` | The thesis, the frozen contracts, the correctness rules. **Start here.** |
| `docs/PROGRESS.md` | What is done, what is next, who owns it, what is blocked |
| `docs/DECISIONS.md` | Why things are the way they are, and the H1–H9 verification log |
| `docs/SPEC.md` | What the sponsor actually requires (extraction from the PDF) |
| `docs/PLAN.md` | The full approved plan, including the day-by-day schedule |
| `docs/METHOD.md` | The technical writeup the deck is generated from |

If you are a Claude Code instance: `CLAUDE.md` loads automatically. Read `docs/PROGRESS.md` next to
find the current gate before doing anything.

## 4. Get data

The committed `data/bench/` set (the ≥30 pairs the spec requires) ships with the repo. Everything
larger is regenerated from recorded seeds — the generator is deterministic, so this reproduces the
exact same images:

```bash
make data
```

To also pull the sponsor's published generator for cross-generator validation (fetched into
gitignored `third_party/`, never vendored):

```bash
bash scripts/fetch_reference_generator.sh
```

## 5. Run something end to end

```bash
# Single pair — prints exactly one line: "312.42,489.07"
python localize.py --reference data/bench/reference/00000.png --search data/bench/search/00000.png

# Batch over a manifest, then score it
python localize.py --manifest data/bench/manifest.csv --out results/predictions.csv
python evaluate.py --manifest data/bench/manifest.csv --predictions results/predictions.csv --out results/
```

## 6. Before you push

- `make test` and `make verify` are green.
- New non-obvious choice? Add an ADR to `docs/DECISIONS.md`.
- Cleared a gate? Tick it in `docs/PROGRESS.md` with your initials and the date.
- Changed results? Regenerate `results/` in the same commit. **Never a claim in the deck without a
  commit behind it** (R2).
- Stay inside your directory (`CLAUDE.md` → ownership table). If you must touch someone else's,
  tell them first — that separation is what keeps three people from colliding.

## 7. Package the submission

```bash
make package     # -> dist/drift-lock-submission.zip, in the sponsor's recommended layout
```

Then the real test: unzip it into an empty directory **on a machine that has never seen this
project**, and run the commands in section 5. Identical numbers, or it is not done.

---

## Gotchas that have already bitten us

- **`opencv-python-headless`, never `opencv-python`.** The evaluator's box may have no display libraries.
- **`torch` is optional and lazily imported.** `pip uninstall torch` must leave everything working.
  Never import it at module top level.
- **`.gitattributes` matters.** It marks `*.png binary`; without it Windows CRLF conversion silently
  corrupts committed PNGs and quietly breaks the byte-identical reproducibility claim.
- **stdout is sacred** in single-pair mode: the coordinate and nothing else. All logs to stderr.
- **The x/y swap.** `cv2` indexes `[y, x]`; the spec wants `(x, y)`. Conversion happens only in
  `src/driftlock/io.py` (ADR-0007), and the geometry test is asymmetric on purpose — a symmetric test
  cannot catch a swap.
