"""Tests for FastAPI dashboard service."""


import pytest
from fastapi.testclient import TestClient

from src.ui_api.app import app


@pytest.fixture
def temp_config_and_ledger(tmp_path, monkeypatch):
    """Create temporary config and ledger directories."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create config directory with strategies.yaml
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config_file = config_dir / "strategies.yaml"
    config_file.write_text(
        """
strategies:
  - strategy_id: "TestStrategy1"
    name: "Test Strategy 1"
    description: "Test strategy"
    enabled: true
    weight: 0.6
    params:
      sma_fast_period: 10
      sma_slow_period: 20
    risk_limits:
      max_position_size: 5000
      max_positions: 3
      max_daily_loss: 500

  - strategy_id: "TestStrategy2"
    name: "Test Strategy 2"
    description: "Another test strategy"
    enabled: false
    weight: 0.4
    params:
      sma_fast_period: 5
      sma_slow_period: 15
    risk_limits:
      max_position_size: 3000
      max_positions: 5
      max_daily_loss: 300

global:
  max_daily_loss: 1000
  max_total_positions: 10
  max_order_notional: 10000
  bar_timeframe: "1Min"
  market_open_hour: 9
  market_open_minute: 30
  market_close_hour: 16
  market_close_minute: 0
"""
    )

    # Create out/ledger directory
    ledger_dir = tmp_path / "out" / "ledger"
    ledger_dir.mkdir(parents=True)

    return tmp_path


@pytest.fixture
def client(temp_config_and_ledger):
    """Create test client."""
    # TestClient automatically handles lifespan events
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    """Test GET /health endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["registry_loaded"] is True
    assert data["ledger_available"] is True


def test_account_summary_endpoint(client):
    """Test GET /account/summary endpoint."""
    response = client.get("/account/summary")

    assert response.status_code == 200
    data = response.json()

    assert "total_capital" in data
    assert data["max_daily_loss"] == 1000
    assert data["max_total_positions"] == 10
    assert data["enabled_strategies_count"] == 1  # Only TestStrategy1 is enabled
    assert data["total_strategies_count"] == 2


def test_strategies_endpoint(client):
    """Test GET /strategies endpoint."""
    response = client.get("/strategies")

    assert response.status_code == 200
    data = response.json()

    assert "strategies" in data
    assert "global_config" in data

    # Check strategies
    strategies = data["strategies"]
    assert len(strategies) == 2

    # Find TestStrategy1
    strat1 = next(s for s in strategies if s["strategy_id"] == "TestStrategy1")
    assert strat1["name"] == "Test Strategy 1"
    assert strat1["enabled"] is True
    assert strat1["weight"] == 0.6
    assert strat1["params"]["sma_fast_period"] == 10
    assert strat1["active_version"] == 1
    assert strat1["pending_version"] is None

    # Check global config
    global_config = data["global_config"]
    assert global_config["max_daily_loss"] == 1000
    assert global_config["bar_timeframe"] == "1Min"


def test_activity_endpoint_empty(client):
    """Test GET /activity endpoint with no events."""
    response = client.get("/activity")

    assert response.status_code == 200
    data = response.json()

    assert "events" in data
    assert "total_events" in data
    assert data["total_events"] == 0
    assert len(data["events"]) == 0


def test_activity_endpoint_with_limit(client):
    """Test GET /activity endpoint with limit parameter."""
    response = client.get("/activity?limit=10")

    assert response.status_code == 200
    data = response.json()

    assert "events" in data
    assert len(data["events"]) <= 10


def test_enable_strategy_endpoint(client):
    """Test POST /strategies/{id}/enable endpoint."""
    # Disable TestStrategy1
    response = client.post("/strategies/TestStrategy1/enable", json={"enabled": False})

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "disabled" in data["message"]
    assert data["pending_version"] == 2  # Version incremented

    # Verify strategy is staged for disable
    strategies_response = client.get("/strategies")
    strategies = strategies_response.json()["strategies"]
    strat1 = next(s for s in strategies if s["strategy_id"] == "TestStrategy1")

    assert strat1["enabled"] is False  # Changed immediately
    assert strat1["pending_version"] == 2  # Has pending version


def test_enable_strategy_invalid_id(client):
    """Test POST /strategies/{id}/enable with invalid strategy ID."""
    response = client.post("/strategies/NonExistentStrategy/enable", json={"enabled": True})

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_update_weight_endpoint(client):
    """Test POST /strategies/{id}/weight endpoint."""
    response = client.post("/strategies/TestStrategy1/weight", json={"weight": 0.8})

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "weight updated to 0.8" in data["message"]
    assert data["pending_version"] == 2

    # Verify weight is updated
    strategies_response = client.get("/strategies")
    strategies = strategies_response.json()["strategies"]
    strat1 = next(s for s in strategies if s["strategy_id"] == "TestStrategy1")

    assert strat1["weight"] == 0.8
    assert strat1["pending_version"] == 2


def test_update_weight_invalid_value(client):
    """Test POST /strategies/{id}/weight with invalid weight."""
    response = client.post("/strategies/TestStrategy1/weight", json={"weight": 1.5})

    assert response.status_code == 422  # Validation error


def test_update_weight_negative(client):
    """Test POST /strategies/{id}/weight with negative weight."""
    response = client.post("/strategies/TestStrategy1/weight", json={"weight": -0.1})

    assert response.status_code == 422  # Validation error


def test_update_params_endpoint(client):
    """Test POST /strategies/{id}/params endpoint."""
    new_params = {"sma_fast_period": 15, "sma_slow_period": 30}

    response = client.post("/strategies/TestStrategy1/params", json={"params": new_params})

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "parameters updated" in data["message"]
    assert data["pending_version"] == 2

    # Verify params are updated
    strategies_response = client.get("/strategies")
    strategies = strategies_response.json()["strategies"]
    strat1 = next(s for s in strategies if s["strategy_id"] == "TestStrategy1")

    assert strat1["params"]["sma_fast_period"] == 15
    assert strat1["params"]["sma_slow_period"] == 30
    assert strat1["pending_version"] == 2


def test_update_params_invalid_strategy(client):
    """Test POST /strategies/{id}/params with invalid strategy ID."""
    response = client.post(
        "/strategies/InvalidStrategy/params",
        json={"params": {"test": 123}},
    )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_multiple_changes_increment_version(client):
    """Test that multiple changes increment version correctly."""
    # Change 1: Disable
    response1 = client.post("/strategies/TestStrategy1/enable", json={"enabled": False})
    assert response1.json()["pending_version"] == 2

    # Change 2: Update weight
    response2 = client.post("/strategies/TestStrategy1/weight", json={"weight": 0.9})
    assert response2.json()["pending_version"] == 3

    # Change 3: Update params
    response3 = client.post(
        "/strategies/TestStrategy1/params",
        json={"params": {"sma_fast_period": 12}},
    )
    assert response3.json()["pending_version"] == 4

    # Verify final state
    strategies_response = client.get("/strategies")
    strategies = strategies_response.json()["strategies"]
    strat1 = next(s for s in strategies if s["strategy_id"] == "TestStrategy1")

    assert strat1["enabled"] is False
    assert strat1["weight"] == 0.9
    assert strat1["params"]["sma_fast_period"] == 12
    assert strat1["pending_version"] == 4
