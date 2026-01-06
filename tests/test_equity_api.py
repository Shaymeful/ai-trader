"""Tests for equity series API endpoint."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from src.ui_api.app import app

    return TestClient(app)


def test_get_equity_series_empty(client, tmp_path, monkeypatch):
    """Test equity series endpoint with no data."""

    # Mock Path to return tmp_path
    def mock_path(x):
        if x == "out/perf/equity.jsonl":
            return tmp_path / "equity.jsonl"
        return Path(x)

    monkeypatch.setattr("src.app.equity_capture.Path", mock_path)

    response = client.get("/account/performance/series")

    assert response.status_code == 200
    data = response.json()

    assert data["points"] == []
    assert data["count"] == 0
    assert data["hours"] == 24


def test_get_equity_series_with_data(client, tmp_path, monkeypatch):
    """Test equity series endpoint with data."""
    equity_file = tmp_path / "equity.jsonl"
    equity_file.parent.mkdir(parents=True, exist_ok=True)

    # Write test data
    now = datetime.now(UTC)
    snapshots = [
        {
            "timestamp": (now - timedelta(hours=12)).isoformat(),
            "equity": 100000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {
            "timestamp": (now - timedelta(hours=6)).isoformat(),
            "equity": 101000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {"timestamp": now.isoformat(), "equity": 102000.0, "cash": 50000.0, "mode": "paper"},
    ]

    with open(equity_file, "w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot) + "\n")

    # Mock load_equity_series to use our test file
    from src.app.equity_capture import load_equity_series as original_load

    def mock_load_equity_series(equity_file_param=None, hours=24):
        return original_load(equity_file, hours)

    monkeypatch.setattr("src.app.equity_capture.load_equity_series", mock_load_equity_series)

    response = client.get("/account/performance/series")

    assert response.status_code == 200
    data = response.json()

    assert len(data["points"]) == 3
    assert data["count"] == 3
    assert data["hours"] == 24

    # Verify data
    assert data["points"][0]["equity"] == 100000.0
    assert data["points"][1]["equity"] == 101000.0
    assert data["points"][2]["equity"] == 102000.0


def test_get_equity_series_with_custom_hours(client, tmp_path, monkeypatch):
    """Test equity series endpoint with custom time window."""
    equity_file = tmp_path / "equity.jsonl"
    equity_file.parent.mkdir(parents=True, exist_ok=True)

    # Write test data
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
        {"timestamp": now.isoformat(), "equity": 103000.0, "cash": 50000.0, "mode": "paper"},
    ]

    with open(equity_file, "w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot) + "\n")

    # Mock load_equity_series to use our test file
    from src.app.equity_capture import load_equity_series as original_load

    def mock_load_equity_series(equity_file_param=None, hours=24):
        return original_load(equity_file, hours)

    monkeypatch.setattr("src.app.equity_capture.load_equity_series", mock_load_equity_series)

    # Request last 24 hours only
    response = client.get("/account/performance/series?hours=24")

    assert response.status_code == 200
    data = response.json()

    # Should only get last 2 points (12h and now)
    assert len(data["points"]) == 2
    assert data["count"] == 2
    assert data["hours"] == 24


def test_get_equity_series_caps_max_hours(client, tmp_path, monkeypatch):
    """Test that hours parameter is capped at 720."""
    equity_file = tmp_path / "equity.jsonl"
    equity_file.parent.mkdir(parents=True, exist_ok=True)

    # Mock Path to return tmp_path
    def mock_path(x):
        if x == "out/perf/equity.jsonl":
            return equity_file
        return Path(x)

    monkeypatch.setattr("src.app.equity_capture.Path", mock_path)

    # Request 1000 hours (should be capped at 720)
    response = client.get("/account/performance/series?hours=1000")

    assert response.status_code == 200
    data = response.json()

    # Should be capped at 720
    assert data["hours"] == 720


def test_get_equity_series_filters_old_data(client, tmp_path, monkeypatch):
    """Test that old data is filtered out."""
    equity_file = tmp_path / "equity.jsonl"
    equity_file.parent.mkdir(parents=True, exist_ok=True)

    # Write test data
    now = datetime.now(UTC)
    snapshots = [
        {
            "timestamp": (now - timedelta(hours=100)).isoformat(),
            "equity": 100000.0,
            "cash": 50000.0,
            "mode": "paper",
        },
        {
            "timestamp": (now - timedelta(hours=50)).isoformat(),
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
        {"timestamp": now.isoformat(), "equity": 103000.0, "cash": 50000.0, "mode": "paper"},
    ]

    with open(equity_file, "w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot) + "\n")

    # Mock load_equity_series to use our test file
    from src.app.equity_capture import load_equity_series as original_load

    def mock_load_equity_series(equity_file_param=None, hours=24):
        return original_load(equity_file, hours)

    monkeypatch.setattr("src.app.equity_capture.load_equity_series", mock_load_equity_series)

    # Request last 24 hours only
    response = client.get("/account/performance/series?hours=24")

    assert response.status_code == 200
    data = response.json()

    # Should only get last 2 points (within 24 hours)
    assert len(data["points"]) == 2

    equities = [p["equity"] for p in data["points"]]
    assert 102000.0 in equities
    assert 103000.0 in equities
