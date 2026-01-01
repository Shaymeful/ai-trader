$ErrorActionPreference = "Stop"

$root   = "C:\dev\ai-trader"
$python = Join-Path $root ".venv\Scripts\python.exe"
$runner = Join-Path $root "src\app\runner.py"
$logDir = Join-Path $root "logs"
$tslog  = Join-Path $logDir "task_scheduler.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# NOTE: Single-instance enforcement is handled by the Python runner's mutex/file lock guard.
# This wrapper simply launches the runner and waits for it to exit.
# Running runner.py directly (not via -m) reduces likelihood of Windows python->python re-exec.

Add-Content $tslog ("[{0}] Starting runner (Script PID: {1})" -f (Get-Date), $PID)
Add-Content $tslog ("[{0}]   Python: {1}" -f (Get-Date), $python)
Add-Content $tslog ("[{0}]   Runner: {1}" -f (Get-Date), $runner)
Add-Content $tslog ("[{0}]   Working Dir: {1}" -f (Get-Date), $root)

$p = Start-Process -FilePath $python `
      -ArgumentList @($runner, "--mode", "paper", "--loop", "--sleep-seconds", "3600", "--dry-run") `
      -WorkingDirectory $root `
      -NoNewWindow `
      -PassThru

Add-Content $tslog ("[{0}] Runner started (Runner PID: {1})" -f (Get-Date), $p.Id)

# Wait for runner to exit (or until crash/exit)
$p.WaitForExit()
Add-Content $tslog ("[{0}] Runner exited. ExitCode={1} (Runner PID: {2}, Script PID: {3})" -f (Get-Date), $p.ExitCode, $p.Id, $PID)
exit $p.ExitCode
