<#
.SYNOPSIS
    DriftLock task runner for Windows PowerShell. Mirrors the Makefile target-for-target.

.EXAMPLE
    .\make.ps1 setup
    .\make.ps1 data -N 200 -Split train -Seed 7
    .\make.ps1 verify
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'data', 'bench', 'test', 'verify', 'lint', 'fmt', 'sponsor', 'package', 'clean')]
    [string]$Target = 'help',

    [int]$N = 30,
    [int]$Seed = 1234,
    [string]$Split = 'bench'
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VPy = Join-Path $Venv 'Scripts\python.exe'

function Assert-Venv {
    if (-not (Test-Path $VPy)) {
        throw "No virtualenv found at $Venv. Run: .\make.ps1 setup"
    }
}

switch ($Target) {
    'help' {
        Write-Host ''
        Write-Host '  DriftLock tasks' -ForegroundColor Cyan
        Write-Host ''
        Write-Host '    setup     Create .venv and install pinned dependencies'
        Write-Host '    data      Regenerate datasets from recorded seeds'
        Write-Host '    bench     Run localization over the bench manifest and score it'
        Write-Host '    test      Run the unit tests'
        Write-Host '    verify    Spec checklist, no-absolute-paths scan, determinism check'
        Write-Host '    lint      Ruff check'
        Write-Host '    fmt       Ruff format'
        Write-Host '    sponsor   Fetch the sponsor reference generator into third_party/'
        Write-Host '    package   Build dist/drift-lock-submission.zip'
        Write-Host '    clean     Remove caches and packaging output'
        Write-Host ''
    }

    'setup' {
        python -m venv $Venv
        & $VPy -m pip install --upgrade pip
        & $VPy -m pip install -r (Join-Path $Root 'requirements-dev.txt')
        Write-Host "Environment ready. Activate with: .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
    }

    'data' {
        Assert-Venv
        & $VPy (Join-Path $Root 'generate_dataset.py') --num-samples $N --split $Split --seed $Seed --output-dir (Join-Path $Root 'data')
    }

    'bench' {
        Assert-Venv
        $manifest = Join-Path $Root "data\$Split\manifest.csv"
        $preds = Join-Path $Root 'results\predictions.csv'
        & $VPy (Join-Path $Root 'localize.py') --manifest $manifest --out $preds
        & $VPy (Join-Path $Root 'evaluate.py') --manifest $manifest --predictions $preds --out (Join-Path $Root 'results')
    }

    'test' { Assert-Venv; & $VPy -m pytest }

    'verify' { Assert-Venv; & $VPy (Join-Path $Root 'scripts\verify_submission.py') }

    'lint' { Assert-Venv; & $VPy -m ruff check $Root }

    'fmt' { Assert-Venv; & $VPy -m ruff format $Root }

    'sponsor' { bash (Join-Path $Root 'scripts/fetch_reference_generator.sh') }

    'package' { Assert-Venv; & $VPy (Join-Path $Root 'scripts\package_submission.py') }

    'clean' {
        foreach ($d in @('.pytest_cache', '.ruff_cache', 'dist')) {
            $p = Join-Path $Root $d
            if (Test-Path $p) { Remove-Item -Recurse -Force $p }
        }
        Get-ChildItem -Path $Root -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notlike "*\.venv\*" } |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Write-Host 'Cleaned.' -ForegroundColor Green
    }
}
