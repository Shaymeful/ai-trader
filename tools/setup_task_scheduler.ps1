# AI Trader - Windows Task Scheduler Setup Script
# Run this script as Administrator to set up hourly automated trading

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("shadow", "paper")]
    [string]$Mode = "shadow",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [string]$TaskName = "AI-Trader-Hourly",

    [Parameter(Mandatory=$false)]
    [string]$StartTime = "09:30",

    [Parameter(Mandatory=$false)]
    [switch]$Remove
)

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

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Handle task removal
if ($Remove) {
    Write-Host "Removing task: $TaskName" -ForegroundColor Yellow

    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "✓ Task removed successfully" -ForegroundColor Green
    } catch {
        Write-Host "✗ Failed to remove task: $_" -ForegroundColor Red
        exit 1
    }

    exit 0
}

# Display configuration
Write-Host ""
Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host "  AI Trader - Windows Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Task Name:      $TaskName"
Write-Host "  Mode:           $Mode"
Write-Host "  Dry-Run:        $DryRun"
Write-Host "  Start Time:     $StartTime (daily)"
Write-Host "  Interval:       Every 1 hour"
Write-Host "  Project Root:   $ProjectRoot"
Write-Host ""

# Confirm with user
$Confirm = Read-Host "Create this scheduled task? (Y/N)"
if ($Confirm -ne "Y" -and $Confirm -ne "y") {
    Write-Host "Cancelled by user" -ForegroundColor Yellow
    exit 0
}

# Build PowerShell command
$RunLoopScript = Join-Path $ScriptDir "run_loop.ps1"
$PSArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunLoopScript`" -Mode $Mode -SleepSeconds 3600"

if ($DryRun) {
    $PSArgs += " -DryRun"
}

# Create scheduled task action
$Action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
                                  -Argument $PSArgs `
                                  -WorkingDirectory $ProjectRoot

# Create trigger (daily at start time, repeat every hour for 23.5 hours)
$Trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$Trigger.Repetition = [CimInstance]::new("MSFT_TaskRepetitionPattern")
$Trigger.Repetition.Interval = "PT1H"  # Repeat every 1 hour
$Trigger.Repetition.Duration = "PT23H30M"  # For 23.5 hours (resets at next start time)

# Create task settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries `
                                         -StartWhenAvailable `
                                         -RunOnlyIfNetworkAvailable `
                                         -MultipleInstances IgnoreNew

# Create principal (run as current user)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask -TaskName $TaskName `
                          -Action $Action `
                          -Trigger $Trigger `
                          -Settings $Settings `
                          -Principal $Principal `
                          -Description "AI Trader hourly loop runner ($Mode mode)" `
                          -Force

    Write-Host ""
    Write-Host "✓ Scheduled task created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Yellow
    Write-Host "  Name:        $TaskName"
    Write-Host "  Status:      Ready"
    Write-Host "  Start Time:  $StartTime (daily)"
    Write-Host "  Interval:    Every 1 hour"
    Write-Host ""
    Write-Host "Management Commands:" -ForegroundColor Yellow
    Write-Host "  View task:    Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Start now:    Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Stop task:    Stop-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Remove task:  .\tools\setup_task_scheduler.ps1 -Remove"
    Write-Host ""
    Write-Host "Log Files:" -ForegroundColor Yellow
    Write-Host "  Task log:     logs\task_scheduler.log"
    Write-Host "  Loop status:  logs\loop_status.log"
    Write-Host "  Loop errors:  logs\loop_errors.log"
    Write-Host "  stdout:       logs\loop_stdout.log"
    Write-Host "  stderr:       logs\loop_stderr.log"
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "  1. Test the task: Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  2. Monitor logs:  Get-Content logs\loop_status.log -Tail 10 -Wait"
    Write-Host "  3. Stop task:     Stop-ScheduledTask -TaskName '$TaskName'"
    Write-Host ""
    Write-Host "=================================================================================" -ForegroundColor Cyan

} catch {
    Write-Host ""
    Write-Host "✗ Failed to create scheduled task" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    exit 1
}
