<#
.SYNOPSIS
    Launch the NETRA v0.2 baseline as a detached, resumable background process.

.DESCRIPTION
    Phase 27. Starts ONE baseline training run that survives the terminal closing.
    The run checkpoints every epoch (best + last), writes a JSONL epoch log, and
    can be resumed from its own last checkpoint.

    This script deliberately does NOT launch a sweep and does NOT launch more than
    one experiment. Long training is gated on the real smoke test:
        scripts/netra_v02/06_real_smoke_test.py
    which must print LONG_TRAINING_AUTHORIZED = TRUE first.

.PARAMETER Epochs
    Training epochs. Default 50.

.PARAMETER Resume
    Resume from <experiment_id>_last.pt if it exists.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\netra_v02\launch_baseline.ps1
    powershell -ExecutionPolicy Bypass -File scripts\netra_v02\launch_baseline.ps1 -Resume
#>
param(
    [int]$Epochs = 50,
    [string]$Config = "configs/lab/netra.yaml",
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Repo

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Project interpreter not found at $Python. The system 'python' carries a CPU-only torch build and must not be used."
    exit 1
}

# --- caches off the full C: drive -------------------------------------------
$CacheRoot = "D:\varuna_cache"
foreach ($d in @("$CacheRoot\hf", "$CacheRoot\torch", "$CacheRoot\tmp")) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}
$env:HF_HOME   = "$CacheRoot\hf"
$env:TORCH_HOME= "$CacheRoot\torch"
$env:TMP       = "$CacheRoot\tmp"
$env:TEMP      = "$CacheRoot\tmp"
$env:PYTHONUNBUFFERED = "1"

# --- hard gate: the real smoke test must have authorised this ---------------
$SmokeReport = Join-Path $Repo "reports\netra_v02\06_smoke_test.json"
if (-not (Test-Path $SmokeReport)) {
    Write-Error "No smoke-test report at $SmokeReport. Run scripts/netra_v02/06_real_smoke_test.py first; long training is not authorised."
    exit 2
}
$Smoke = Get-Content $SmokeReport -Raw | ConvertFrom-Json
if (-not $Smoke.long_training_authorized) {
    Write-Host "REAL_SMOKE_TEST results:" -ForegroundColor Yellow
    $Smoke.results.PSObject.Properties | ForEach-Object { Write-Host ("  {0,-18} = {1}" -f $_.Name, $_.Value) }
    Write-Error "LONG_TRAINING_AUTHORIZED = FALSE. Refusing to start the baseline."
    exit 3
}
Write-Host "LONG_TRAINING_AUTHORIZED = TRUE (from $SmokeReport)" -ForegroundColor Green

# --- launch -----------------------------------------------------------------
$Stamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$LogDir  = Join-Path $Repo "artifacts\experiments"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$StdOut  = Join-Path $LogDir "baseline_$Stamp.out.log"
$StdErr  = Join-Path $LogDir "baseline_$Stamp.err.log"

$ArgList = @("-u", "train_netra.py", "--config", $Config, "--epochs", "$Epochs")
if ($Resume) { $ArgList += @("--resume", "auto") }

Write-Host "Repo        : $Repo"
Write-Host "Interpreter : $Python"
Write-Host "Command     : python $($ArgList -join ' ')"
Write-Host "stdout      : $StdOut"
Write-Host "stderr      : $StdErr"

$proc = Start-Process -FilePath $Python `
                      -ArgumentList $ArgList `
                      -WorkingDirectory $Repo `
                      -RedirectStandardOutput $StdOut `
                      -RedirectStandardError $StdErr `
                      -WindowStyle Hidden `
                      -PassThru

$Meta = @{
    pid          = $proc.Id
    started_at   = (Get-Date).ToUniversalTime().ToString("o")
    epochs       = $Epochs
    config       = $Config
    resume       = [bool]$Resume
    stdout       = $StdOut
    stderr       = $StdErr
    interpreter  = $Python
} | ConvertTo-Json
$MetaPath = Join-Path $LogDir "baseline_$Stamp.launch.json"
$Meta | Set-Content -Path $MetaPath -Encoding utf8

Write-Host ""
Write-Host "BASELINE STARTED" -ForegroundColor Green
Write-Host "  PID          : $($proc.Id)"
Write-Host "  launch record: $MetaPath"
Write-Host ""
Write-Host "The process is detached and survives this terminal closing."
Write-Host "Follow progress :  Get-Content -Wait -Tail 40 `"$StdOut`""
Write-Host "Stop            :  Stop-Process -Id $($proc.Id)"
Write-Host "Resume later    :  powershell -File scripts\netra_v02\launch_baseline.ps1 -Resume"
