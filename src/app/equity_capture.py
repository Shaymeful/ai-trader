"""Equity curve time series capture and management."""

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


def capture_equity_snapshot(
    equity: float,
    cash: float,
    mode: str,
    equity_file: Path | None = None,
    max_points: int = 5000,
) -> None:
    """
    Append equity snapshot to time series file.

    Args:
        equity: Current portfolio equity
        cash: Current cash balance
        mode: Trading mode ("paper" or "live")
        equity_file: Path to equity.jsonl file (default: out/perf/equity.jsonl)
        max_points: Maximum points to keep (default: 5000)
    """
    if equity_file is None:
        equity_file = Path("out/perf/equity.jsonl")

    # Ensure directory exists
    equity_file.parent.mkdir(parents=True, exist_ok=True)

    # Create snapshot
    snapshot = {
        "timestamp": datetime.now(UTC).isoformat(),
        "equity": equity,
        "cash": cash,
        "mode": mode,
    }

    # Read existing points if file exists
    existing_points = []
    if equity_file.exists():
        try:
            with open(equity_file, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            existing_points.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"WARNING: Failed to read existing equity data: {e}")
            existing_points = []

    # Append new snapshot
    existing_points.append(snapshot)

    # Keep only last max_points
    if len(existing_points) > max_points:
        existing_points = existing_points[-max_points:]

    # Write back atomically (temp file + rename)
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=equity_file.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for point in existing_points:
                tmp_file.write(json.dumps(point) + "\n")
            tmp_path = Path(tmp_file.name)

        tmp_path.replace(equity_file)

    except Exception as e:
        print(f"WARNING: Failed to write equity snapshot: {e}")
        # Clean up temp file if it exists
        if tmp_path.exists():
            tmp_path.unlink()


def load_equity_series(
    equity_file: Path | None = None,
    hours: int = 24,
) -> list[dict]:
    """
    Load equity time series filtered by time window.

    Args:
        equity_file: Path to equity.jsonl file (default: out/perf/equity.jsonl)
        hours: Time window in hours (default: 24)

    Returns:
        List of equity snapshots within time window
    """
    if equity_file is None:
        equity_file = Path("out/perf/equity.jsonl")

    if not equity_file.exists():
        return []

    # Calculate cutoff time
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # Load and filter points
    points = []
    try:
        with open(equity_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    point = json.loads(line)

                    # Parse timestamp
                    timestamp_str = point.get("timestamp", "")
                    timestamp = datetime.fromisoformat(timestamp_str)

                    # Filter by time window
                    if timestamp >= cutoff:
                        points.append(point)

                except (json.JSONDecodeError, ValueError):
                    continue

    except Exception as e:
        print(f"WARNING: Failed to load equity series: {e}")
        return []

    return points
