"""Tests for UI API enhancements (sector editor, account summary, performance)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from src.ui_api.app import app

    return TestClient(app)


@pytest.fixture
def mock_universe_registry():
    """Mock universe registry."""
    mock = MagicMock()
    mock.sectors = {
        "mega_cap_tech": MagicMock(
            symbols=["AAPL", "MSFT", "GOOGL"],
            enabled=True,
            description="Mega cap tech",
        )
    }
    return mock


def test_update_sector_tickers_add(client, mock_universe_registry, tmp_path, monkeypatch):
    """Test adding tickers to a sector."""
    # Mock universe_registry
    import src.ui_api.app

    monkeypatch.setattr(src.ui_api.app, "universe_registry", mock_universe_registry)

    # Mock ledger
    mock_ledger = MagicMock()
    monkeypatch.setattr(src.ui_api.app, "ledger", mock_ledger)

    # Mock stage_constituent_change
    mock_universe_registry.stage_constituent_change.return_value = 2

    # Make request
    response = client.post(
        "/universe/sectors/mega_cap_tech/tickers",
        json={"add": ["NVDA", "AMD"], "remove": []},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert "Added 2 ticker(s)" in result["message"]
    assert result["pending_version"] == 2

    # Verify stage_constituent_change was called (order may vary due to set conversion)
    assert mock_universe_registry.stage_constituent_change.called
    call_args = mock_universe_registry.stage_constituent_change.call_args
    assert call_args[0][0] == "mega_cap_tech"
    assert call_args[0][1] == "add"
    assert set(call_args[0][2]) == {"NVDA", "AMD"}

    # Verify ledger was called
    assert mock_ledger.append.called


def test_update_sector_tickers_remove(client, mock_universe_registry, tmp_path, monkeypatch):
    """Test removing tickers from a sector."""
    import src.ui_api.app

    monkeypatch.setattr(src.ui_api.app, "universe_registry", mock_universe_registry)
    mock_ledger = MagicMock()
    monkeypatch.setattr(src.ui_api.app, "ledger", mock_ledger)

    mock_universe_registry.stage_constituent_change.return_value = 2

    response = client.post(
        "/universe/sectors/mega_cap_tech/tickers",
        json={"add": [], "remove": ["GOOGL"]},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert "Removed 1 ticker(s)" in result["message"]


def test_update_sector_tickers_invalid_sector(client, mock_universe_registry, monkeypatch):
    """Test updating tickers for non-existent sector."""
    import src.ui_api.app

    monkeypatch.setattr(src.ui_api.app, "universe_registry", mock_universe_registry)
    mock_ledger = MagicMock()
    monkeypatch.setattr(src.ui_api.app, "ledger", mock_ledger)

    response = client.post(
        "/universe/sectors/nonexistent/tickers",
        json={"add": ["AAPL"], "remove": []},
    )

    assert response.status_code == 404


def test_update_sector_tickers_empty_request(client, mock_universe_registry, monkeypatch):
    """Test updating with no add or remove."""
    import src.ui_api.app

    monkeypatch.setattr(src.ui_api.app, "universe_registry", mock_universe_registry)
    mock_ledger = MagicMock()
    monkeypatch.setattr(src.ui_api.app, "ledger", mock_ledger)

    response = client.post(
        "/universe/sectors/mega_cap_tech/tickers",
        json={"add": [], "remove": []},
    )

    assert response.status_code == 400


def test_update_account_summary(client, tmp_path, monkeypatch):
    """Test updating account summary settings."""
    import src.ui_api.app

    mock_ledger = MagicMock()
    monkeypatch.setattr(src.ui_api.app, "ledger", mock_ledger)

    # Use tmp_path for settings file
    settings_file = tmp_path / "account_summary.json"
    monkeypatch.setattr(
        Path,
        "__truediv__",
        lambda self, other: settings_file if other == "account_summary.json" else self / other,
    )

    response = client.post(
        "/account/summary",
        json={
            "total_capital": 50000.0,
            "max_daily_loss": 1500.0,
            "max_total_positions": 15,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert "total_capital" in result["message"]


def test_get_account_performance_unavailable(client, monkeypatch):
    """Test getting performance when broker unavailable."""

    # Mock config to raise exception
    def mock_load_config():
        raise Exception("Config not available")

    with patch("src.app.config.load_config_with_yaml", side_effect=mock_load_config):
        response = client.get("/account/performance")

    assert response.status_code == 200
    result = response.json()
    assert result["data_source"] == "unavailable"
    assert result["equity"] is None


def test_get_account_performance_with_broker(client, monkeypatch):
    """Test getting performance from broker."""
    # Mock config
    mock_config = MagicMock()
    mock_config.mode = "paper"
    mock_config.alpaca_paper_key_id = "test_key"
    mock_config.alpaca_paper_secret_key = "test_secret"

    # Mock broker account
    mock_account = MagicMock()
    mock_account.equity = "100000.00"
    mock_account.last_equity = "99500.00"
    mock_account.cash = "50000.00"
    mock_account.buying_power = "200000.00"

    mock_broker = MagicMock()
    mock_broker.get_account.return_value = mock_account

    with (
        patch("src.app.config.load_config_with_yaml", return_value=mock_config),
        patch("src.broker.base.AlpacaBroker", return_value=mock_broker),
    ):
        response = client.get("/account/performance")

    assert response.status_code == 200
    result = response.json()
    assert result["data_source"] == "paper"
    assert result["equity"] == 100000.0
    assert result["day_pl"] == 500.0
    assert result["day_pl_pct"] > 0
