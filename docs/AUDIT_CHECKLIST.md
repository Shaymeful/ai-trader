# Trading Bot Execution Environment Audit Checklist

## Overview
Use this checklist to systematically locate and audit all environments where your AI trader might be running with your Alpaca API keys.

---

## 1. Local Windows Machine (Current PC)

### Check Running Processes
```powershell
# Find any running Python processes with "trader" or "alpaca" in command line
Get-Process python* | ForEach-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    if ($cmdLine -match "trader|alpaca|runner") {
        [PSCustomObject]@{
            PID = $_.Id
            Name = $_.Name
            CommandLine = $cmdLine
        }
    }
}

# Check all Python processes (might be running from different directory)
Get-WmiObject Win32_Process | Where-Object {$_.Name -like "*python*"} | Select-Object ProcessId, CommandLine

# Kill specific process if found
taskkill /PID <PID> /F
```

### Check Windows Task Scheduler
```powershell
# List all tasks with "trader" or "alpaca" in name
Get-ScheduledTask | Where-Object {$_.TaskName -like "*trader*" -or $_.TaskName -like "*alpaca*"} | Format-List *

# List ALL tasks (to catch tasks with different names)
Get-ScheduledTask | Select-Object TaskName, State, @{Name='NextRun';Expression={(Get-ScheduledTaskInfo -TaskName $_.TaskName).NextRunTime}}

# View specific task details
Get-ScheduledTask -TaskName "AI-Trader-Paper-Hourly" | Format-List *
(Get-ScheduledTask -TaskName "AI-Trader-Paper-Hourly").Actions
(Get-ScheduledTask -TaskName "AI-Trader-Paper-Hourly").Triggers

# Check last run time and result
Get-ScheduledTaskInfo -TaskName "AI-Trader-Paper-Hourly"

# Disable task (keeps it but stops execution)
Disable-ScheduledTask -TaskName "AI-Trader-Paper-Hourly"

# Remove task completely
Unregister-ScheduledTask -TaskName "AI-Trader-Paper-Hourly" -Confirm:$false

# Search ALL tasks for Alpaca API keys or repo paths
Get-ScheduledTask | ForEach-Object {
    $actions = $_.Actions | Select-Object -ExpandProperty Execute, Arguments -ErrorAction SilentlyContinue
    if ($actions -match "alpaca|ai-trader|ALPACA_") {
        [PSCustomObject]@{
            TaskName = $_.TaskName
            State = $_.State
            Actions = $actions
        }
    }
}
```

### Check Startup Programs
```powershell
# Check Registry startup locations
Get-ItemProperty HKCU:\Software\Microsoft\Windows\CurrentVersion\Run
Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Run

# Check Startup folder
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
Get-ChildItem "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
```

### Check Windows Services
```powershell
# List services with "trader" or "alpaca" in name
Get-Service | Where-Object {$_.DisplayName -like "*trader*" -or $_.DisplayName -like "*alpaca*"}

# Check all services (detailed)
Get-WmiObject Win32_Service | Where-Object {$_.PathName -like "*python*" -or $_.PathName -like "*trader*"} | Select-Object Name, State, PathName
```

### Search for API Keys in Environment
```powershell
# Check current session environment variables
Get-ChildItem Env: | Where-Object {$_.Name -like "*ALPACA*"}

# Check user environment variables (persisted)
[System.Environment]::GetEnvironmentVariables("User") | Where-Object {$_.Keys -like "*ALPACA*"}

# Check system-wide environment variables
[System.Environment]::GetEnvironmentVariables("Machine") | Where-Object {$_.Keys -like "*ALPACA*"}

# Search for .env files in common locations
Get-ChildItem -Path C:\Users\$env:USERNAME -Recurse -Filter ".env" -ErrorAction SilentlyContinue | Select-Object FullName
Get-ChildItem -Path C:\dev -Recurse -Filter ".env" -ErrorAction SilentlyContinue | Select-Object FullName
Get-ChildItem -Path C:\projects -Recurse -Filter ".env" -ErrorAction SilentlyContinue | Select-Object FullName

# Search inside .env files for ALPACA keys
Get-ChildItem -Path C:\dev -Recurse -Filter ".env" -ErrorAction SilentlyContinue | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match "ALPACA") {
        Write-Host "`nFound in: $($_.FullName)"
        Get-Content $_.FullName | Select-String "ALPACA"
    }
}
```

### Check PowerShell History
```powershell
# View PowerShell command history
Get-Content (Get-PSReadlineOption).HistorySavePath | Select-String "alpaca|trader|python.*runner"

# Search for API key usage in history
Get-Content (Get-PSReadlineOption).HistorySavePath | Select-String "ALPACA_"
```

---

## 2. WSL (Windows Subsystem for Linux)

### Check if WSL is installed and running
```powershell
# List WSL distributions
wsl --list --verbose

# Check running WSL instances
Get-Process -Name "wsl*", "wslhost*"
```

### Inside each WSL distribution
```bash
# Enter WSL
wsl -d Ubuntu  # or your distro name

# Check for running Python processes
ps aux | grep -E "python|trader|alpaca"

# Check cron jobs
crontab -l
sudo crontab -l  # root crontab

# Check system-wide cron
cat /etc/crontab
ls -la /etc/cron.d/
ls -la /etc/cron.hourly/
ls -la /etc/cron.daily/

# Check systemd services (if WSL2 with systemd)
systemctl list-units --type=service | grep -E "trader|alpaca"

# Check tmux/screen sessions
tmux list-sessions
screen -ls

# Search for .env files
find /home/$USER -name ".env" 2>/dev/null
find /mnt/c/Users -name ".env" 2>/dev/null

# Search for API keys in environment
env | grep ALPACA
cat ~/.bashrc | grep ALPACA
cat ~/.bash_profile | grep ALPACA
cat ~/.profile | grep ALPACA
cat ~/.zshrc | grep ALPACA 2>/dev/null

# Check bash history
cat ~/.bash_history | grep -E "python.*runner|alpaca|trader"

# Find all copies of the repo
find / -type d -name "ai-trader" 2>/dev/null

# Kill processes
pkill -f "python.*runner"
```

---

## 3. Docker Containers

### On Windows
```powershell
# Check if Docker is running
Get-Process *docker* | Select-Object Name, Id

# List running containers
docker ps -a

# Search for containers with your code
docker ps -a | Select-String "trader|alpaca"

# Inspect container for environment variables
docker inspect <container_id> | Select-String "ALPACA"

# Check container logs
docker logs <container_id>

# Stop and remove containers
docker stop <container_id>
docker rm <container_id>

# List Docker images
docker images | Select-String "trader|alpaca"

# Remove images
docker rmi <image_id>

# Check docker-compose projects
Get-ChildItem -Path C:\dev -Recurse -Filter "docker-compose.yml" -ErrorAction SilentlyContinue

# Search docker-compose files for ALPACA keys
Get-ChildItem -Path C:\dev -Recurse -Filter "docker-compose*.yml" -ErrorAction SilentlyContinue | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match "ALPACA") {
        Write-Host "`nFound in: $($_.FullName)"
        Get-Content $_.FullName | Select-String "ALPACA"
    }
}
```

### Inside WSL Docker
```bash
# Same commands as above in WSL
docker ps -a
docker inspect <container_id> | grep ALPACA
docker logs <container_id>
docker stop $(docker ps -aq)  # Stop all containers
```

---

## 4. Cloud Servers (AWS, Azure, GCP, DigitalOcean, etc.)

### For each cloud provider, check:

#### AWS EC2 Instances
```bash
# List running EC2 instances (requires AWS CLI)
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --query 'Reservations[*].Instances[*].[InstanceId,PublicIpAddress,Tags[?Key==`Name`].Value|[0]]' --output table

# SSH into each instance
ssh -i ~/.ssh/your-key.pem ubuntu@<IP_ADDRESS>

# Then check processes, cron, etc. (see Linux section below)
```

#### Azure VMs
```bash
# List running VMs (requires Azure CLI)
az vm list --query "[?powerState=='VM running'].{Name:name, ResourceGroup:resourceGroup}" --output table

# SSH into VM
ssh azureuser@<IP_ADDRESS>
```

#### GCP Compute Instances
```bash
# List running instances (requires gcloud CLI)
gcloud compute instances list --filter="status=RUNNING"

# SSH into instance
gcloud compute ssh <instance-name>
```

#### DigitalOcean Droplets
```bash
# List droplets (requires doctl CLI)
doctl compute droplet list

# SSH into droplet
ssh root@<IP_ADDRESS>
```

### On each cloud server:
```bash
# Check running Python processes
ps aux | grep -E "python|trader"
pgrep -af python

# Check cron jobs (both user and root)
crontab -l
sudo crontab -l
cat /etc/crontab
ls -la /etc/cron.d/

# Check systemd services
systemctl list-units --type=service --state=running | grep -E "trader|alpaca"
systemctl list-timers --all

# Check tmux/screen sessions
tmux list-sessions
screen -ls

# Find the repo
find /home -type d -name "ai-trader" 2>/dev/null
find /opt -type d -name "ai-trader" 2>/dev/null
find /var -type d -name "ai-trader" 2>/dev/null

# Check environment variables
env | grep ALPACA
cat /etc/environment | grep ALPACA

# Check .env files
find /home -name ".env" 2>/dev/null
find /opt -name ".env" 2>/dev/null

# Stop trading bot
pkill -f "python.*runner"
systemctl stop ai-trader 2>/dev/null
```

---

## 5. GitHub Actions / CI/CD Runners

### Check GitHub Actions
```bash
# Via GitHub web interface:
# Go to: https://github.com/<username>/ai-trader/actions
# Look for: Running workflows, scheduled workflows

# Check workflow files in repo
ls -la .github/workflows/
cat .github/workflows/*.yml | grep -E "schedule|cron|ALPACA"

# Check repository secrets
# Go to: https://github.com/<username>/ai-trader/settings/secrets/actions
# Look for: ALPACA_PAPER_KEY_ID, ALPACA_LIVE_KEY_ID
```

### Check Other CI/CD Services
- **GitLab CI**: Check `.gitlab-ci.yml` and project CI/CD schedules
- **CircleCI**: Check `.circleci/config.yml` and scheduled workflows
- **Jenkins**: Check job configurations and scheduled builds
- **Travis CI**: Check `.travis.yml` and cron jobs

---

## 6. Other Laptops / PCs

### For each Windows machine:
```powershell
# Remote into other PCs via PowerShell remoting
Enter-PSSession -ComputerName <computer-name>

# Then run all Windows checks from Section 1
```

### For each Linux/Mac machine:
```bash
# SSH into machine
ssh user@<hostname-or-ip>

# Run all Linux checks (see Section 2 and Section 4)
```

---

## 7. Raspberry Pi / Home Server

```bash
# SSH into device
ssh pi@<IP_ADDRESS>

# Check all processes
ps aux | grep python

# Check cron
crontab -l
sudo crontab -l

# Check systemd services
systemctl list-units --type=service | grep trader

# Find repo
find /home -name "ai-trader" 2>/dev/null

# Kill processes
pkill -f "python.*runner"
```

---

## 8. Virtual Machines (VirtualBox, VMware, Hyper-V)

### Check Hyper-V VMs (Windows)
```powershell
# List running VMs
Get-VM | Where-Object {$_.State -eq 'Running'}

# Connect to VM
vmconnect localhost <VM-Name>

# Then check inside VM as normal
```

### Check VirtualBox VMs
```powershell
# List running VMs
VBoxManage list runningvms

# Access VM console or SSH into it
```

---

## 9. Cloud Notebooks / IDEs

### Check these services:
- **Google Colab**: https://colab.research.google.com - Check running notebooks
- **Kaggle Kernels**: https://www.kaggle.com/code - Check running kernels
- **AWS SageMaker**: Check running notebook instances
- **Azure Notebooks**: Check running notebooks
- **Replit**: https://replit.com - Check running repls
- **GitPod**: https://gitpod.io/workspaces - Check active workspaces
- **Codespaces**: https://github.com/codespaces - Check active codespaces

---

## 10. Mobile Devices (Rare but possible)

### Android (Termux)
```bash
# If you installed Termux and Python
ps aux | grep python
crontab -l
```

### iOS (Pythonista, a-Shell)
- Check running scripts in apps

---

## 11. Git Repository Audit

### Search all branches and commits for API keys
```bash
# Clone fresh copy of repo
git clone <repo-url> temp-audit
cd temp-audit

# Search all branches for .env files
git log --all --full-history -- "*.env"

# Search all commits for ALPACA keys (even deleted files)
git log --all --full-history -S "ALPACA_PAPER_KEY_ID" --source --all

# Search for API keys in all commits
git grep -i "ALPACA" $(git rev-list --all)

# Check if keys were ever committed
git log -p -S "ALPACA_" --all

# If keys found in history, consider rotating them
```

---

## 12. API Key Rotation (If you find unauthorized usage)

### Immediate Actions
```bash
# 1. Log into Alpaca Dashboard
# URL: https://app.alpaca.markets/paper/dashboard/overview (Paper)
# URL: https://app.alpaca.markets/live/dashboard/overview (Live)

# 2. Go to API Keys section
# Paper: https://app.alpaca.markets/paper/dashboard/api-keys
# Live: https://app.alpaca.markets/live/dashboard/api-keys

# 3. Delete old API keys
# 4. Generate new API keys
# 5. Update .env file in your repo
# 6. DO NOT commit .env to git

# 7. Check order history for unexpected trades
# Use tools/alpaca.ps1 to review orders:
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders -Mode paper
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders -Mode live
```

---

## Quick Nuclear Option (Stop Everything)

### Windows
```powershell
# Kill ALL Python processes
Get-Process python* | Stop-Process -Force

# Disable ALL scheduled tasks with "trader" in name
Get-ScheduledTask | Where-Object {$_.TaskName -like "*trader*"} | Disable-ScheduledTask

# Stop Docker containers
docker stop $(docker ps -aq)
```

### Linux/WSL/Mac
```bash
# Kill all Python processes
pkill -9 python
pkill -9 python3

# Stop all cron jobs temporarily
sudo systemctl stop cron  # Linux
sudo launchctl stop com.vixie.cron  # Mac

# Stop all tmux sessions
tmux kill-server

# Stop all screen sessions
screen -wipe
pkill screen
```

---

## Checklist Summary

- [ ] Check current Windows PC processes and Task Scheduler
- [ ] Check WSL distributions and cron jobs
- [ ] Check Docker containers (both Windows and WSL)
- [ ] Check all cloud server instances (AWS, Azure, GCP, etc.)
- [ ] Check GitHub Actions and other CI/CD workflows
- [ ] Check other laptops/PCs you own
- [ ] Check Raspberry Pi or home servers
- [ ] Check virtual machines (Hyper-V, VirtualBox, VMware)
- [ ] Check cloud notebooks (Colab, Kaggle, etc.)
- [ ] Search git history for accidentally committed keys
- [ ] Check Alpaca dashboard for recent activity
- [ ] Rotate API keys if any unexpected activity found
- [ ] Update .env files with new keys
- [ ] Verify .env is in .gitignore

---

## Monitoring Going Forward

### Set up alerts for unexpected trading:
```python
# Add to your runner.py or create monitoring script
def check_unexpected_orders():
    """Alert if orders appear that weren't placed by current session"""
    broker = AlpacaBroker(is_live=False)  # Paper trading
    orders = broker.list_open_orders_detailed()

    # Check for orders placed in last hour
    recent_orders = [o for o in orders if was_placed_recently(o)]

    if recent_orders and not is_current_session():
        send_alert(f"Found {len(recent_orders)} orders from unknown source!")
```

### Enable Alpaca email notifications:
- Go to Alpaca Dashboard > Settings > Notifications
- Enable email alerts for: Orders filled, Orders placed, Orders rejected

---

## Emergency Contact

If you find truly unauthorized access (not just forgotten environments):
1. **Immediately** delete API keys in Alpaca dashboard
2. Change Alpaca account password
3. Enable 2FA if not already enabled
4. Review all account activity
5. Contact Alpaca support if needed: support@alpaca.markets
