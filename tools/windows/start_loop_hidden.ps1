#Requires -Version 5.1
<#
.SYNOPSIS
    Start AI Trader loop hidden (no pop-up windows).

.DESCRIPTION
    Starts the trading loop in a hidden window using the regular start_loop.ps1 script.
    This version is designed to run from Task Scheduler without showing pop-up windows.

    All parameters are passed through to start_loop.ps1.

.PARAMETER Mode
    Trading mode: shadow or paper (default: paper)

.PARAMETER DryRun
    Run in dry-run mode (no actual orders placed)

.PARAMETER SleepSeconds
    Sleep interval between loop iterations in seconds (default: 3600 = 1 hour)

.PARAMETER CreatePauseFlag
    Create pause_trading.flag at startup for safe warm start

.EXAMPLE
    .\start_loop_hidden.ps1
    Start loop in paper mode with hourly ticks (hidden)

.EXAMPLE
    .\start_loop_hidden.ps1 -Mode paper -SleepSeconds 300
    Start loop in paper mode with 5-minute ticks (hidden)
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("shadow", "paper")]
    [string]$Mode = "paper",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [int]$SleepSeconds = 3600,

    [Parameter(Mandatory=$false)]
    [switch]$CreatePauseFlag
)

$ErrorActionPreference = "Stop"

# Get repository root (2 levels up from tools/windows)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$StartLoopScript = Join-Path $PSScriptRoot "start_loop.ps1"

# Build arguments for start_loop.ps1
$Args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden",
    "-File", $StartLoopScript,
    "-Mode", $Mode,
    "-SleepSeconds", $SleepSeconds,
    "-LogToFile"
)

if ($DryRun) {
    $Args += "-DryRun"
}

if ($CreatePauseFlag) {
    $Args += "-CreatePauseFlag"
}

# Start the loop hidden
Start-Process -FilePath "PowerShell.exe" -ArgumentList $Args -WorkingDirectory $RepoRoot -WindowStyle Hidden
