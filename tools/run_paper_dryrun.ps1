$ErrorActionPreference = "Stop"

$root   = "C:\dev\ai-trader"
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
$lock   = Join-Path $logDir "paper_dryrun.lock"
$tslog  = Join-Path $logDir "task_scheduler.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Atomic lock: if another instance has the lock, this will throw and we exit.
# FileShare.None means exclusive access - no other process can open this file.
try {
  $fs = [System.IO.File]::Open($lock, "OpenOrCreate", "ReadWrite", "None")
  Add-Content $tslog ("[{0}] Lock acquired (PID: {1})" -f (Get-Date), $PID)
} catch {
  Add-Content $tslog ("[{0}] BLOCKED: Lock held by another instance. Exiting. (PID: {1})" -f (Get-Date), $PID)
  exit 0
}

try {
  Add-Content $tslog ("[{0}] Starting runner: {1} -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run" -f (Get-Date), $python)

  $p = Start-Process -FilePath $python `
        -ArgumentList @("-m","src.app.runner","--mode","paper","--loop","--sleep-seconds","3600","--dry-run") `
        -WorkingDirectory $root `
        -NoNewWindow `
        -PassThru

  Add-Content $tslog ("[{0}] Runner PID: {1}" -f (Get-Date), $p.Id)

  # Wait forever (or until crash/exit). Lock stays held while we wait.
  $p.WaitForExit()
  Add-Content $tslog ("[{0}] Runner exited. ExitCode={1} (Runner PID: {2}, Script PID: {3})" -f (Get-Date), $p.ExitCode, $p.Id, $PID)
  exit $p.ExitCode
}
finally {
  if ($fs) {
    $fs.Dispose()
    Add-Content $tslog ("[{0}] Lock released (PID: {1})" -f (Get-Date), $PID)
  }
}
