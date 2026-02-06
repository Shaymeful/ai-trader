#Requires -RunAsAdministrator
# Fix AITrader-Selector task to be hidden

$ErrorActionPreference = "Stop"

$TaskName = "AITrader-Selector"

Write-Host "Updating $TaskName to be hidden..." -ForegroundColor Cyan

try {
    # Get existing task
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop

    Write-Host "Current Hidden setting: $($Task.Settings.Hidden)" -ForegroundColor Gray

    # Export task XML
    $Xml = Export-ScheduledTask -TaskName $TaskName

    # Parse XML
    [xml]$TaskXml = $Xml

    # Update Hidden setting
    if ($TaskXml.Task.Settings.Hidden) {
        $TaskXml.Task.Settings.Hidden = 'true'
    } else {
        # Add Hidden element if it doesn't exist
        $hiddenElement = $TaskXml.CreateElement('Hidden', $TaskXml.Task.Settings.NamespaceURI)
        $hiddenElement.InnerText = 'true'
        $TaskXml.Task.Settings.AppendChild($hiddenElement) | Out-Null
    }

    # Update PowerShell action to add -WindowStyle Hidden
    foreach ($action in $TaskXml.Task.Actions.Exec) {
        if ($action.Command -eq 'PowerShell.exe') {
            $currentArgs = $action.Arguments
            if ($currentArgs -notmatch '-WindowStyle Hidden') {
                # Add -WindowStyle Hidden after -ExecutionPolicy Bypass
                $newArgs = $currentArgs -replace '(-ExecutionPolicy Bypass)', '$1 -WindowStyle Hidden'
                $action.Arguments = $newArgs
                Write-Host "Updated arguments to include -WindowStyle Hidden" -ForegroundColor Yellow
            }
        }
    }

    # Save to temp file
    $TempFile = [System.IO.Path]::GetTempFileName()
    $TaskXml.Save($TempFile)

    # Re-register task
    Write-Host "Re-registering task with updated settings..." -ForegroundColor Gray
    Register-ScheduledTask -TaskName $TaskName -Xml (Get-Content $TempFile -Raw) -Force | Out-Null

    # Clean up
    Remove-Item $TempFile -Force

    # Verify
    $UpdatedTask = Get-ScheduledTask -TaskName $TaskName

    Write-Host ""
    Write-Host "[SUCCESS] Task updated!" -ForegroundColor Green
    Write-Host "  Hidden setting: $($UpdatedTask.Settings.Hidden)" -ForegroundColor Gray
    Write-Host "  Task will now run without showing console windows" -ForegroundColor Gray

} catch {
    Write-Host "[ERROR] Failed to update task: $_" -ForegroundColor Red
    exit 1
}
