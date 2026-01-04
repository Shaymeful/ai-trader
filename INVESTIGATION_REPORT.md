# Trading Bot Investigation Report - Jan 2, 2026

## Mystery Orders Timeline

### Orders Found:
1. **4:00 AM EST** - Multiple orders placed (per screenshot)
2. **9:23 AM EST** - Multiple orders placed (per screenshot)
3. **1:06 PM EST** - 12 orders placed (known test run on this PC)

---

## Local Machine Investigation Results

### ✅ Confirmed: This PC Did NOT Place the 4:00 AM or 9:23 AM Orders

**Evidence:**
1. **No log files exist** from those times:
   - No `paper_run_*.jsonl` files for 4:00 AM or 9:23 AM
   - Only logs from 1:03 PM and 1:06 PM exist for Jan 2

2. **Scheduled task analysis:**
   ```
   Task Name: AI-Trader-Hourly
   Command: python.exe -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run
   Trigger: At logon time
   Last Run: Jan 1, 2026 3:41:32 PM
   Status: Has --dry-run flag (safe, won't place orders)
   ```
   - Task has `--dry-run` flag (wouldn't place orders anyway)
   - Task only triggers at login, not at 4:00 AM or 9:23 AM
   - Last ran on Jan 1, not Jan 2

3. **No Python processes running** currently

4. **loop_status.log** has no entries for Jan 2 (only Jan 1 entries)

5. **User confirmed PC was powered off** at those times

---

## ⚠️ CONCLUSION: Orders Were Placed From Another System

Since your Windows PC was powered off and has no logs from those times, the trading bot **MUST** be running on another system you have access to.

---

## Likely Sources (In Order of Probability)

### 1. Another Laptop/PC You Own
**Action:** Check each computer/laptop you have
- Look for cloned `ai-trader` repository
- Check for scheduled tasks/cron jobs
- Search for `.env` files with Alpaca keys

**Commands to run on each machine:**
```powershell
# Windows
Get-ScheduledTask | Where-Object {$_.TaskName -like "*trader*"}
Get-Process python* | Select-Object Id, ProcessName, StartTime
dir C:\dev\ai-trader\.env

# Mac/Linux
crontab -l | grep trader
ps aux | grep python
find ~ -name "ai-trader" 2>/dev/null
```

---

### 2. Cloud Server (AWS/Azure/GCP/DigitalOcean/etc.)
**Action:** Check each cloud provider you have accounts with

**AWS:**
```bash
# List EC2 instances
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress]' --output table

# SSH into each instance and check
ssh -i ~/.ssh/your-key.pem ubuntu@<IP_ADDRESS>
ps aux | grep python
crontab -l
find /home -name "ai-trader" 2>/dev/null
```

**Azure:**
```bash
az vm list --query "[].{Name:name, PowerState:powerState}" --output table
```

**GCP:**
```bash
gcloud compute instances list
```

**DigitalOcean:**
```bash
doctl compute droplet list
```

---

### 3. VPS / Hosting Service
Check if you have accounts with:
- Linode
- Vultr
- Hetzner
- OVH
- Any other VPS provider

---

### 4. Docker Container (On Another Machine)
**Action:** Check if Docker is running on any of your systems
```bash
docker ps -a
docker logs <container_id>
```

---

### 5. WSL on Another Windows Machine
**Action:** If you have other Windows PCs, check WSL
```bash
wsl --list --running
wsl -d Ubuntu  # or your distro name
ps aux | grep python
crontab -l
```

---

### 6. Raspberry Pi / Home Server
**Action:** Check any Raspberry Pi or home server you might have running

---

### 7. Friend/Colleague's System
**Action:** Did you share your API keys or repo with anyone?

---

## 🔍 How to Systematically Find the Source

### Step 1: Check Your Email for Cloud Service Confirmations
Search your email for:
- "instance launched"
- "server created"
- "droplet created"
- "EC2"
- "compute engine"
- Keywords: AWS, Azure, GCP, DigitalOcean, Linode, Vultr

### Step 2: Check Cloud Provider Dashboards
Log into each cloud provider and look for:
- Running instances/VMs
- Recent activity logs
- Billing for compute resources

### Step 3: Check GitHub Actions (Unlikely but possible)
- Go to: https://github.com/Shaymeful/ai-trader/actions
- Look for any running workflows
- Check for scheduled workflows

**Note:** Current `.github/workflows/tests.yml` only runs tests, not trading

### Step 4: Check SSH Known Hosts
```bash
cat ~/.ssh/known_hosts
```
This will show IPs/hostnames you've connected to recently

### Step 5: Check PowerShell/Bash History on All Machines
```powershell
# Windows
Get-Content (Get-PSReadlineOption).HistorySavePath | Select-String "ssh|scp|aws|azure|gcloud|docker"
```

```bash
# Mac/Linux
cat ~/.bash_history | grep -E "ssh|scp|aws|azure|gcloud|docker"
cat ~/.zsh_history | grep -E "ssh|scp|aws|azure|gcloud|docker"
```

---

## 🚨 If You Can't Find the Source

### Immediate Actions:

1. **Rotate your Alpaca API keys NOW**
   - Log into https://app.alpaca.markets/paper/dashboard/api-keys
   - Delete current API keys
   - Generate new ones
   - Update your local `.env` file

2. **Check Alpaca Account Activity**
   - Review all orders: https://app.alpaca.markets/paper/dashboard/orders
   - Check account balance history
   - Look for unexpected trades

3. **Enable Alpaca Email Notifications**
   - Settings > Notifications
   - Enable alerts for: Orders placed, Orders filled, Position changes

4. **Check for Compromised Keys**
   - Search GitHub for your API keys (they might have been committed accidentally)
   - Go to: https://github.com/search?q=%22your-key-here%22&type=code

5. **Review Git Commit History for Leaked Keys**
   ```bash
   git log --all --full-history -S "ALPACA_PAPER_KEY_ID" --source --all
   git log --all --full-history -S "ALPACA_" --source --all
   ```

---

## 📋 Comprehensive Checklist

Use this to systematically check every possibility:

- [ ] Check all other laptops/PCs you own
- [ ] Check AWS EC2 instances
- [ ] Check Azure VMs
- [ ] Check GCP Compute instances
- [ ] Check DigitalOcean droplets
- [ ] Check Linode instances
- [ ] Check Vultr instances
- [ ] Check Raspberry Pi or home servers
- [ ] Check Docker containers on all machines
- [ ] Check WSL on other Windows PCs
- [ ] Check GitHub Actions workflows
- [ ] Check with anyone you shared keys/repo with
- [ ] Search email for cloud service notifications
- [ ] Check SSH known_hosts for unfamiliar IPs
- [ ] Review bash/PowerShell history for remote connections
- [ ] Check git history for accidentally committed keys
- [ ] Search GitHub for leaked keys
- [ ] Check Alpaca dashboard for unrecognized activity
- [ ] Rotate API keys if you can't find source

---

## 🔧 Quick Commands to Run Now

### Check All Possible Scheduled Tasks
```powershell
# On this PC (already done)
Get-ScheduledTask | Select-Object TaskName, State, LastRunTime, NextRunTime | Out-GridView
```

### Check Alpaca Order History for Exact Times
```powershell
cd C:\dev\ai-trader
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders | Out-File -FilePath orders_full.txt
```

Then search `orders_full.txt` for the exact timestamps from your screenshots.

### Search for All .env Files on This PC
```powershell
Get-ChildItem -Path C:\ -Recurse -Filter ".env" -ErrorAction SilentlyContinue | Select-Object FullName, LastWriteTime
```

---

## 🎯 Most Likely Scenario

Based on the timing (4:00 AM and 9:23 AM):
- **4:00 AM** - Suggests a scheduled cron job (common times: midnight, 4 AM, 8 AM, etc.)
- **9:23 AM** - More unusual time, might be manual or offset schedule

**Best Guess:** You have a cloud server or another PC with a cron job or scheduled task that runs at these times.

**What to look for:**
- Cron entry like: `0 4,9 * * * cd /home/user/ai-trader && python3 -m src.app.runner --mode paper`
- Windows task scheduled for 4:00 AM and 9:23 AM
- Docker container with restart policy and cron inside

---

## 📞 Next Steps

1. **Immediately:** Use the checklist above to systematically check each possibility
2. **Document:** As you check each item, write down what you find
3. **If found:** Document the location and decide whether to keep or terminate it
4. **If not found within 1 hour:** Rotate your API keys as a safety precaution
5. **Going forward:** Use the audit scripts created:
   - `tools/quick_audit.cmd` - Run on any Windows machine
   - `docs/AUDIT_CHECKLIST.md` - Full investigation guide

---

## 🛡️ Prevention Going Forward

1. **Keep an inventory** of where the repo is cloned
2. **Use different API keys** for different environments (dev vs. production)
3. **Set up alerts** on Alpaca for all order activity
4. **Add logging** that includes hostname/IP in each run
5. **Create a deployment log** whenever you set up automation somewhere
6. **Never commit `.env`** to git (already in `.gitignore`, good!)
7. **Use a password manager** to track where keys are deployed

---

## 📁 Reference Files Created

- `docs/AUDIT_CHECKLIST.md` - Comprehensive audit guide
- `tools/audit_running_instances.ps1` - Local machine audit script
- `tools/quick_audit.cmd` - Quick Windows audit
- This file: `INVESTIGATION_REPORT.md`

---

## ❓ Questions to Ask Yourself

1. Did I ever SSH into a cloud server and clone this repo?
2. Did I ever set up a "set it and forget it" trading bot?
3. Do I have an old laptop that's still running?
4. Did I give API keys to anyone (friend, colleague, freelancer)?
5. Have I ever committed `.env` to git by mistake?
6. Do I have any VPS or cloud services I pay for monthly that I forgot about?
7. Did I ever test this on a friend's computer?

---

**Report Generated:** 2026-01-02
**Author:** Claude Code Investigation
**Status:** 🔴 ACTIVE INVESTIGATION - Orders placed from unknown source
