#!/usr/bin/env python3
"""Check if live paper trading mode is active."""
import re

# Read today's log
with open(r'logs\loop\loop_20260108.log', 'r', encoding='utf-16-le') as f:
    content = f.read()

# Find last iteration
iterations = re.findall(r'\[2026-01-08 \d{2}:\d{2}:\d{2}\] LOOP STARTUP.*?(?=\[2026-01-08|\Z)', content, re.DOTALL)

if iterations:
    last_iter = iterations[-1]

    # Check dry-run status
    dry_run_match = re.search(r'Dry-Run:\s*(True|False)', last_iter)
    if dry_run_match:
        print(f"[OK] Dry-Run Status: {dry_run_match.group(1)}")

    # Check broker type
    if 'Using MockBroker' in last_iter:
        print("[OK] Broker: MockBroker (dry-run mode)")
    elif 'Using AlpacaBroker' in last_iter or 'Alpaca' in last_iter:
        print("[OK] Broker: AlpacaBroker (LIVE mode)")
    else:
        print("[?] Broker: Unknown")

    # Check for orders
    if '[DRY-RUN]' in last_iter:
        print("[OK] Orders: Simulated (dry-run)")
    elif 'BUY' in last_iter or 'SELL' in last_iter:
        print("[OK] Orders: LIVE (sent to Alpaca)")
    else:
        print("[?] Orders: None placed")

    # Show command
    cmd_match = re.search(r'Command: (.+)', last_iter)
    if cmd_match:
        print(f"\n[OK] Command: {cmd_match.group(1)}")
else:
    print("No iterations found today")
