# AI Trader - Loop Runner for Windows Task Scheduler
# This script runs the trading bot in loop mode with configurable parameters

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("shadow", "paper")]
    [string]$Mode = "shadow",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [int]$SleepSeconds = 3600,

    [Parameter(Mandatory=$false)]
    [string]$LogFile = "logs\task_scheduler.log"
)

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Change to project directory
Set-Location $ProjectRoot

# Ensure logs directory exists
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Full path to log file
$LogFilePath = Join-Path $ProjectRoot $LogFile

# Log startup
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$StartupMsg = @"

================================================================================
[$Timestamp] TASK SCHEDULER - Starting Loop Runner
================================================================================
Mode: $Mode
Dry-Run: $DryRun
Sleep Interval: $SleepSeconds seconds
Project Root: $ProjectRoot
Log File: $LogFilePath
================================================================================

"@

Add-Content -Path $LogFilePath -Value $StartupMsg

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

# Log command
$Command = "python $($Args -join ' ')"
Add-Content -Path $LogFilePath -Value "Command: $Command`n"

# Run the loop runner
try {
    # Run python with output redirection
    $Process = Start-Process -FilePath "python" `
                            -ArgumentList $Args `
                            -WorkingDirectory $ProjectRoot `
                            -NoNewWindow `
                            -PassThru `
                            -RedirectStandardOutput (Join-Path $ProjectRoot "logs\loop_stdout.log") `
                            -RedirectStandardError (Join-Path $ProjectRoot "logs\loop_stderr.log")

    $SuccessMsg = @"
[$Timestamp] Loop runner started successfully
Process ID: $($Process.Id)
Status: Running

To monitor:
  - Loop status: logs\loop_status.log
  - Loop errors: logs\loop_errors.log
  - stdout: logs\loop_stdout.log
  - stderr: logs\loop_stderr.log

To stop:
  Stop-Process -Id $($Process.Id)

================================================================================
"@

    Add-Content -Path $LogFilePath -Value $SuccessMsg

    # Wait for process (keeps script running)
    $Process.WaitForExit()

    $ExitMsg = @"
[$((Get-Date -Format "yyyy-MM-dd HH:mm:ss"))] Loop runner exited
Exit Code: $($Process.ExitCode)
================================================================================
"@

    Add-Content -Path $LogFilePath -Value $ExitMsg

    exit $Process.ExitCode

} catch {
    $ErrorMsg = @"
[$((Get-Date -Format "yyyy-MM-dd HH:mm:ss"))] ERROR: Failed to start loop runner

Error: $_

Stack Trace:
$($_.ScriptStackTrace)

================================================================================
"@

    Add-Content -Path $LogFilePath -Value $ErrorMsg
    Write-Error $_
    exit 1
}
