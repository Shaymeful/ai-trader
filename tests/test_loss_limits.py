"""Tests for the daily/session loss kill switches wired into the runner path.

Covers two layers:
  1. LossLimitGuard drawdown math + baseline persistence (process vs Eastern date).
  2. AlpacaExecutor enforcement: risk-increasing BUYs are blocked when the switch
     has tripped, while risk-reducing SELL / flatten orders still go through.
"""

from decimal import Decimal

from src.app.config import Config
from src.app.execution import AlpacaExecutor
from src.app.loss_limits import LossLimitGuard, fetch_account_equity
from src.broker import MockBroker

# ---------------------------------------------------------------------------
# LossLimitGuard: drawdown math
# ---------------------------------------------------------------------------


def test_within_limits_not_tripped(tmp_path):
    guard = LossLimitGuard(state_path=tmp_path / "ll.json")
    # First call establishes the session + day baseline at 100000.
    guard.evaluate(
        current_equity=Decimal("100000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=Decimal("500"),
        today="2026-06-07",
    )
    # Down 200 — within both limits.
    state = guard.evaluate(
        current_equity=Decimal("99800"),
        max_daily_loss=Decimal("500"),
        max_session_loss=Decimal("500"),
        today="2026-06-07",
    )
    assert state.tripped is False
    assert state.daily_drawdown == Decimal("200")
    assert state.session_drawdown == Decimal("200")
    assert state.equity_available is True


def test_daily_loss_trips(tmp_path):
    guard = LossLimitGuard(state_path=tmp_path / "ll.json")
    # First observation sets day-start baseline at 100000.
    guard.evaluate(
        current_equity=Decimal("100000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=None,
        today="2026-06-07",
    )
    # Equity falls to 99000 -> drawdown 1000 >= 500 -> tripped.
    state = guard.evaluate(
        current_equity=Decimal("99000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=None,
        today="2026-06-07",
    )
    assert state.tripped is True
    assert state.daily_drawdown == Decimal("1000")
    assert any("Daily loss" in r for r in state.reasons)


def test_session_loss_trips_independently_of_daily(tmp_path):
    guard = LossLimitGuard(state_path=tmp_path / "ll.json")
    # High daily limit so only the session switch can trip.
    guard.evaluate(
        current_equity=Decimal("100000"),
        max_daily_loss=Decimal("1000000"),
        max_session_loss=Decimal("500"),
        today="2026-06-07",
    )
    state = guard.evaluate(
        current_equity=Decimal("99000"),
        max_daily_loss=Decimal("1000000"),
        max_session_loss=Decimal("500"),
        today="2026-06-07",
    )
    assert state.tripped is True
    assert state.session_drawdown == Decimal("1000")
    assert any("Session loss" in r for r in state.reasons)


# ---------------------------------------------------------------------------
# LossLimitGuard: baselines
# ---------------------------------------------------------------------------


def test_day_start_equity_persists_across_processes(tmp_path):
    """A restart (new guard instance) must NOT reset the daily baseline."""
    path = tmp_path / "ll.json"
    guard1 = LossLimitGuard(state_path=path)
    guard1.evaluate(
        current_equity=Decimal("100000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=None,
        today="2026-06-07",
    )

    # New process: fresh guard, same persisted state, equity already down 1000.
    guard2 = LossLimitGuard(state_path=path)
    state = guard2.evaluate(
        current_equity=Decimal("99000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=None,
        today="2026-06-07",
    )
    # Baseline came from disk (100000), so the limit cannot be reset by restarting.
    assert state.day_start_equity == Decimal("100000")
    assert state.tripped is True


def test_day_start_equity_rebaselines_on_new_date(tmp_path):
    path = tmp_path / "ll.json"
    guard = LossLimitGuard(state_path=path)
    guard.evaluate(
        current_equity=Decimal("100000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=None,
        today="2026-06-07",
    )
    # New trading date -> baseline resets to current equity, no carry-over loss.
    state = guard.evaluate(
        current_equity=Decimal("99000"),
        max_daily_loss=Decimal("500"),
        max_session_loss=None,
        today="2026-06-08",
    )
    assert state.day_start_equity == Decimal("99000")
    assert state.daily_drawdown == Decimal("0")
    assert state.tripped is False


def test_session_start_captured_once(tmp_path):
    guard = LossLimitGuard(state_path=tmp_path / "ll.json")
    assert guard.capture_session_start(Decimal("100000")) == Decimal("100000")
    # Later equity does not change the session baseline within the same process.
    assert guard.capture_session_start(Decimal("90000")) == Decimal("100000")


def test_equity_unavailable_fails_closed(tmp_path):
    path = tmp_path / "ll.json"
    guard = LossLimitGuard(state_path=path)
    state = guard.evaluate(
        current_equity=None,
        max_daily_loss=Decimal("500"),
        max_session_loss=Decimal("500"),
    )
    assert state.tripped is True
    assert state.equity_available is False
    # No baseline should be written from a bad reading.
    assert not path.exists()


def test_fetch_account_equity_from_client_shim():
    class _Acct:
        equity = "12345.67"

    class _Client:
        def get_account(self):
            return _Acct()

    class _Broker:
        client = _Client()

    assert fetch_account_equity(_Broker()) == Decimal("12345.67")


def test_fetch_account_equity_returns_none_for_plain_mock():
    # MockBroker has no account/equity interface -> None (caller fails closed).
    assert fetch_account_equity(MockBroker()) is None


# ---------------------------------------------------------------------------
# Executor enforcement
# ---------------------------------------------------------------------------


def _config():
    return Config(
        max_positions_notional=Decimal("100000"),
        max_order_notional=Decimal("100000"),
        max_daily_loss=Decimal("500"),
    )


def test_kill_switch_blocks_risk_increasing_buy():
    broker = MockBroker()
    executor = AlpacaExecutor(
        broker,
        _config(),
        dry_run=False,
        block_new_risk=True,
        block_new_risk_reason="Daily loss limit exceeded",
    )

    # Flat -> target 10 is a risk-increasing BUY, must be blocked.
    result = executor.reconcile_and_execute({"SPY": 10}, {"SPY": Decimal("450.00")})

    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) == 1
    symbol, reason = result.orders_skipped[0]
    assert symbol == "SPY"
    assert "loss kill switch" in reason.lower()
    assert "SPY" not in broker.positions  # nothing bought


def test_kill_switch_allows_risk_reducing_sell():
    broker = MockBroker()
    broker.positions["SPY"] = (10, Decimal("440.00"))
    executor = AlpacaExecutor(
        broker,
        _config(),
        dry_run=False,
        block_new_risk=True,
        block_new_risk_reason="Daily loss limit exceeded",
    )

    # Long 10 -> target 5 is a risk-reducing SELL, must still go through.
    result = executor.reconcile_and_execute({"SPY": 5}, {"SPY": Decimal("450.00")})

    assert len(result.orders_placed) == 1
    assert len(result.orders_skipped) == 0
    assert broker.positions["SPY"][0] == 5  # position reduced


def test_kill_switch_allows_full_flatten():
    broker = MockBroker()
    broker.positions["SPY"] = (10, Decimal("440.00"))
    executor = AlpacaExecutor(
        broker,
        _config(),
        dry_run=False,
        block_new_risk=True,
        block_new_risk_reason="Session loss limit exceeded",
    )

    # Long 10 -> not in target == flatten to 0, must still go through.
    result = executor.reconcile_and_execute({}, {"SPY": Decimal("450.00")})

    assert len(result.orders_placed) == 1
    assert "SPY" not in broker.positions  # fully closed


def test_kill_switch_blocks_buy_but_allows_sell_in_same_tick():
    broker = MockBroker()
    broker.positions["SPY"] = (10, Decimal("440.00"))
    executor = AlpacaExecutor(
        broker,
        _config(),
        dry_run=False,
        block_new_risk=True,
        block_new_risk_reason="Daily loss limit exceeded",
    )

    # SELL SPY (risk-reducing) should pass; BUY AAPL (risk-increasing) blocked.
    result = executor.reconcile_and_execute(
        {"SPY": 5, "AAPL": 3},
        {"SPY": Decimal("450.00"), "AAPL": Decimal("190.00")},
    )

    assert len(result.orders_placed) == 1
    assert broker.positions["SPY"][0] == 5
    assert "AAPL" not in broker.positions
    skipped_symbols = {sym for sym, _ in result.orders_skipped}
    assert "AAPL" in skipped_symbols


def test_no_block_when_switch_not_tripped():
    broker = MockBroker()
    executor = AlpacaExecutor(
        broker,
        _config(),
        dry_run=False,
        block_new_risk=False,
    )

    result = executor.reconcile_and_execute({"SPY": 10}, {"SPY": Decimal("450.00")})

    assert len(result.orders_placed) == 1
    assert broker.positions["SPY"][0] == 10
