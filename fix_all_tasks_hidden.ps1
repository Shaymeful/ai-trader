#Requires -RunAsAdministrator
# Fix all AITrader tasks to be hidden

$ErrorActionPreference = "Stop"

$TaskNames = @('AITrader-Selector', 'AITrader-Dashboard')

Write-Host "Fixing AITrader scheduled tasks to run hidden..." -ForegroundColor Cyan
Write-Host ""

foreach ($TaskName in $TaskNames) {
    try {
        # Check if task exists
        $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $Task) {
            Write-Host "[$TaskName] Task not found, skipping" -ForegroundColor Yellow
            continue
        }

        Write-Host "[$TaskName] Current Hidden setting: $($Task.Settings.Hidden)" -ForegroundColor Gray

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
        $actionUpdated = $false
        foreach ($action in $TaskXml.Task.Actions.Exec) {
            if ($action.Command -match 'PowerShell') {
                $currentArgs = $action.Arguments
                if ($currentArgs -notmatch '-WindowStyle Hidden') {
                    # Add -WindowStyle Hidden after -ExecutionPolicy Bypass
                    $newArgs = $currentArgs -replace '(-ExecutionPolicy Bypass)', '$1 -WindowStyle Hidden'
                    $action.Arguments = $newArgs
                    $actionUpdated = $true
                }
            }
        }

        if ($actionUpdated) {
            Write-Host "[$TaskName] Added -WindowStyle Hidden to PowerShell command" -ForegroundColor Yellow
        }

        # Save to temp file
        $TempFile = [System.IO.Path]::GetTempFileName()
        $TaskXml.Save($TempFile)

        # Re-register task
        Write-Host "[$TaskName] Re-registering task with hidden settings..." -ForegroundColor Gray
        Register-ScheduledTask -TaskName $TaskName -Xml (Get-Content $TempFile -Raw) -Force | Out-Null

        # Clean up
        Remove-Item $TempFile -Force

        # Verify
        $UpdatedTask = Get-ScheduledTask -TaskName $TaskName

        Write-Host "[$TaskName] SUCCESS - Hidden: $($UpdatedTask.Settings.Hidden)" -ForegroundColor Green
        Write-Host ""

    } catch {
        Write-Host "[$TaskName] ERROR: $_" -ForegroundColor Red
        Write-Host ""
    }
}

Write-Host "Done! All AITrader tasks should now run without popups." -ForegroundColor Cyan
