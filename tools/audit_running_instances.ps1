# AI Trader Instance Audit Script
# Automatically checks for running instances on current Windows machine

Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host "  AI Trader Instance Audit - Local Machine" -ForegroundColor Cyan
Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host ""

$foundIssues = $false

# 1. Check for running Python processes
Write-Host "[1/7] Checking for running Python processes..." -ForegroundColor Yellow
$pythonProcs = Get-Process python* -ErrorAction SilentlyContinue
if ($pythonProcs) {
    Write-Host "  Found $($pythonProcs.Count) Python process(es):" -ForegroundColor Red
    $foundIssues = $true

    foreach ($proc in $pythonProcs) {
        $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
        Write-Host "    PID $($proc.Id): $cmdLine" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✓ No Python processes running" -ForegroundColor Green
}
Write-Host ""

# 2. Check Task Scheduler
Write-Host "[2/7] Checking Windows Task Scheduler..." -ForegroundColor Yellow
$tasks = Get-ScheduledTask | Where-Object {
    $_.TaskName -like "*trader*" -or
    $_.TaskName -like "*alpaca*" -or
    $_.TaskName -like "*AI-*"
}

if ($tasks) {
    Write-Host "  Found $($tasks.Count) scheduled task(s):" -ForegroundColor Red
    $foundIssues = $true

    foreach ($task in $tasks) {
        $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -ErrorAction SilentlyContinue
        Write-Host "    Task: $($task.TaskName)" -ForegroundColor Yellow
        Write-Host "      State: $($task.State)" -ForegroundColor Yellow
        Write-Host "      Last Run: $($info.LastRunTime)" -ForegroundColor Yellow
        Write-Host "      Next Run: $($info.NextRunTime)" -ForegroundColor Yellow
        Write-Host "      Last Result: $($info.LastTaskResult)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✓ No trader-related scheduled tasks found" -ForegroundColor Green
}
Write-Host ""

# 3. Check Startup Programs
Write-Host "[3/7] Checking Startup programs..." -ForegroundColor Yellow
$startupReg = @()
$startupReg += Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue
$startupReg += Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue

$startupFiles = @()
$startupFiles += Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" -ErrorAction SilentlyContinue
$startupFiles += Get-ChildItem "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup" -ErrorAction SilentlyContinue

$foundStartup = $false
foreach ($item in $startupReg) {
    $item.PSObject.Properties | Where-Object {$_.Value -like "*trader*" -or $_.Value -like "*alpaca*"} | ForEach-Object {
        Write-Host "  Registry: $($_.Name) = $($_.Value)" -ForegroundColor Yellow
        $foundStartup = $true
        $foundIssues = $true
    }
}

foreach ($file in $startupFiles) {
    if ($file.Name -like "*trader*" -or $file.Name -like "*alpaca*") {
        Write-Host "  Startup File: $($file.FullName)" -ForegroundColor Yellow
        $foundStartup = $true
        $foundIssues = $true
    }
}

if (-not $foundStartup) {
    Write-Host "  ✓ No trader-related startup programs found" -ForegroundColor Green
}
Write-Host ""

# 4. Check for .env files with API keys
Write-Host "[4/7] Searching for .env files with API keys..." -ForegroundColor Yellow
$envFiles = Get-ChildItem -Path C:\dev -Recurse -Filter ".env" -ErrorAction SilentlyContinue |
    Where-Object {$_.FullName -notlike "*node_modules*" -and $_.FullName -notlike "*\.git\*"}

if ($envFiles) {
    Write-Host "  Found $($envFiles.Count) .env file(s):" -ForegroundColor Yellow

    foreach ($file in $envFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if ($content -match "ALPACA") {
            Write-Host "    $($file.FullName)" -ForegroundColor Red
            $foundIssues = $true

            # Show API key status (masked)
            $lines = $content -split "`n"
            foreach ($line in $lines) {
                if ($line -match "ALPACA.*=(.+)") {
                    $key = $matches[1].Trim()
                    if ($key) {
                        $masked = $key.Substring(0, [Math]::Min(8, $key.Length)) + "..." +
                                  $key.Substring([Math]::Max(0, $key.Length - 4))
                        Write-Host "      $($line.Split('=')[0]) = $masked" -ForegroundColor Yellow
                    }
                }
            }
        }
    }
} else {
    Write-Host "  No .env files found in C:\dev" -ForegroundColor Green
}
Write-Host ""

# 5. Check environment variables
Write-Host "[5/7] Checking environment variables for API keys..." -ForegroundColor Yellow
$envVars = Get-ChildItem Env: | Where-Object {$_.Name -like "*ALPACA*"}

if ($envVars) {
    Write-Host "  Found ALPACA environment variable(s):" -ForegroundColor Red
    $foundIssues = $true

    foreach ($var in $envVars) {
        $masked = $var.Value.Substring(0, [Math]::Min(8, $var.Value.Length)) + "..." +
                  $var.Value.Substring([Math]::Max(0, $var.Value.Length - 4))
        Write-Host "    $($var.Name) = $masked" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✓ No ALPACA environment variables in current session" -ForegroundColor Green
}
Write-Host ""

# 6. Check Docker containers
Write-Host "[6/7] Checking Docker containers..." -ForegroundColor Yellow
try {
    $dockerInstalled = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerInstalled) {
        $containers = docker ps --format "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}" 2>$null

        if ($LASTEXITCODE -eq 0 -and $containers) {
            Write-Host "  Found $($containers.Count) running container(s):" -ForegroundColor Yellow
            $foundIssues = $true

            foreach ($line in $containers) {
                Write-Host "    $line" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  ✓ No running Docker containers (or Docker not running)" -ForegroundColor Green
        }
    } else {
        Write-Host "  Docker not installed" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Could not check Docker: $_" -ForegroundColor Gray
}
Write-Host ""

# 7. Check WSL instances
Write-Host "[7/7] Checking WSL instances..." -ForegroundColor Yellow
try {
    $wslInstalled = Get-Command wsl -ErrorAction SilentlyContinue
    if ($wslInstalled) {
        $wslList = wsl --list --running 2>$null

        if ($LASTEXITCODE -eq 0 -and $wslList -and $wslList.Count -gt 1) {
            Write-Host "  Found running WSL instance(s):" -ForegroundColor Yellow
            $foundIssues = $true

            foreach ($line in $wslList) {
                if ($line.Trim()) {
                    Write-Host "    $line" -ForegroundColor Yellow
                }
            }

            Write-Host "  Run these commands in each WSL instance:" -ForegroundColor Cyan
            Write-Host "    wsl -d [distro-name]" -ForegroundColor Cyan
            Write-Host "    ps aux | grep python" -ForegroundColor Cyan
            Write-Host "    crontab -l" -ForegroundColor Cyan
            Write-Host "    pkill -f python" -ForegroundColor Cyan
        } else {
            Write-Host "  ✓ No running WSL instances" -ForegroundColor Green
        }
    } else {
        Write-Host "  WSL not installed" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Could not check WSL: $_" -ForegroundColor Gray
}
Write-Host ""

# Summary
Write-Host "=================================================================================" -ForegroundColor Cyan
if ($foundIssues) {
    Write-Host "  ⚠ FOUND POTENTIAL RUNNING INSTANCES" -ForegroundColor Red
    Write-Host "=================================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Actions to take:" -ForegroundColor Yellow
    Write-Host "  1. Review findings above" -ForegroundColor Yellow
    Write-Host "  2. Kill processes: Get-Process python* | Stop-Process -Force" -ForegroundColor Yellow
    Write-Host "  3. Disable tasks: Disable-ScheduledTask -TaskName 'AI-Trader-Paper-Hourly'" -ForegroundColor Yellow
    Write-Host "  4. Check Alpaca dashboard for recent order activity" -ForegroundColor Yellow
    Write-Host "  5. See docs/AUDIT_CHECKLIST.md for comprehensive audit" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ NO RUNNING INSTANCES FOUND ON LOCAL MACHINE" -ForegroundColor Green
    Write-Host "=================================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "If trades occurred while this PC was off, check:" -ForegroundColor Yellow
    Write-Host "  - Other computers/laptops" -ForegroundColor Yellow
    Write-Host "  - Cloud servers (AWS / Azure / GCP / etc.)" -ForegroundColor Yellow
    Write-Host "  - GitHub Actions workflows" -ForegroundColor Yellow
    Write-Host "  - Docker containers on other machines" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "See docs/AUDIT_CHECKLIST.md for full investigation guide" -ForegroundColor Cyan
}
Write-Host ""
