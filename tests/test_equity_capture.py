"""Tests for equity capture and time series."""

import json
from datetime import UTC, datetime, timedelta

from src.app.equity_capture import capture_equity_snapshot, load_equity_series


def test_capture_equity_snapshot_creates_file(tmp_path):
    """Test that capturing a snapshot creates the file."""
    equity_file = tmp_path / "equity.jsonl"

    capture_equity_snapshot(
        equity=100000.0,
        cash=50000.0,
        mode="paper",
        equity_file=equity_file,
    )

    assert equity_file.exists()

    # Read and verify content
    with open(equity_file, encoding="utf-8") as f:
        data = json.loads(f.readline())

    assert data["equity"] == 100000.0
    assert data["cash"] == 50000.0
    assert data["mode"] == "paper"
    assert "timestamp" in data


def test_capture_equity_snapshot_appends_to_existing(tmp_path):
    """Test that capturing appends to existing file."""
    equity_file = tmp_path / "equity.jsonl"

    # First snapshot
    capture_equity_snapshot(
        equity=100000.0,
        cash=50000.0,
        mode="paper",
        equity_file=equity_file,
    )

    # Second snapshot
    capture_equity_snapshot(
        equity=100500.0,
        cash=49500.0,
        mode="paper",
        equity_file=equity_file,
    )

    # Read all lines
    with open(equity_file, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 2

    data1 = json.loads(lines[0])
    data2 = json.loads(lines[1])

    assert data1["equity"] == 100000.0
    assert data2["equity"] == 100500.0


def test_capture_equity_snapshot_caps_at_max_points(tmp_path):
    """Test that file is capped at max_points."""
    equity_file = tmp_path / "equity.jsonl"

    # Write 10 snapshots with max_points=5
    for i in range(10):
        capture_equity_snapshot(
            equity=100000.0 + i * 1000,
            cash=50000.0,
            mode="paper",
            equity_file=equity_file,
            max_points=5,
        )

    # Read all lines
    with open(equity_file, encoding="utf-8") as f:
        lines = f.readlines()

    # Should only have last 5 points
    assert len(lines) == 5

    # Verify it's the last 5 (equity 105000-109000)
    data = [json.loads(line) for line in lines]
    equities = [d["equity"] for d in data]

    assert equities == [105000.0, 106000.0, 107000.0, 108000.0, 109000.0]


def test_capture_equity_snapshot_handles_missing_directory(tmp_path):
    """Test that missing directory is created."""
    equity_file = tmp_path / "perf" / "equity.jsonl"

    # Directory doesn't exist yet
    assert not equity_file.parent.exists()

    capture_equity_snapshot(
        equity=100000.0,
        cash=50000.0,
        mode="paper",
        equity_file=equity_file,
    )

    # Directory and file should be created
    assert equity_file.parent.exists()
    assert equity_file.exists()


def test_capture_equity_snapshot_handles_corrupted_file(tmp_path):
    """Test that corrupted file is handled gracefully."""
    equity_file = tmp_path / "equity.jsonl"

    # Write invalid JSON
    with open(equity_file, "w", encoding="utf-8") as f:
        f.write("not valid json\n")
        f.write("{incomplete: json\n")

    # Should still work (discard corrupted data)
    capture_equity_snapshot(
        equity=100000.0,
        cash=50000.0,
        mode="paper",
        equity_file=equity_file,
    )

    # Read lines
    with open(equity_file, encoding="utf-8") as f:
        lines = f.readlines()

    # Should only have new snapshot
    assert len(lines) == 1

    data = json.loads(lines[0])
    assert data["equity"] == 100000.0


def test_load_equity_series_returns_empty_if_no_file(tmp_path):
    """Test that missing file returns empty list."""
    equity_file = tmp_path / "equity.jsonl"

    points = load_equity_series(equity_file, hours=24)

    assert points == []


def test_load_equity_series_filters_by_time_window(tmp_path):
    """Test that time window filtering works."""
    equity_file = tmp_path / "equity.jsonl"

    # Write snapshots at different times
    now = datetime.now(UTC)

    snapshots = [
        {
            "timestamp": (now - timedelta(hours=48)).isoformat(),
            "equity": 100000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {
            "timestamp": (now - timedelta(hours=36)).isoformat(),
            "equity": 101000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {
            "timestamp": (now - timedelta(hours=12)).isoformat(),
            "equity": 102000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {
            "timestamp": (now - timedelta(hours=6)).isoformat(),
            "equity": 103000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {"timestamp": now.isoformat(), "equity": 104000.0, "cash": 50000.0, "mode": "paper"},
    ]

    with open(equity_file, "w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot) + "\n")

    # Load last 24 hours
    points = load_equity_series(equity_file, hours=24)

    # Should only get last 3 points (12h, 6h, now)
    assert len(points) == 3

    equities = [p["equity"] for p in points]
    assert equities == [102000.0, 103000.0, 104000.0]


def test_load_equity_series_handles_corrupted_lines(tmp_path):
    """Test that corrupted lines are skipped."""
    equity_file = tmp_path / "equity.jsonl"

    now = datetime.now(UTC)

    with open(equity_file, "w", encoding="utf-8") as f:
        f.write("not valid json\n")
        f.write(
            json.dumps(
                {"timestamp": now.isoformat(), "equity": 100000.0, "cash": 50000.0, "mode": "paper"}
            )
            + "\n"
        )
        f.write("{incomplete: json\n")
        f.write(
            json.dumps(
                {"timestamp": now.isoformat(), "equity": 101000.0, "cash": 50000.0, "mode": "paper"}
            )
            + "\n"
        )

    points = load_equity_series(equity_file, hours=24)

    # Should only get 2 valid points
    assert len(points) == 2

    equities = [p["equity"] for p in points]
    assert equities == [100000.0, 101000.0]


def test_load_equity_series_handles_missing_timestamp(tmp_path):
    """Test that entries without timestamp are skipped."""
    equity_file = tmp_path / "equity.jsonl"

    now = datetime.now(UTC)

    with open(equity_file, "w", encoding="utf-8") as f:
        # Missing timestamp
        f.write(json.dumps({"equity": 100000.0, "cash": 50000.0, "mode": "paper"}) + "\n")

        # Valid entry
        f.write(
            json.dumps(
                {"timestamp": now.isoformat(), "equity": 101000.0, "cash": 50000.0, "mode": "paper"}
            )
            + "\n"
        )

    points = load_equity_series(equity_file, hours=24)

    # Should only get 1 valid point
    assert len(points) == 1
    assert points[0]["equity"] == 101000.0


def test_capture_with_different_modes(tmp_path):
    """Test capturing snapshots in different modes."""
    equity_file = tmp_path / "equity.jsonl"

    capture_equity_snapshot(
        equity=100000.0,
        cash=50000.0,
        mode="paper",
        equity_file=equity_file,
    )

    capture_equity_snapshot(
        equity=200000.0,
        cash=100000.0,
        mode="live",
        equity_file=equity_file,
    )

    with open(equity_file, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 2

    data1 = json.loads(lines[0])
    data2 = json.loads(lines[1])

    assert data1["mode"] == "paper"
    assert data2["mode"] == "live"
