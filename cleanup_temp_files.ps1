# Cleanup temporary files and test scripts
$ErrorActionPreference = "Continue"

Write-Host "Cleaning up temporary files..." -ForegroundColor Cyan
Write-Host ""

# Patterns to remove
$PatternsToRemove = @(
    "*.md",  # Temporary markdown docs (keep important ones)
    "*.ps1", # Temp PowerShell scripts (keep important ones)
    "*.cmd",
    "*.txt",
    "*.log",
    "*.xml",
    "*.json",
    "*.py",
    "tmpclaude-*"
)

# Files to preserve (important)
$Preserve = @(
    "README.md",
    "CLAUDE.md",
    "OPENAI_USAGE_AUDIT.md",
    "tools\windows\*.ps1",
    "list_tasks.ps1",
    "fix_selector_task_complete.ps1"
)

# Get all temp files
$TempFiles = Get-ChildItem -Path . -File | Where-Object {
    ($_.Name -match "^(test_|check_|enable_|verify_|restart_|diagnose_|force_|cancel_|close_|exit_|start_|update_|revert_|delete_|apply_|fix_|recreate_|replace_)") -or
    ($_.Name -match "\.xml$" -and $_.Name -like "*AITrader*") -or
    ($_.Name -match "^[A-Z_]+\.(md|txt|log)$") -or
    ($_.Name -like "*test*.json") -or
    ($_.Name -like "paper_test*") -or
    ($_.Name -like "logs*")
}

# Also get tmpclaude directories
$TempDirs = Get-ChildItem -Path . -Directory | Where-Object {
    $_.Name -like "tmpclaude-*"
}

Write-Host "Found temporary files to remove:" -ForegroundColor Yellow
$TempFiles | Select-Object Name | Format-Table -AutoSize

Write-Host ""
Write-Host "Found temporary directories to remove:" -ForegroundColor Yellow
$TempDirs | Select-Object Name | Format-Table -AutoSize

Write-Host ""
$Confirm = Read-Host "Remove these files? (y/n)"

if ($Confirm -eq "y") {
    $Count = 0

    foreach ($File in $TempFiles) {
        try {
            Remove-Item $File.FullName -Force
            $Count++
        } catch {
            Write-Host "  Failed to remove: $($File.Name)" -ForegroundColor Red
        }
    }

    foreach ($Dir in $TempDirs) {
        try {
            Remove-Item $Dir.FullName -Recurse -Force
            $Count++
        } catch {
            Write-Host "  Failed to remove: $($Dir.Name)" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "Removed $Count items" -ForegroundColor Green
} else {
    Write-Host "Cleanup cancelled" -ForegroundColor Yellow
}
