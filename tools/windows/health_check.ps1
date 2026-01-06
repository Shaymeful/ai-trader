<#
.SYNOPSIS
Health check script for scheduled AI Trader runs

.DESCRIPTION
Performs comprehensive health checks for AI Trader scheduled tasks, endpoints, logs, and connectivity.
Always exits with code 0, but prints clear READY/NOT READY status.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File tools\windows\health_check.ps1
#>

param()

$ErrorActionPreference = "Continue"
$global:HealthIssues = @()

function Add-Issue {
    param([string]$Message)
    $global:HealthIssues += $Message
}

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Details = ""
    )
    $status = if ($Passed) { "[OK]" } else { "[FAIL]" }
    $color = if ($Passed) { "Green" } else { "Red" }

    Write-Host "$status $Name" -ForegroundColor $color
    if ($Details) {
        Write-Host "      $Details" -ForegroundColor Gray
    }

    if (-not $Passed) {
        Add-Issue $Name
    }
}

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "AI Trader Health Check" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Task Scheduler tasks
Write-Host "1. Task Scheduler Status" -ForegroundColor Yellow
Write-Host "   ----------------------" -ForegroundColor Yellow

$tasks = @("AITrader-Dashboard", "AITrader-Selector", "AITrader-Loop")
foreach ($taskName in $tasks) {
    try {
        $taskInfo = schtasks /query /tn $taskName /fo LIST /v 2>$null | Out-String

        if ($LASTEXITCODE -eq 0) {
            # Parse task info
            $status = if ($taskInfo -match "Status:\s+(.+)") { $matches[1].Trim() } else { "Unknown" }
            $nextRun = if ($taskInfo -match "Next Run Time:\s+(.+)") { $matches[1].Trim() } else { "Unknown" }
            $lastResult = if ($taskInfo -match "Last Result:\s+(.+)") { $matches[1].Trim() } else { "Unknown" }

            $taskOk = ($status -eq "Ready" -or $status -eq "Running") -and $lastResult -eq "0"
            Write-Check $taskName $taskOk "Status: $status | Next: $nextRun | Last: $lastResult"
        } else {
            Write-Check $taskName $false "Task not found"
        }
    } catch {
        Write-Check $taskName $false "Error querying task: $_"
    }
}

Write-Host ""

# 2. Check Dashboard endpoint
Write-Host "2. Dashboard Endpoint" -ForegroundColor Yellow
Write-Host "   ------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/status" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $dashboardOk = $response.StatusCode -eq 200
    Write-Check "Dashboard reachable" $dashboardOk "http://localhost:8000/status - Status $($response.StatusCode)"

    if ($dashboardOk) {
        try {
            $statusData = $response.Content | ConvertFrom-Json
            if ($statusData.mode) {
                Write-Host "      Mode: $($statusData.mode)" -ForegroundColor Gray
            }
            if ($statusData.is_paused -ne $null) {
                Write-Host "      Paused: $($statusData.is_paused)" -ForegroundColor Gray
            }
        } catch {
            # JSON parse failed, but endpoint responded
        }
    }
} catch {
    Write-Check "Dashboard reachable" $false "Timeout or connection failed"
}

Write-Host ""

# 3. Check Selector endpoint
Write-Host "3. Selector Endpoint" -ForegroundColor Yellow
Write-Host "   -----------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/selector/status" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $selectorOk = $response.StatusCode -eq 200
    Write-Check "Selector endpoint reachable" $selectorOk "http://localhost:8000/selector/status - Status $($response.StatusCode)"

    if ($selectorOk) {
        try {
            $selectorData = $response.Content | ConvertFrom-Json
            if ($selectorData.last_run) {
                Write-Host "      Last Run: $($selectorData.last_run)" -ForegroundColor Gray
            }
            if ($selectorData.candidates_count -ne $null) {
                Write-Host "      Candidates: $($selectorData.candidates_count)" -ForegroundColor Gray
            }
        } catch {
            # JSON parse failed, but endpoint responded
        }
    }
} catch {
    Write-Check "Selector endpoint reachable" $false "Timeout or connection failed"
}

Write-Host ""

# 4. Check selector snapshot
Write-Host "4. Selector Snapshot" -ForegroundColor Yellow
Write-Host "   -----------------" -ForegroundColor Yellow

$snapshotPath = "out\selector\snapshot.json"
if (Test-Path $snapshotPath) {
    $snapshotFile = Get-Item $snapshotPath
    $age = (Get-Date) - $snapshotFile.LastWriteTime
    $ageMinutes = [math]::Floor($age.TotalMinutes)

    try {
        $snapshot = Get-Content $snapshotPath -Raw | ConvertFrom-Json
        $count = if ($snapshot.count) { $snapshot.count } else { $snapshot.candidates.Count }

        $snapshotOk = $ageMinutes -lt 120  # Less than 2 hours old
        Write-Check "Snapshot exists" $snapshotOk "Age: ${ageMinutes}m | Count: $count"
    } catch {
        Write-Check "Snapshot exists" $false "File exists but parse failed"
    }
} else {
    Write-Check "Snapshot exists" $false "File not found: $snapshotPath"
}

Write-Host ""

# 5. Check selector logs
Write-Host "5. Selector Logs" -ForegroundColor Yellow
Write-Host "   -------------" -ForegroundColor Yellow

$selectorLogPath = "out\selector\events.jsonl"
if (Test-Path $selectorLogPath) {
    $logFile = Get-Item $selectorLogPath
    $lines = Get-Content $selectorLogPath | Select-Object -Last 20
    Write-Check "Selector events.jsonl exists" $true "Lines: $($lines.Count) (showing last 20)"

    Write-Host ""
    Write-Host "   Last 20 events:" -ForegroundColor Gray
    foreach ($line in $lines) {
        try {
            $event = $line | ConvertFrom-Json
            $timestamp = if ($event.timestamp) { $event.timestamp } else { "?" }
            $type = if ($event.event_type) { $event.event_type } else { "?" }
            Write-Host "      $timestamp | $type" -ForegroundColor DarkGray
        } catch {
            Write-Host "      [parse error]" -ForegroundColor DarkGray
        }
    }
} else {
    Write-Check "Selector events.jsonl exists" $false "File not found: $selectorLogPath"
}

Write-Host ""

# 6. Check loop logs
Write-Host "6. Loop Logs" -ForegroundColor Yellow
Write-Host "   ---------" -ForegroundColor Yellow

$loopLogPath = "logs\loop_status.log"
if (Test-Path $loopLogPath) {
    $logFile = Get-Item $loopLogPath
    $age = (Get-Date) - $logFile.LastWriteTime
    $ageMinutes = [math]::Floor($age.TotalMinutes)

    $lines = Get-Content $loopLogPath | Select-Object -Last 20

    $loopOk = $ageMinutes -lt 60  # Updated within last hour
    Write-Check "Loop log exists" $loopOk "Age: ${ageMinutes}m"

    Write-Host ""
    Write-Host "   Last 20 lines:" -ForegroundColor Gray
    foreach ($line in $lines) {
        Write-Host "      $line" -ForegroundColor DarkGray
    }
} else {
    Write-Check "Loop log exists" $false "File not found: $loopLogPath"
}

Write-Host ""

# 7. Check Python/Uvicorn processes
Write-Host "7. Python Processes" -ForegroundColor Yellow
Write-Host "   ----------------" -ForegroundColor Yellow

try {
    $pythonProcs = Get-Process python -ErrorAction SilentlyContinue
    $uvicornRunning = $false

    if ($pythonProcs) {
        foreach ($proc in $pythonProcs) {
            try {
                $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
                if ($cmdLine -like "*uvicorn*") {
                    $uvicornRunning = $true
                    Write-Check "Uvicorn process running" $true "PID: $($proc.Id)"
                    break
                }
            } catch {
                # Could not get command line, skip
            }
        }

        if (-not $uvicornRunning) {
            Write-Check "Uvicorn process running" $false "Python processes found but no uvicorn"
        }
    } else {
        Write-Check "Uvicorn process running" $false "No python.exe processes found"
    }
} catch {
    Write-Check "Uvicorn process running" $false "Error checking processes: $_"
}

Write-Host ""

# 8. Check Alpaca connectivity (best-effort)
Write-Host "8. Alpaca Connectivity (Best-Effort)" -ForegroundColor Yellow
Write-Host "   ----------------------------------" -ForegroundColor Yellow

$alpacaPaperKey = $env:ALPACA_PAPER_KEY_ID
$alpacaPaperSecret = $env:ALPACA_PAPER_SECRET_KEY

if ($alpacaPaperKey -and $alpacaPaperSecret) {
    try {
        $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${alpacaPaperKey}:${alpacaPaperSecret}"))
        $headers = @{
            "Authorization" = "Basic $auth"
        }

        $response = Invoke-WebRequest -Uri "https://paper-api.alpaca.markets/v2/account" -Headers $headers -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        $alpacaOk = $response.StatusCode -eq 200
        Write-Check "Alpaca Paper API" $alpacaOk "Connected - Status $($response.StatusCode)"

        if ($alpacaOk) {
            try {
                $account = $response.Content | ConvertFrom-Json
                Write-Host "      Account: $($account.account_number)" -ForegroundColor Gray
                Write-Host "      Status: $($account.status)" -ForegroundColor Gray
            } catch {
                # JSON parse failed
            }
        }
    } catch {
        Write-Check "Alpaca Paper API" $false "Connection failed or timeout"
    }
} else {
    Write-Host "   [SKIP] Alpaca credentials not found in environment" -ForegroundColor Gray
    Write-Host "         Set ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY to test" -ForegroundColor Gray
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan

# Summary
if ($global:HealthIssues.Count -eq 0) {
    Write-Host "STATUS: READY" -ForegroundColor Green
    Write-Host "All health checks passed!" -ForegroundColor Green
} else {
    Write-Host "STATUS: NOT READY" -ForegroundColor Red
    Write-Host "$($global:HealthIssues.Count) issue(s) detected:" -ForegroundColor Red
    foreach ($issue in $global:HealthIssues) {
        Write-Host "  - $issue" -ForegroundColor Red
    }
}

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Always exit 0
exit 0
