#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install Windows Scheduled Tasks for AI Trader morning automation.

.DESCRIPTION
    Creates 3 scheduled tasks for automated morning trading:

    1. AITrader-Dashboard (8:45 AM ET)
       - Starts FastAPI dashboard for monitoring
       - Provides status, controls, and candidate view
       - Runs continuously in background

    2. AITrader-Selector (Every 15 min, 8:50 AM - 4:10 PM ET)
       - Fetches RSS feeds and generates candidates
       - Writes to out/selector/snapshot.json
       - Runs selector once per execution

    3. AITrader-Loop (9:00 AM ET, hourly)
       - Processes candidates and generates orders
       - Respects pause_trading.flag
       - Repeats every hour during market hours

    IMPORTANT: These tasks use Eastern Time (ET) for market hours, even though
    the host machine may be in a different timezone (e.g., Indiana).

.PARAMETER Mode
    Trading mode for loop: shadow or paper (default: paper for safety)

.PARAMETER DryRun
    Run loop in dry-run mode (no actual orders placed)

.PARAMETER CreatePauseFlag
    Create pause_trading.flag at startup for safe warm start

.PARAMETER Remove
    Remove all AITrader scheduled tasks

.PARAMETER RemoveTask
    Remove a specific task by name (Dashboard, Selector, or Loop)

.EXAMPLE
    .\install_tasks.ps1
    Install all 3 tasks in paper mode

.EXAMPLE
    .\install_tasks.ps1 -DryRun
    Install all 3 tasks with loop in dry-run mode

.EXAMPLE
    .\install_tasks.ps1 -CreatePauseFlag
    Install tasks with pause_trading.flag created for safety

.EXAMPLE
    .\install_tasks.ps1 -Remove
    Remove all AITrader scheduled tasks

.EXAMPLE
    .\install_tasks.ps1 -RemoveTask Selector
    Remove only the Selector task
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("shadow", "paper")]
    [string]$Mode = "paper",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [switch]$CreatePauseFlag,

    [Parameter(Mandatory=$false)]
    [switch]$Remove,

    [Parameter(Mandatory=$false)]
    [ValidateSet("Dashboard", "Selector", "Loop")]
    [string]$RemoveTask
)

$ErrorActionPreference = "Stop"

# Get repository root (2 levels up from tools/windows)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Check if running as Administrator
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host ""
    Write-Host "To run as Administrator:" -ForegroundColor Yellow
    Write-Host "  1. Right-click PowerShell" -ForegroundColor Yellow
    Write-Host "  2. Select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host "  3. Run this script again" -ForegroundColor Yellow
    exit 1
}

# Task names
$TaskNames = @{
    Dashboard = "AITrader-Dashboard"
    Selector  = "AITrader-Selector"
    Loop      = "AITrader-Loop"
}

# Handle task removal
if ($Remove) {
    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor Yellow
    Write-Host "  REMOVING ALL AITrader Scheduled Tasks" -ForegroundColor Yellow
    Write-Host "=" * 80 -ForegroundColor Yellow
    Write-Host ""

    $RemovedCount = 0
    foreach ($TaskName in $TaskNames.Values) {
        try {
            $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if ($Task) {
                Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
                Write-Host "[OK] Removed: $TaskName" -ForegroundColor Green
                $RemovedCount++
            } else {
                Write-Host "[SKIP] Not found: $TaskName" -ForegroundColor Gray
            }
        } catch {
            Write-Host "[ERROR] Failed to remove $TaskName : $_" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "Removed $RemovedCount task(s)" -ForegroundColor Cyan
    exit 0
}

if ($RemoveTask) {
    $TaskName = $TaskNames[$RemoveTask]
    Write-Host "Removing task: $TaskName" -ForegroundColor Yellow

    try {
        $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($Task) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
            Write-Host "[OK] Task removed successfully" -ForegroundColor Green
        } else {
            Write-Host "[WARN] Task not found: $TaskName" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[ERROR] Failed to remove task: $_" -ForegroundColor Red
        exit 1
    }

    exit 0
}

# Display configuration
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "  AI Trader - Windows Task Scheduler Installation" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
Write-Host "This will create 3 scheduled tasks for morning automation:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. $($TaskNames.Dashboard) (8:45 AM ET)" -ForegroundColor White
Write-Host "   - Starts dashboard for monitoring and controls"
Write-Host "   - Runs continuously in background"
Write-Host ""
Write-Host "2. $($TaskNames.Selector) (Every 15 min, 8:50 AM - 4:10 PM ET)" -ForegroundColor White
Write-Host "   - Fetches RSS feeds and generates candidates"
Write-Host "   - Writes to out/selector/snapshot.json"
Write-Host ""
Write-Host "3. $($TaskNames.Loop) (9:00 AM ET, hourly)" -ForegroundColor White
Write-Host "   - Processes candidates and generates orders"
Write-Host "   - Respects pause_trading.flag"
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Mode:               $Mode"
Write-Host "  Dry-Run:            $DryRun"
Write-Host "  Create Pause Flag:  $CreatePauseFlag"
Write-Host "  Repository:         $RepoRoot"
Write-Host ""

# Safety warning
if (-not $DryRun -and $Mode -eq "paper" -and -not $CreatePauseFlag) {
    Write-Host "WARNING: Loop will place REAL PAPER TRADING orders!" -ForegroundColor Red
    Write-Host "Consider using -CreatePauseFlag for safe warm start" -ForegroundColor Yellow
    Write-Host ""
}

# Confirm with user
$Confirm = Read-Host "Create these scheduled tasks? (Y/N)"
if ($Confirm -ne "Y" -and $Confirm -ne "y") {
    Write-Host "Cancelled by user" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Creating scheduled tasks..." -ForegroundColor Cyan
Write-Host ""

# Script paths
$DashboardScript = Join-Path $RepoRoot "tools\windows\start_dashboard.ps1"
$SelectorScript = Join-Path $RepoRoot "tools\windows\run_selector.ps1"
$LoopScript = Join-Path $RepoRoot "tools\windows\start_loop.ps1"

# Verify scripts exist
$Scripts = @{
    Dashboard = $DashboardScript
    Selector  = $SelectorScript
    Loop      = $LoopScript
}

foreach ($ScriptInfo in $Scripts.GetEnumerator()) {
    if (-not (Test-Path $ScriptInfo.Value)) {
        Write-Host "[ERROR] Script not found: $($ScriptInfo.Value)" -ForegroundColor Red
        exit 1
    }
}

# Task 1: Dashboard (8:45 AM)
try {
    Write-Host "Creating task: $($TaskNames.Dashboard)..." -ForegroundColor White

    $Action = New-ScheduledTaskAction `
        -Execute "PowerShell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$DashboardScript`"" `
        -WorkingDirectory $RepoRoot

    $Trigger = New-ScheduledTaskTrigger -Daily -At "08:45AM"

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -MultipleInstances IgnoreNew

    $Principal = New-ScheduledTaskPrincipal `
        -UserId (whoami) `
        -LogonType Interactive `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskNames.Dashboard `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "AI Trader Dashboard - Starts at 8:45 AM ET for monitoring" `
        -Force | Out-Null

    Write-Host "  [OK] Created: $($TaskNames.Dashboard)" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to create $($TaskNames.Dashboard): $_" -ForegroundColor Red
    exit 1
}

# Task 2: Selector (Every 15 min, 8:50 AM - 4:10 PM)
try {
    Write-Host "Creating task: $($TaskNames.Selector)..." -ForegroundColor White

    $Action = New-ScheduledTaskAction `
        -Execute "PowerShell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$SelectorScript`" -LogToFile" `
        -WorkingDirectory $RepoRoot

    # Create trigger: Daily at 8:50 AM, repeat every 15 minutes for 7 hours 20 minutes (until 4:10 PM)
    $Trigger = New-ScheduledTaskTrigger -Daily -At "08:50AM"
    # Create repetition pattern using proper CIM class instantiation
    $Repetition = (New-ScheduledTaskTrigger -Once -At "08:50AM" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Hours 7 -Minutes 20)).Repetition
    $Trigger.Repetition = $Repetition

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -MultipleInstances Queue `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

    $Principal = New-ScheduledTaskPrincipal `
        -UserId (whoami) `
        -LogonType Interactive `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskNames.Selector `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "AI Trader Selector - Runs every 15 min (8:50 AM - 4:10 PM ET)" `
        -Force | Out-Null

    Write-Host "  [OK] Created: $($TaskNames.Selector)" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to create $($TaskNames.Selector): $_" -ForegroundColor Red
    exit 1
}

# Task 3: Loop (9:00 AM, hourly)
try {
    Write-Host "Creating task: $($TaskNames.Loop)..." -ForegroundColor White

    # Build loop arguments
    $LoopArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$LoopScript`" -Mode $Mode -SleepSeconds 3600 -LogToFile"

    if ($DryRun) {
        $LoopArgs += " -DryRun"
    }

    if ($CreatePauseFlag) {
        $LoopArgs += " -CreatePauseFlag"
    }

    $Action = New-ScheduledTaskAction `
        -Execute "PowerShell.exe" `
        -Argument $LoopArgs `
        -WorkingDirectory $RepoRoot

    # Create trigger: Daily at 9:00 AM, repeat every 1 hour for 23.5 hours
    $Trigger = New-ScheduledTaskTrigger -Daily -At "09:00AM"
    # Create repetition pattern using proper CIM class instantiation
    $Repetition = (New-ScheduledTaskTrigger -Once -At "09:00AM" -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 30)).Repetition
    $Trigger.Repetition = $Repetition

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -MultipleInstances IgnoreNew

    $Principal = New-ScheduledTaskPrincipal `
        -UserId (whoami) `
        -LogonType Interactive `
        -RunLevel Highest

    $Description = "AI Trader Loop - Runs hourly starting at 9:00 AM ET (Mode: $Mode"
    if ($DryRun) {
        $Description += ", DRY-RUN"
    }
    if ($CreatePauseFlag) {
        $Description += ", with pause flag"
    }
    $Description += ")"

    Register-ScheduledTask `
        -TaskName $TaskNames.Loop `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description $Description `
        -Force | Out-Null

    Write-Host "  [OK] Created: $($TaskNames.Loop)" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to create $($TaskNames.Loop): $_" -ForegroundColor Red
    exit 1
}

# Success summary
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Green
Write-Host ""
Write-Host "Created 3 scheduled tasks:" -ForegroundColor Cyan
Write-Host "  - $($TaskNames.Dashboard)" -ForegroundColor White
Write-Host "  - $($TaskNames.Selector)" -ForegroundColor White
Write-Host "  - $($TaskNames.Loop)" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Verify tasks: Get-ScheduledTask -TaskName 'AITrader-*'" -ForegroundColor White
Write-Host "  2. Test dashboard: .\tools\windows\start_dashboard.ps1" -ForegroundColor White
Write-Host "  3. Test selector: .\tools\windows\run_selector.ps1" -ForegroundColor White
Write-Host "  4. Configure RSS feeds in config/selector.yaml" -ForegroundColor White
Write-Host ""

if ($CreatePauseFlag) {
    Write-Host "IMPORTANT: pause_trading.flag will be created at startup" -ForegroundColor Yellow
    Write-Host "Remove state/pause_trading.flag to enable live trading" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "To remove tasks:" -ForegroundColor Gray
Write-Host "  .\install_tasks.ps1 -Remove" -ForegroundColor Gray
Write-Host ""
