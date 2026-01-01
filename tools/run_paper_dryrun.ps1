$ErrorActionPreference = "Stop"

$root   = "C:\dev\ai-trader"
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
$tslog  = Join-Path $logDir "task_scheduler.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# NOTE: Single-instance enforcement is handled by the Python runner's mutex/file lock guard.
# The runner uses early parent process detection to catch and exit re-exec children immediately.
# We continue using -m for proper module imports (direct runner.py breaks imports).

Add-Content $tslog ("[{0}] Starting runner (Script PID: {1})" -f (Get-Date), $PID)
Add-Content $tslog ("[{0}]   Python: {1}" -f (Get-Date), $python)
Add-Content $tslog ("[{0}]   Module: src.app.runner" -f (Get-Date))
Add-Content $tslog ("[{0}]   Working Dir: {1}" -f (Get-Date), $root)

$p = Start-Process -FilePath $python `
      -ArgumentList @("-m", "src.app.runner", "--mode", "paper", "--loop", "--sleep-seconds", "3600", "--dry-run") `
      -WorkingDirectory $root `
      -NoNewWindow `
      -PassThru

Add-Content $tslog ("[{0}] Runner started (Runner PID: {1})" -f (Get-Date), $p.Id)

# Wait for runner to exit (or until crash/exit)
$p.WaitForExit()
Add-Content $tslog ("[{0}] Runner exited. ExitCode={1} (Runner PID: {2}, Script PID: {3})" -f (Get-Date), $p.ExitCode, $p.Id, $PID)
exit $p.ExitCode
