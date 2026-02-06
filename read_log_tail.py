#!/usr/bin/env python3
"""Read last lines of Unicode log file."""
import sys

try:
    with open(r'logs\loop\loop_20260107.log', 'r', encoding='utf-16-le') as f:
        lines = f.readlines()
        # Print last 80 lines
        for line in lines[-80:]:
            print(line.rstrip())
except Exception as e:
    print(f"Error reading log: {e}", file=sys.stderr)
    sys.exit(1)
