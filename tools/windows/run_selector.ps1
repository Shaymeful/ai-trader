#Requires -Version 5.1
<#
.SYNOPSIS
    Run RSS selector once to generate trading candidates.

.DESCRIPTION
    Runs the RSS selector to fetch and process automation/energy sector news.
    Generates candidates and writes to out/selector/snapshot.json.

    Scheduled to run every 15 minutes during market hours (8:50 AM - 4:10 PM ET).

    The selector:
    - Fetches configured RSS feeds
    - Classifies headlines into automation/energy sectors
    - Extracts stock symbols conservatively (explicit patterns only)
    - Maps sentiment to buy/sell/watch actions
    - Computes confidence scores
    - Writes candidates to snapshot.json
    - Appends events to events.jsonl

.PARAMETER LogToFile
    If specified, append output to a log file in logs/selector/

.EXAMPLE
    .\run_selector.ps1
    Run selector and output to console

.EXAMPLE
    .\run_selector.ps1 -LogToFile
    Run selector and log to logs/selector/selector_YYYYMMDD.log
#>

param(
    [Parameter(Mandatory=$false)]
    [switch]$LogToFile
)

$ErrorActionPreference = "Stop"

# Get repository root (2 levels up from tools/windows)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

# Setup logging if requested
if ($LogToFile) {
    $LogDir = Join-Path $RepoRoot "logs\selector"
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }

    $LogFile = Join-Path $LogDir "selector_$(Get-Date -Format 'yyyyMMdd').log"
    $Timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    "[$Timestamp] Starting selector run..." | Tee-Object -FilePath $LogFile -Append
}

# Check if virtual environment exists
$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    $ErrorMsg = "ERROR: Virtual environment not found at $VenvPath"
    if ($LogToFile) {
        $ErrorMsg | Tee-Object -FilePath $LogFile -Append
    } else {
        Write-Host $ErrorMsg -ForegroundColor Red
    }
    exit 1
}

# Check if config exists
$ConfigPath = Join-Path $RepoRoot "config\selector.yaml"
if (-not (Test-Path $ConfigPath)) {
    $ErrorMsg = "ERROR: Selector config not found: $ConfigPath"
    if ($LogToFile) {
        $ErrorMsg | Tee-Object -FilePath $LogFile -Append
    } else {
        Write-Host $ErrorMsg -ForegroundColor Red
    }
    exit 1
}

# Run selector
try {
    if ($LogToFile) {
        & "$VenvPath\Scripts\python.exe" -m src.app.selector.run_once 2>&1 | Tee-Object -FilePath $LogFile -Append
        $ExitCode = $LASTEXITCODE
        "[$Timestamp] Selector run completed with exit code: $ExitCode" | Tee-Object -FilePath $LogFile -Append
        exit $ExitCode
    } else {
        & "$VenvPath\Scripts\python.exe" -m src.app.selector.run_once
        exit $LASTEXITCODE
    }
} catch {
    $ErrorMsg = "ERROR: Selector failed: $_"
    if ($LogToFile) {
        $ErrorMsg | Tee-Object -FilePath $LogFile -Append
    } else {
        Write-Host $ErrorMsg -ForegroundColor Red
    }
    exit 1
}
