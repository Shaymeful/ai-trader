# Force kill all Python processes and clear locks
Write-Host "Killing all Python processes..."
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Force remove lock files
Write-Host "Removing lock files..."
Get-ChildItem -Path logs -Filter "*.lock" | ForEach-Object {
    try {
        Remove-Item $_.FullName -Force -ErrorAction Stop
        Write-Host "Removed: $($_.Name)"
    } catch {
        Write-Host "Failed to remove: $($_.Name) - $($_.Exception.Message)"
    }
}

Write-Host "Done. You can now start the loop."
