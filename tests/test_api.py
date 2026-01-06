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


def test_dashboard_endpoint(client):
    """Test GET / dashboard endpoint."""
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"AI Trader Strategy Dashboard" in response.content
    assert b"Account Summary" in response.content
    assert b"Strategies" in response.content


def test_health_detailed_endpoint(client):
    """Test GET /health/detailed endpoint."""
    response = client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()

    # Check all required fields
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["market_status"] in ["open", "closed"]
    assert data["registry_loaded"] is True
    assert data["ledger_available"] is True
    assert data["single_instance_ok"] is True
    assert isinstance(data["trading_paused"], bool)

    # Optional fields
    assert "last_loop_tick" in data
    assert "last_data_fetch_status" in data
    assert "last_error" in data


def test_allocation_endpoint(client):
    """Test GET /allocation endpoint."""
    response = client.get("/allocation")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "strategies" in data
    assert "timestamp" in data
    assert "mode" in data
    assert data["mode"] in ["equity-based", "legacy"]

    # Check strategies list
    strategies = data["strategies"]
    assert len(strategies) > 0

    # Calculate sum of normalized weights
    total_normalized_weight = sum(s["normalized_weight"] for s in strategies if s["enabled"])

    # Normalized weights should sum to approximately 1.0 (allow small floating point error)
    assert abs(total_normalized_weight - 1.0) < 0.0001

    # Check each strategy has required fields
    for strategy in strategies:
        assert "strategy_id" in strategy
        assert "enabled" in strategy
        assert "configured_weight" in strategy
        assert "normalized_weight" in strategy
        assert "budget" in strategy
        assert "utilization" in strategy

        # Normalized weight should be >= 0
        assert strategy["normalized_weight"] >= 0


def test_allocation_normalized_weights(client):
    """Test that allocation correctly normalizes weights when strategies are enabled/disabled."""
    # Initial state: TestStrategy1 enabled (0.6), TestStrategy2 disabled (0.4)
    response = client.get("/allocation")
    data = response.json()

    # Find enabled strategies
    enabled_strategies = [s for s in data["strategies"] if s["enabled"]]

    # Should only have TestStrategy1 enabled
    assert len(enabled_strategies) == 1
    assert enabled_strategies[0]["strategy_id"] == "TestStrategy1"
    assert enabled_strategies[0]["normalized_weight"] == 1.0  # 100% since it's the only one

    # Enable TestStrategy2
    client.post("/strategies/TestStrategy2/enable", json={"enabled": True})

    # Check allocation again
    response = client.get("/allocation")
    data = response.json()

    enabled_strategies = [s for s in data["strategies"] if s["enabled"]]
    assert len(enabled_strategies) == 2

    # Normalized weights should sum to 1.0
    total_weight = sum(s["normalized_weight"] for s in enabled_strategies)
    assert abs(total_weight - 1.0) < 0.0001

    # Check individual normalized weights (0.6 and 0.4 should normalize to 0.6 and 0.4)
    strat1 = next(s for s in enabled_strategies if s["strategy_id"] == "TestStrategy1")
    strat2 = next(s for s in enabled_strategies if s["strategy_id"] == "TestStrategy2")

    assert abs(strat1["normalized_weight"] - 0.6) < 0.0001
    assert abs(strat2["normalized_weight"] - 0.4) < 0.0001


def test_candidates_endpoint_no_snapshot(client):
    """Test GET /candidates endpoint when no snapshot file exists."""
    response = client.get("/candidates")

    assert response.status_code == 200
    data = response.json()

    # Should return empty candidates list
    assert "candidates" in data
    assert "count" in data
    assert "last_generated" in data

    assert data["count"] == 0
    assert len(data["candidates"]) == 0
    assert data["last_generated"] is None


def test_candidates_endpoint_with_snapshot(client, tmp_path):
    """Test GET /candidates endpoint with a valid snapshot file."""
    # Create out/selector directory
    selector_dir = tmp_path / "out" / "selector"
    selector_dir.mkdir(parents=True, exist_ok=True)

    # Create snapshot.json
    snapshot_file = selector_dir / "snapshot.json"
    snapshot_file.write_text(
        """
{
  "generated_at": "2026-01-05T10:00:00Z",
  "count": 2,
  "candidates": [
    {
      "candidate_id": "test-001",
      "created_at": "2026-01-05T10:00:00Z",
      "expires_at": "2026-01-06T10:00:00Z",
      "symbol": "AAPL",
      "action": "buy",
      "confidence": 0.85,
      "horizon": "intraday",
      "sector": "Technology",
      "event_type": "earnings",
      "tags": ["momentum", "breakout"],
      "reason": "Strong earnings beat",
      "avg_dollar_volume": 50000000000.0
    },
    {
      "candidate_id": "test-002",
      "created_at": "2026-01-05T10:00:00Z",
      "expires_at": "2026-01-06T10:00:00Z",
      "symbol": "SPY",
      "action": "watch",
      "confidence": 0.65,
      "horizon": "swing",
      "sector": null,
      "event_type": "technical",
      "tags": ["trend"],
      "reason": "Watching for breakout",
      "avg_dollar_volume": 25000000000.0
    }
  ],
  "metadata": {
    "source": "test_snapshot"
  }
}
"""
    )

    response = client.get("/candidates")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert data["count"] == 2
    assert len(data["candidates"]) == 2
    assert data["last_generated"] == "2026-01-05T10:00:00Z"

    # Check first candidate
    aapl = data["candidates"][0]
    assert aapl["symbol"] == "AAPL"
    assert aapl["action"] == "buy"
    assert aapl["confidence"] == 0.85
    assert aapl["horizon"] == "intraday"
    assert aapl["sector"] == "Technology"
    assert aapl["tags"] == ["momentum", "breakout"]
    assert aapl["reason"] == "Strong earnings beat"
    assert aapl["expires_at"] == "2026-01-06T10:00:00Z"

    # Check second candidate
    spy = data["candidates"][1]
    assert spy["symbol"] == "SPY"
    assert spy["action"] == "watch"
    assert spy["sector"] is None


def test_pause_trading_endpoint(client, tmp_path):
    """Test POST /pause_trading endpoint."""
    # Create state directory
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    pause_flag = state_dir / "pause_trading.flag"

    # Ensure flag doesn't exist initially
    if pause_flag.exists():
        pause_flag.unlink()

    # Test pausing trading
    response = client.post("/pause_trading", json={"paused": True})

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "paused" in data["message"].lower()
    assert pause_flag.exists()

    # Verify health endpoint shows paused state
    health_response = client.get("/health/detailed")
    health_data = health_response.json()
    assert health_data["trading_paused"] is True

    # Test unpausing trading
    response = client.post("/pause_trading", json={"paused": False})

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "resumed" in data["message"].lower()
    assert not pause_flag.exists()

    # Verify health endpoint shows unpaused state
    health_response = client.get("/health/detailed")
    health_data = health_response.json()
    assert health_data["trading_paused"] is False


def test_pause_trading_idempotent(client, tmp_path):
    """Test that pause_trading endpoint is idempotent."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    # Pause twice - should succeed both times
    response1 = client.post("/pause_trading", json={"paused": True})
    assert response1.status_code == 200
    assert response1.json()["success"] is True

    response2 = client.post("/pause_trading", json={"paused": True})
    assert response2.status_code == 200
    assert response2.json()["success"] is True

    # Unpause twice - should succeed both times
    response3 = client.post("/pause_trading", json={"paused": False})
    assert response3.status_code == 200
    assert response3.json()["success"] is True

    response4 = client.post("/pause_trading", json={"paused": False})
    assert response4.status_code == 200
    assert response4.json()["success"] is True


def test_dashboard_has_new_sections(client):
    """Test that dashboard HTML includes new operational control sections."""
    response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Check for new CSS classes
    assert "health-panel" in content
    assert "candidates-section" in content
    assert "pause-control" in content

    # Check for new UI elements
    assert "Market Status" in content
    assert "Pause Trading" in content
    assert "Candidates" in content

    # Check for filter controls
    assert "filter-action" in content
    assert "filter-min-confidence" in content
    assert "filter-search" in content

    # Check for JavaScript functions
    assert "updateHealthPanel" in content
    assert "togglePauseTrading" in content
    assert "renderCandidates" in content
    assert "filterCandidates" in content


def test_universe_sectors_endpoint(client):
    """Test GET /universe/sectors endpoint."""
    response = client.get("/universe/sectors")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "sectors" in data
    assert "resolved_symbols" in data
    assert "total_symbols" in data
    assert "fallback_mode" in data
    assert "source" in data
    assert "deduplication_count" in data
    assert "warnings" in data

    # Check sectors list
    sectors = data["sectors"]
    assert isinstance(sectors, list)
    assert len(sectors) > 0

    # Check first sector structure
    if sectors:
        sector = sectors[0]
        assert "sector_name" in sector
        assert "enabled" in sector
        assert "description" in sector
        assert "symbols" in sector
        assert "symbol_count" in sector

    # Check resolved symbols
    assert isinstance(data["resolved_symbols"], list)
    assert data["total_symbols"] == len(data["resolved_symbols"])

    # Verify fallback mode is valid
    assert data["fallback_mode"] in ["preserve_order", "alphabetical", "random"]

    # Verify source is valid
    assert data["source"] in ["sectors", "legacy", "empty"]
