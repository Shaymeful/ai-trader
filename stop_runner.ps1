# Stop any running runner processes
$processes = Get-Process python -ErrorAction SilentlyContinue
foreach ($proc in $processes) {
    $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
    if ($cmdline -like "*runner*paper*" -or $cmdline -like "*runner.py*") {
        Write-Host "Stopping runner process: PID $($proc.Id)"
        Stop-Process -Id $proc.Id -Force
    }
}
Write-Host "Done checking processes"
