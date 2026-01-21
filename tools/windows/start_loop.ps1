#Requires -Version 5.1
<#
.SYNOPSIS
    Start AI Trader loop for morning trading session.

.DESCRIPTION
    Starts the trading loop at 9:00 AM ET with hourly ticks.

    The loop runs continuously and:
    - Fetches current snapshot from selector
    - Analyzes candidates and generates orders
    - Submits orders via RiskManager (respects pause_trading.flag)
    - Logs all activity
    - Sleeps for specified interval (default: 1 hour)

    Safety features:
    - Defaults to paper mode
    - Respects pause_trading.flag (can run in DryRun mode when paused)
    - Logs all operations
    - Can optionally create pause_trading.flag at startup for safety

.PARAMETER Mode
    Trading mode: shadow or paper (default: paper)

.PARAMETER DryRun
    Run in dry-run mode (no actual orders placed)

.PARAMETER SleepSeconds
    Sleep interval between loop iterations in seconds (default: 3600 = 1 hour)

.PARAMETER CreatePauseFlag
    Create pause_trading.flag at startup for safe warm start

.PARAMETER LogToFile
    Log output to logs/loop/loop_YYYYMMDD.log

.EXAMPLE
    .\start_loop.ps1
    Start loop in paper mode with hourly ticks

.EXAMPLE
    .\start_loop.ps1 -DryRun
    Start loop in dry-run mode (no orders placed)

.EXAMPLE
    .\start_loop.ps1 -CreatePauseFlag
    Start loop with pause_trading.flag created (safe warm start)

.EXAMPLE
    .\start_loop.ps1 -Mode shadow -SleepSeconds 1800
    Start loop in shadow mode with 30-minute ticks
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("shadow", "paper")]
    [string]$Mode = "paper",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [int]$SleepSeconds = 0,  # Default 0 = use runtime state interval

    [Parameter(Mandatory=$false)]
    [switch]$CreatePauseFlag,

    [Parameter(Mandatory=$false)]
    [switch]$LogToFile
)

$ErrorActionPreference = "Stop"

# Get repository root (2 levels up from tools/windows)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

Write-Host "AI Trader Loop Startup" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Mode: $Mode"
Write-Host "Dry-Run: $DryRun"
Write-Host "Sleep Interval: $SleepSeconds seconds ($([math]::Round($SleepSeconds / 60.0, 1)) minutes)"
Write-Host "Create Pause Flag: $CreatePauseFlag"
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# Setup logging if requested
$LogFile = $null
if ($LogToFile) {
    $LogDir = Join-Path $RepoRoot "logs\loop"
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }

    $LogFile = Join-Path $LogDir "loop_$(Get-Date -Format 'yyyyMMdd').log"
    $Timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    @"
================================================================================
[$Timestamp] LOOP STARTUP
================================================================================
Mode: $Mode
Dry-Run: $DryRun
Sleep Interval: $SleepSeconds seconds
Create Pause Flag: $CreatePauseFlag
Repository: $RepoRoot
================================================================================

"@ | Tee-Object -FilePath $LogFile -Append
}

# Check if virtual environment exists
$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    $ErrorMsg = "ERROR: Virtual environment not found at $VenvPath"
    if ($LogFile) {
        $ErrorMsg | Tee-Object -FilePath $LogFile -Append
    } else {
        Write-Host $ErrorMsg -ForegroundColor Red
    }
    exit 1
}

# Create pause_trading.flag if requested (safe warm start)
if ($CreatePauseFlag) {
    $StateDir = Join-Path $RepoRoot "state"
    if (-not (Test-Path $StateDir)) {
        New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    }

    $PauseFlagPath = Join-Path $StateDir "pause_trading.flag"
    if (-not (Test-Path $PauseFlagPath)) {
        "" | Out-File -FilePath $PauseFlagPath -Encoding utf8
        $SafetyMsg = "SAFETY: Created pause_trading.flag for safe warm start"
        if ($LogFile) {
            $SafetyMsg | Tee-Object -FilePath $LogFile -Append
        } else {
            Write-Host $SafetyMsg -ForegroundColor Yellow
        }
        Write-Host "Remove $PauseFlagPath to enable live trading" -ForegroundColor Yellow
        Write-Host ""
    }
}

# Build command arguments
$Args = @(
    "-m", "src.app.runner",
    "--mode", $Mode,
    "--loop",
    "--sleep-seconds", $SleepSeconds
)

if ($DryRun) {
    $Args += "--dry-run"
}

$CommandStr = "python $($Args -join ' ')"
if ($LogFile) {
    "Command: $CommandStr`n" | Tee-Object -FilePath $LogFile -Append
}

Write-Host "Starting loop..." -ForegroundColor Green
Write-Host "Command: $CommandStr" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Run the loop
try {
    if ($LogFile) {
        & "$VenvPath\Scripts\python.exe" @Args 2>&1 | Tee-Object -FilePath $LogFile -Append
        $ExitCode = $LASTEXITCODE
        "[$((Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))] Loop exited with code: $ExitCode" | Tee-Object -FilePath $LogFile -Append
        exit $ExitCode
    } else {
        & "$VenvPath\Scripts\python.exe" @Args
        exit $LASTEXITCODE
    }
} catch {
    $ErrorMsg = "ERROR: Loop failed: $_"
    if ($LogFile) {
        $ErrorMsg | Tee-Object -FilePath $LogFile -Append
    } else {
        Write-Host $ErrorMsg -ForegroundColor Red
    }
    exit 1
}
