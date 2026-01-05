#!/bin/bash
# Quick check script to run on any Linux/Mac system to see if trading bot is running
# Usage: bash check_if_bot_running_here.sh

echo "==============================================================================="
echo "AI Trader Bot Detection Script"
echo "==============================================================================="
echo ""
echo "Hostname: $(hostname)"
echo "Current User: $(whoami)"
echo "Date: $(date)"
echo ""

found_something=false

# Check for Python processes
echo "[1/7] Checking for Python processes..."
python_procs=$(ps aux | grep -E "python|runner|trader|alpaca" | grep -v grep)
if [ -n "$python_procs" ]; then
    echo "  FOUND Python processes:"
    echo "$python_procs" | while read line; do echo "    $line"; done
    found_something=true
else
    echo "  OK - No Python processes found"
fi
echo ""

# Check for ai-trader directory
echo "[2/7] Searching for ai-trader directory..."
ai_trader_dirs=$(find /home /opt /var /root -name "ai-trader" -type d 2>/dev/null)
if [ -n "$ai_trader_dirs" ]; then
    echo "  FOUND ai-trader directory(ies):"
    echo "$ai_trader_dirs" | while read line; do echo "    $line"; done
    found_something=true
else
    echo "  OK - No ai-trader directory found"
fi
echo ""

# Check cron jobs
echo "[3/7] Checking cron jobs..."
user_cron=$(crontab -l 2>/dev/null | grep -E "trader|alpaca|runner")
root_cron=$(sudo crontab -l 2>/dev/null | grep -E "trader|alpaca|runner")

if [ -n "$user_cron" ]; then
    echo "  FOUND user cron jobs:"
    echo "$user_cron" | while read line; do echo "    $line"; done
    found_something=true
fi

if [ -n "$root_cron" ]; then
    echo "  FOUND root cron jobs:"
    echo "$root_cron" | while read line; do echo "    $line"; done
    found_something=true
fi

if [ -z "$user_cron" ] && [ -z "$root_cron" ]; then
    echo "  OK - No trading bot cron jobs found"
fi
echo ""

# Check systemd services
echo "[4/7] Checking systemd services..."
systemd_services=$(systemctl list-units --type=service --all | grep -E "trader|alpaca")
if [ -n "$systemd_services" ]; then
    echo "  FOUND systemd services:"
    echo "$systemd_services" | while read line; do echo "    $line"; done
    found_something=true
else
    echo "  OK - No trading bot systemd services"
fi
echo ""

# Check for .env files
echo "[5/7] Searching for .env files with ALPACA keys..."
env_files=$(find /home /opt -name ".env" 2>/dev/null | xargs grep -l "ALPACA" 2>/dev/null)
if [ -n "$env_files" ]; then
    echo "  FOUND .env files with ALPACA keys:"
    echo "$env_files" | while read line; do echo "    $line"; done
    found_something=true
else
    echo "  OK - No .env files with ALPACA keys"
fi
echo ""

# Check environment variables
echo "[6/7] Checking environment variables..."
env_vars=$(env | grep -i ALPACA)
if [ -n "$env_vars" ]; then
    echo "  FOUND ALPACA environment variables:"
    echo "$env_vars" | while read line; do
        # Mask the key value
        key=$(echo "$line" | cut -d= -f1)
        value=$(echo "$line" | cut -d= -f2)
        masked="${value:0:8}...${value: -4}"
        echo "    $key=$masked"
    done
    found_something=true
else
    echo "  OK - No ALPACA environment variables"
fi
echo ""

# Check Docker containers
echo "[7/7] Checking Docker containers..."
if command -v docker &> /dev/null; then
    docker_containers=$(docker ps -a --format "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}" 2>/dev/null)
    if [ -n "$docker_containers" ]; then
        echo "  Found Docker containers (check if any are related to trading):"
        echo "$docker_containers" | while read line; do echo "    $line"; done
        found_something=true
    else
        echo "  Docker installed but no containers running"
    fi
else
    echo "  Docker not installed"
fi
echo ""

echo "==============================================================================="
if [ "$found_something" = true ]; then
    echo "  ⚠️  FOUND POTENTIAL TRADING BOT INSTANCES"
    echo "==============================================================================="
    echo ""
    echo "Actions to take:"
    echo "  1. Review findings above"
    echo "  2. Check log files in ai-trader/logs directory"
    echo "  3. Stop processes: pkill -f 'python.*runner'"
    echo "  4. Disable cron: crontab -e (remove trader lines)"
    echo "  5. Stop systemd service: systemctl stop <service-name>"
else
    echo "  ✓ NO TRADING BOT FOUND ON THIS SYSTEM"
    echo "==============================================================================="
fi
echo ""
