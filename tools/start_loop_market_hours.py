#!/usr/bin/env python3
"""
Smart Loop Starter - Only runs during market hours on weekdays

This script checks if the market is open and only starts the trading loop
if it's a weekday during market hours (9:30 AM - 4:00 PM EST).

Safe to run repeatedly - will not start duplicate instances.

Usage:
    python tools/start_loop_market_hours.py

Schedule this script to run every 10-15 minutes during weekdays via:
- Windows Task Scheduler (recommended)
- Cron (Linux/Mac)

The script will:
1. Check if it's a weekday (Monday-Friday)
2. Check if current time is during market hours (9:30 AM - 4:00 PM EST)
3. Check if loop is already running
4. Start loop only if all conditions are met
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))


def get_eastern_time() -> datetime:
    """Get current time in US Eastern timezone."""
    return datetime.now(ZoneInfo("America/New_York"))


def is_weekday() -> bool:
    """Check if today is a weekday (Monday=0, Sunday=6)."""
    et_now = get_eastern_time()
    return et_now.weekday() < 5  # Monday-Friday


def is_market_hours() -> bool:
    """Check if current time is during market hours (9:30 AM - 4:00 PM ET)."""
    et_now = get_eastern_time()

    # Market hours: 9:30 AM - 4:00 PM ET
    market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = et_now.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= et_now <= market_close


def is_loop_running() -> bool:
    """Check if trading loop is already running."""
    lock_file = Path("logs/paper_dryrun.lock")

    # Check if lock file exists
    if not lock_file.exists():
        return False

    # Try to read PID from lock file
    try:
        with open(lock_file, 'r') as f:
            content = f.read().strip()
            if not content:
                return False

            # Extract PID (format: "PID: 12345")
            pid = int(content.split()[-1])

            # Check if process is still running
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return True
            except OSError:
                # Process not running, clean up stale lock
                print(f"Removing stale lock file (PID {pid} not running)")
                lock_file.unlink()
                return False
    except PermissionError:
        # Lock file is being held by another process - loop is running
        print("Lock file is held by running process")
        return True
    except (ValueError, IndexError, FileNotFoundError):
        # Invalid lock file format, remove it
        print("Removing invalid lock file")
        try:
            lock_file.unlink()
        except:
            pass
        return False


def start_loop() -> bool:
    """Start the trading loop in background."""
    log_dir = Path("logs/loop")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"loop_{get_eastern_time().strftime('%Y%m%d')}.log"

    # Start loop process with proper environment
    cmd = [
        sys.executable,  # Use same Python interpreter
        "-m", "src.app.runner",
        "--mode", "paper",
        "--loop",
        "--sleep-seconds", "600"
    ]

    # Set up environment
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)

    try:
        # Start process in background
        process = subprocess.Popen(
            cmd,
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            cwd=project_root,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )

        print(f"Started trading loop with PID: {process.pid}")
        print(f"Logging to: {log_file}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to start loop: {e}")
        return False


def main():
    """Main entry point."""
    et_now = get_eastern_time()

    print("=" * 60)
    print("AI Trader - Smart Loop Starter")
    print("=" * 60)
    print(f"Current time: {et_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()

    # Check weekday
    if not is_weekday():
        day_name = et_now.strftime('%A')
        print(f"[X] Not a weekday (today is {day_name})")
        print("Loop will not start on weekends")
        return

    print("[OK] Weekday check passed")

    # Check market hours
    if not is_market_hours():
        print(f"[X] Outside market hours (9:30 AM - 4:00 PM ET)")
        print(f"Current time: {et_now.strftime('%H:%M:%S ET')}")
        print("Loop will not start outside market hours")
        return

    print("[OK] Market hours check passed")

    # Check if already running
    if is_loop_running():
        print("[OK] Loop is already running")
        print("No action needed")
        return

    print("[!] Loop is not running")

    # Start the loop
    print()
    print("Starting trading loop...")
    if start_loop():
        print("[OK] Loop started successfully!")
    else:
        print("[ERROR] Failed to start loop")
        sys.exit(1)


if __name__ == "__main__":
    main()
