"""Tests for ledger system."""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.app.ledger import (
    Ledger,
    OrderFilledEvent,
    OrderPlacedEvent,
    PositionUpdateEvent,
    SignalGeneratedEvent,
    StrategyConfigActivatedEvent,
)


@pytest.fixture
def temp_ledger_dir(tmp_path):
    """Create temporary ledger directory."""
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    return ledger_dir


@pytest.fixture
def ledger(temp_ledger_dir):
    """Create ledger instance."""
    return Ledger(ledger_dir=temp_ledger_dir)


def test_ledger_appends_event(ledger, temp_ledger_dir):
    """Test that ledger appends event to file."""
    event = StrategyConfigActivatedEvent(
        strategy_id="TestStrategy1",
        version=1,
        config_snapshot={"enabled": True, "weight": 0.5},
    )

    ledger.append(event)

    # Check file was created
    today = datetime.now(UTC).date()
    ledger_file = temp_ledger_dir / f"{today.isoformat()}.jsonl"
    assert ledger_file.exists()

    # Check content
    with open(ledger_file) as f:
        lines = f.readlines()
        assert len(lines) == 1

        event_dict = json.loads(lines[0])
        assert event_dict["event_type"] == "strategy_config_activated"
        assert event_dict["strategy_id"] == "TestStrategy1"
        assert event_dict["version"] == 1


def test_ledger_appends_multiple_events(ledger, temp_ledger_dir):
    """Test that ledger appends multiple events."""
    event1 = StrategyConfigActivatedEvent(
        strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
    )
    event2 = SignalGeneratedEvent(
        strategy_id="TestStrategy1",
        version=1,
        symbol="AAPL",
        signal_type="buy",
        strength=0.8,
    )
    event3 = OrderPlacedEvent(
        strategy_id="TestStrategy1",
        version=1,
        client_order_id="order-1",
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        order_type="market",
    )

    ledger.append(event1)
    ledger.append(event2)
    ledger.append(event3)

    # Check file has 3 lines
    today = datetime.now(UTC).date()
    ledger_file = temp_ledger_dir / f"{today.isoformat()}.jsonl"
    with open(ledger_file) as f:
        lines = f.readlines()
        assert len(lines) == 3


def test_ledger_read_all(ledger):
    """Test reading all events from ledger."""
    # Append some events
    event1 = StrategyConfigActivatedEvent(
        strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
    )
    event2 = SignalGeneratedEvent(
        strategy_id="TestStrategy1",
        version=1,
        symbol="AAPL",
        signal_type="buy",
        strength=0.8,
    )

    ledger.append(event1)
    ledger.append(event2)

    # Read all events
    events = ledger.read_all()

    assert len(events) == 2
    assert events[0]["event_type"] == "strategy_config_activated"
    assert events[1]["event_type"] == "signal_generated"


def test_ledger_read_all_empty(ledger):
    """Test reading from empty ledger."""
    events = ledger.read_all()
    assert events == []


def test_ledger_rebuild_state_empty(ledger):
    """Test rebuilding state from empty ledger."""
    state = ledger.rebuild_state()

    assert state["strategies"] == {}
    assert state["last_event_timestamp"] is None


def test_ledger_rebuild_state_with_config_activation(ledger):
    """Test rebuilding state with config activation events."""
    # Append activation event
    event = StrategyConfigActivatedEvent(
        strategy_id="TestStrategy1",
        version=1,
        config_snapshot={"enabled": True, "weight": 0.5},
    )
    ledger.append(event)

    # Rebuild state
    state = ledger.rebuild_state()

    assert "TestStrategy1" in state["strategies"]
    strat = state["strategies"]["TestStrategy1"]
    assert strat["active_version"] == 1
    assert strat["config"]["enabled"] is True
    assert strat["config"]["weight"] == 0.5


def test_ledger_rebuild_state_with_orders(ledger):
    """Test rebuilding state with order events."""
    # Config activation
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
        )
    )

    # Order placed
    ledger.append(
        OrderPlacedEvent(
            strategy_id="TestStrategy1",
            version=1,
            client_order_id="order-1",
            symbol="AAPL",
            side="buy",
            quantity=Decimal("10"),
            order_type="market",
        )
    )

    # Rebuild state
    state = ledger.rebuild_state()

    strat = state["strategies"]["TestStrategy1"]
    assert len(strat["orders"]) == 1
    order = strat["orders"][0]
    assert order["client_order_id"] == "order-1"
    assert order["symbol"] == "AAPL"
    assert order["side"] == "buy"
    assert order["quantity"] == Decimal("10")
    assert order["status"] == "placed"


def test_ledger_rebuild_state_with_fills(ledger):
    """Test rebuilding state with order fill events."""
    # Config activation
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
        )
    )

    # Order placed
    ledger.append(
        OrderPlacedEvent(
            strategy_id="TestStrategy1",
            version=1,
            client_order_id="order-1",
            symbol="AAPL",
            side="buy",
            quantity=Decimal("10"),
            order_type="market",
        )
    )

    # Order filled
    ledger.append(
        OrderFilledEvent(
            strategy_id="TestStrategy1",
            version=1,
            client_order_id="order-1",
            symbol="AAPL",
            side="buy",
            quantity=Decimal("10"),
            fill_price=Decimal("150.50"),
            fill_time=datetime.now(UTC),
        )
    )

    # Rebuild state
    state = ledger.rebuild_state()

    strat = state["strategies"]["TestStrategy1"]
    assert len(strat["orders"]) == 1
    order = strat["orders"][0]
    assert order["status"] == "filled"
    assert order["fill_price"] == Decimal("150.50")

    # Check realized PnL (buy decreases PnL)
    assert strat["realized_pnl"] == Decimal("-1505.00")  # -10 * 150.50


def test_ledger_rebuild_state_with_positions(ledger):
    """Test rebuilding state with position update events."""
    # Config activation
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
        )
    )

    # Position update
    ledger.append(
        PositionUpdateEvent(
            strategy_id="TestStrategy1",
            version=1,
            symbol="AAPL",
            quantity=10,
            avg_price=Decimal("150.50"),
            current_price=Decimal("152.00"),
            unrealized_pnl=Decimal("15.00"),
        )
    )

    # Rebuild state
    state = ledger.rebuild_state()

    strat = state["strategies"]["TestStrategy1"]
    assert "AAPL" in strat["positions"]
    position = strat["positions"]["AAPL"]
    assert position["quantity"] == 10
    assert position["avg_price"] == Decimal("150.50")
    assert position["current_price"] == Decimal("152.00")
    assert position["unrealized_pnl"] == Decimal("15.00")


def test_ledger_rebuild_state_multiple_strategies(ledger):
    """Test rebuilding state with multiple strategies."""
    # Strategy 1 activation
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
        )
    )

    # Strategy 2 activation
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy2", version=1, config_snapshot={"enabled": False}
        )
    )

    # Orders for both strategies
    ledger.append(
        OrderPlacedEvent(
            strategy_id="TestStrategy1",
            version=1,
            client_order_id="order-1",
            symbol="AAPL",
            side="buy",
            quantity=Decimal("10"),
            order_type="market",
        )
    )

    ledger.append(
        OrderPlacedEvent(
            strategy_id="TestStrategy2",
            version=1,
            client_order_id="order-2",
            symbol="MSFT",
            side="buy",
            quantity=Decimal("5"),
            order_type="market",
        )
    )

    # Rebuild state
    state = ledger.rebuild_state()

    assert len(state["strategies"]) == 2
    assert "TestStrategy1" in state["strategies"]
    assert "TestStrategy2" in state["strategies"]

    assert state["strategies"]["TestStrategy1"]["config"]["enabled"] is True
    assert state["strategies"]["TestStrategy2"]["config"]["enabled"] is False

    assert len(state["strategies"]["TestStrategy1"]["orders"]) == 1
    assert len(state["strategies"]["TestStrategy2"]["orders"]) == 1


def test_ledger_rebuild_state_version_updates(ledger):
    """Test that later config activations update version."""
    # Initial activation
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=1, config_snapshot={"weight": 0.5}
        )
    )

    # Later activation with new version
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=2, config_snapshot={"weight": 0.7}
        )
    )

    # Rebuild state
    state = ledger.rebuild_state()

    strat = state["strategies"]["TestStrategy1"]
    assert strat["active_version"] == 2
    assert strat["config"]["weight"] == 0.7


def test_ledger_handles_limit_orders(ledger):
    """Test that ledger correctly handles limit orders with limit_price."""
    ledger.append(
        StrategyConfigActivatedEvent(
            strategy_id="TestStrategy1", version=1, config_snapshot={"enabled": True}
        )
    )

    # Place limit order
    ledger.append(
        OrderPlacedEvent(
            strategy_id="TestStrategy1",
            version=1,
            client_order_id="order-1",
            symbol="AAPL",
            side="buy",
            quantity=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150.00"),
        )
    )

    # Rebuild state
    state = ledger.rebuild_state()

    order = state["strategies"]["TestStrategy1"]["orders"][0]
    assert order["order_type"] == "limit"
    assert order["limit_price"] == Decimal("150.00")


def test_signal_generated_event_serialization(ledger):
    """Test that signal events are correctly serialized."""
    event = SignalGeneratedEvent(
        strategy_id="TestStrategy1",
        version=1,
        symbol="AAPL",
        signal_type="buy",
        strength=0.85,
        metadata={"sma_fast": 151.2, "sma_slow": 150.0},
    )

    ledger.append(event)

    events = ledger.read_all()
    assert len(events) == 1
    assert events[0]["event_type"] == "signal_generated"
    assert events[0]["symbol"] == "AAPL"
    assert events[0]["signal_type"] == "buy"
    assert events[0]["strength"] == 0.85
    assert events[0]["metadata"]["sma_fast"] == 151.2
