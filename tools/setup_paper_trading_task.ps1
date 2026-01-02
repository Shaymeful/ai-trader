# AI Trader - Paper Trading Task Scheduler Setup
# Sets up hourly paper trading with automatic open order cancellation
# Run this script as Administrator

param(
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
$TaskName = "AI-Trader-Paper-Hourly"

# Handle task removal
if ($Remove) {
    Write-Host "Removing task: $TaskName" -ForegroundColor Yellow

    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "[OK] Task removed successfully" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Failed to remove task: $_" -ForegroundColor Red
        exit 1
    }

    exit 0
}

# Display configuration
Write-Host ""
Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host "  AI Trader - Paper Trading Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Task Name:      $TaskName"
Write-Host "  Mode:           paper (LIVE orders, NOT dry-run)"
Write-Host "  Schedule:       Hourly during market hours (Mon-Fri, 09:35-15:35 EST)"
Write-Host "  Command:        python.exe -m src.app.runner --mode paper --cancel-open-orders"
Write-Host "  Python:         .venv\Scripts\python.exe"
Write-Host "  Working Dir:    $ProjectRoot"
Write-Host "  Run As:         $env:USERNAME (highest privileges)"
Write-Host ""
Write-Host "Log Files:" -ForegroundColor Yellow
Write-Host "  stdout:         logs\paper_live_stdout.log"
Write-Host "  stderr:         logs\paper_live_stderr.log"
Write-Host ""

# Confirm with user
$Confirm = Read-Host "Create this scheduled task? (Y/N)"
if ($Confirm -ne "Y" -and $Confirm -ne "y") {
    Write-Host "Cancelled by user" -ForegroundColor Yellow
    exit 0
}

# Ensure logs directory exists
$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

# Build Python command with logging
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$StdoutLog = Join-Path $LogsDir "paper_live_stdout.log"
$StderrLog = Join-Path $LogsDir "paper_live_stderr.log"

# PowerShell wrapper script to handle logging
$WrapperScript = @"
Set-Location '$ProjectRoot'
& '$PythonExe' -m src.app.runner --mode paper --cancel-open-orders >> '$StdoutLog' 2>> '$StderrLog'
"@

# Create wrapper script file
$WrapperScriptPath = Join-Path $ProjectRoot "tools\run_paper_trading.ps1"
$WrapperScript | Out-File -FilePath $WrapperScriptPath -Encoding UTF8 -Force

# Create scheduled task action
$Action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
                                  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WrapperScriptPath`"" `
                                  -WorkingDirectory $ProjectRoot

# Create triggers for hourly execution during market hours (9:35 AM - 3:35 PM EST, Mon-Fri)
$Triggers = @()

# Create 6 triggers: 9:35, 10:35, 11:35, 12:35, 13:35, 14:35, 15:35
$TriggerTimes = @("09:35", "10:35", "11:35", "12:35", "13:35", "14:35", "15:35")

foreach ($Time in $TriggerTimes) {
    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
    $Triggers += $Trigger
}

# Create task settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries `
                                         -StartWhenAvailable `
                                         -RunOnlyIfNetworkAvailable `
                                         -MultipleInstances Queue `
                                         -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Create principal (run as current user with highest privileges)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask -TaskName $TaskName `
                          -Action $Action `
                          -Trigger $Triggers `
                          -Settings $Settings `
                          -Principal $Principal `
                          -Description "AI Trader paper trading with automatic order cancellation - runs hourly during market hours" `
                          -Force

    Write-Host ""
    Write-Host "[OK] Scheduled task created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Yellow
    Write-Host "  Name:        $TaskName"
    Write-Host "  Status:      Ready"
    Write-Host "  Schedule:    Mon-Fri at 9:35, 10:35, 11:35, 12:35, 13:35, 14:35, 15:35 EST"
    Write-Host "  Timeout:     30 minutes per run"
    Write-Host ""
    Write-Host "Management Commands:" -ForegroundColor Yellow
    Write-Host "  View task:    Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  View details: Get-ScheduledTask -TaskName '$TaskName' | Format-List *"
    Write-Host "  Start now:    Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Stop task:    Stop-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Remove task:  .\tools\setup_paper_trading_task.ps1 -Remove"
    Write-Host ""
    Write-Host "Log Files:" -ForegroundColor Yellow
    Write-Host "  stdout:       logs\paper_live_stdout.log"
    Write-Host "  stderr:       logs\paper_live_stderr.log"
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "  1. Test the task manually: Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  2. Monitor stdout:          Get-Content logs\paper_live_stdout.log -Tail 20 -Wait"
    Write-Host "  3. Monitor stderr:          Get-Content logs\paper_live_stderr.log -Tail 20 -Wait"
    Write-Host ""
    Write-Host "IMPORTANT:" -ForegroundColor Red
    Write-Host "  - This task will submit LIVE orders to Alpaca paper trading account"
    Write-Host "  - Ensure ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY are set in .env"
    Write-Host "  - Test manually first before relying on automation"
    Write-Host ""
    Write-Host "=================================================================================" -ForegroundColor Cyan

} catch {
    Write-Host ""
    Write-Host "[ERROR] Failed to create scheduled task" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    exit 1
}
