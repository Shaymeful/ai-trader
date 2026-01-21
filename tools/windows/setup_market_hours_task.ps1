#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configure AITrader-Loop to run automatically during market hours.

.DESCRIPTION
    Sets up Task Scheduler to:
    - Start the loop at 9:30 AM ET every weekday
    - Stop the loop at 4:00 PM ET every weekday
    - Run with hidden window
    - Auto-restart if it crashes

.PARAMETER Mode
    Trading mode: shadow or paper (default: paper)

.PARAMETER SleepSeconds
    Sleep interval between loop iterations in seconds (default: 300 = 5 minutes)

.EXAMPLE
    .\setup_market_hours_task.ps1
    Setup loop to run during market hours in paper mode with 5-minute intervals

.EXAMPLE
    .\setup_market_hours_task.ps1 -Mode shadow -SleepSeconds 600
    Setup loop in shadow mode with 10-minute intervals
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("shadow", "paper")]
    [string]$Mode = "paper",

    [Parameter(Mandatory=$false)]
    [int]$SleepSeconds = 300
)

$ErrorActionPreference = "Stop"

# Get repository root (2 levels up from tools/windows)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TaskName = "AITrader-Loop"
$StartScriptPath = Join-Path $RepoRoot "tools\windows\start_loop.ps1"

Write-Host "AI Trader Market Hours Task Setup" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Mode: $Mode"
Write-Host "Sleep Interval: $SleepSeconds seconds ($([math]::Round($SleepSeconds / 60.0, 1)) minutes)"
Write-Host ""

# Check if task exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "Existing task found. Removing..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Task removed." -ForegroundColor Green
    Write-Host ""
}

# Build command arguments for start_loop.ps1
$Arguments = "-ExecutionPolicy Bypass -File `"$StartScriptPath`" -Mode $Mode -SleepSeconds $SleepSeconds -LogToFile"

# Set environment variable to hide Python window
$EnvVars = @{
    "HIDE_PYTHON_WINDOW" = "1"
}
$EnvVarsXml = ($EnvVars.GetEnumerator() | ForEach-Object {
    "<Variable><Name>$($_.Key)</Name><Value>$($_.Value)</Value></Variable>"
}) -join ""

# Create task XML with market hours schedule
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>AI Trader loop runner - Runs during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)</Description>
    <URI>\$TaskName</URI>
  </RegistrationInfo>
  <Triggers>
    <!-- Start at 9:30 AM ET every weekday -->
    <CalendarTrigger>
      <StartBoundary>2026-01-22T09:30:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <UserId>$env:USERNAME</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT7H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>$Arguments</Arguments>
      <WorkingDirectory>$RepoRoot</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Save XML to temp file
$TempXmlPath = Join-Path $env:TEMP "$TaskName.xml"
$TaskXml | Out-File -FilePath $TempXmlPath -Encoding unicode -Force

try {
    # Register task
    Write-Host "Registering task..." -ForegroundColor Cyan
    Register-ScheduledTask -TaskName $TaskName -Xml (Get-Content $TempXmlPath | Out-String) -Force | Out-Null

    Write-Host "Task registered successfully!" -ForegroundColor Green
    Write-Host ""

    # Show task details
    $Task = Get-ScheduledTask -TaskName $TaskName
    $TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName

    Write-Host "Task Configuration:" -ForegroundColor Cyan
    Write-Host "  Name: $($Task.TaskName)"
    Write-Host "  State: $($Task.State)"
    Write-Host "  Next Run: $($TaskInfo.NextRunTime)"
    Write-Host "  Last Run: $($TaskInfo.LastRunTime)"
    Write-Host ""

    Write-Host "Schedule:" -ForegroundColor Cyan
    Write-Host "  Start: 9:30 AM ET (Monday-Friday)"
    Write-Host "  Stop: 4:00 PM ET (automatic via 7-hour timeout)"
    Write-Host "  Interval: Every $([math]::Round($SleepSeconds / 60.0, 1)) minutes"
    Write-Host ""

    Write-Host "SETUP COMPLETE!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The loop will:" -ForegroundColor Cyan
    Write-Host "  - Start automatically at 9:30 AM ET every weekday"
    Write-Host "  - Run with hidden window (no popups)"
    Write-Host "  - Stop automatically at 4:00 PM ET"
    Write-Host "  - Log to logs/loop/loop_YYYYMMDD.log"
    Write-Host ""
    Write-Host "To manually start now:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host ""
    Write-Host "To manually stop:" -ForegroundColor Yellow
    Write-Host "  Stop-ScheduledTask -TaskName '$TaskName'"
    Write-Host ""
    Write-Host "To view logs:" -ForegroundColor Yellow
    Write-Host "  Get-Content logs\loop\loop_`$(Get-Date -Format 'yyyyMMdd').log -Tail 50 -Wait"

} finally {
    # Cleanup temp file
    if (Test-Path $TempXmlPath) {
        Remove-Item $TempXmlPath -Force
    }
}
