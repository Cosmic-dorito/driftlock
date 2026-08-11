<#
.SYNOPSIS
    End-to-end smoke test for Windows PowerShell. Mirrors scripts/smoke_test.sh.

.DESCRIPTION
    Runs exactly the commands the README tells an evaluator to run. A script that fails on the
    evaluator's machine scores zero no matter how good the method is, and environment failure is
    what eliminates teams. Run this on a CLEAN machine before submitting - not just on the laptop
    where everything was written.

.EXAMPLE
    .\scripts\smoke_test.ps1
#>

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) {
    $Py = 'python'
    Write-Host 'note: no .venv found, using system python' -ForegroundColor Yellow
}

function Pass($m) { Write-Host "  [PASS] $m" -ForegroundColor Green }
function Skip($m) { Write-Host "  [SKIP] $m" -ForegroundColor DarkGray }
function Fail($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

Write-Host ''
Write-Host 'DriftLock smoke test'
Write-Host "  python: $(& $Py --version)"
Write-Host ''

# 1 -------------------------------------------------------------- imports
Write-Host '1. Dependencies import'
& $Py -c "import numpy, scipy, cv2, skimage, pandas, yaml, PIL"
if ($LASTEXITCODE -ne 0) { Fail 'dependency import failed' }
Pass 'numpy, scipy, cv2, skimage, pandas, yaml, PIL'

# 2 -------------------------------------------------------------- tests
Write-Host ''
Write-Host '2. Unit tests'
& $Py -m pytest -q | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "pytest - run '$Py -m pytest' to see why" }
Pass 'pytest'

# 3 -------------------------------------------------------------- generator
Write-Host ''
Write-Host '3. Dataset generation'
if (Test-Path 'generate_dataset.py') {
    & $Py generate_dataset.py --num-samples 2 --split _smoke --seed 4242 --output-dir data | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail 'generate_dataset.py returned non-zero' }
    if (-not (Test-Path 'data\_smoke\manifest.csv')) { Fail 'generator did not write the manifest' }
    Pass 'generated 2 pairs + manifest'
} else {
    Skip 'generate_dataset.py not written yet'
}

# 4 -------------------------------------------------------------- localizer
Write-Host ''
Write-Host '4. Localization'
if (Test-Path 'localize.py') {
    $ref = Get-ChildItem -Path 'data' -Recurse -Filter '*.png' -ErrorAction SilentlyContinue |
           Where-Object { $_.FullName -like '*reference*' } | Select-Object -First 1
    $search = Get-ChildItem -Path 'data' -Recurse -Filter '*.png' -ErrorAction SilentlyContinue |
              Where-Object { $_.FullName -like '*search*' } | Select-Object -First 1
    if ($ref -and $search) {
        $out = & $Py localize.py --reference $ref.FullName --search $search.FullName
        if ($LASTEXITCODE -ne 0) { Fail 'localize.py returned non-zero' }
        # stdout discipline: EXACTLY one line, "x,y", nothing else.
        $lines = @($out | Where-Object { $_ -ne '' })
        if ($lines.Count -ne 1) { Fail "localize.py printed $($lines.Count) stdout lines; logs belong on stderr" }
        if ($lines[0] -notmatch '^-?\d+(\.\d+)?,-?\d+(\.\d+)?$') { Fail "stdout was '$($lines[0])', expected 'x,y'" }
        Pass "single-pair mode printed exactly one coordinate line: $($lines[0])"
    } else {
        Skip 'no images available to localize'
    }
} else {
    Skip 'localize.py not written yet'
}

# 5 -------------------------------------------------------------- torch optional
Write-Host ''
Write-Host '5. torch is genuinely optional'
& $Py -c "import sys; sys.modules['torch']=None; import importlib; importlib.import_module('src.driftlock')"
if ($LASTEXITCODE -ne 0) { Fail 'src.driftlock failed to import without torch' }
Pass 'src.driftlock imports with torch unavailable'

# 6 -------------------------------------------------------------- checklist
Write-Host ''
Write-Host '6. Submission checklist'
& $Py scripts\verify_submission.py | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'verify_submission.py reported failures' }
Pass 'no failures (run scripts\verify_submission.py for the full report)'

if (Test-Path 'data\_smoke') { Remove-Item -Recurse -Force 'data\_smoke' }

Write-Host ''
Write-Host 'Smoke test passed.' -ForegroundColor Green
Write-Host ''
