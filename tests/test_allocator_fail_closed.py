"""Tests for fail-closed allocator behavior on account-equity failure.

When real orders could be placed (live/paper, real broker, not dry-run), an equity
fetch failure or equity <= 0 must NOT silently fall back to legacy equal-weight
allocation. Instead the allocator returns a fail-closed result with no target
positions, so the runner places no orders. Dry-run/shadow may keep the fallback.
"""

from decimal import Decimal

from src.app.allocator import Allocator
from src.app.config import Config


class _RaisingClientBroker:
    """Real-order-style broker whose account fetch fails."""

    class _Client:
        def get_account(self):
            raise RuntimeError("network down")

    client = _Client()


def _equity_broker(equity_str):
    class _Acct:
        equity = equity_str

    class _Client:
        def get_account(self):
            return _Acct()

    class _Broker:
        client = _Client()

    return _Broker()


# A non-None sentinel registry so allocate() takes the registry path. The equity
# check runs before the registry is ever dereferenced, so a bare object is fine.
_REGISTRY_SENTINEL = object()


def _live_config():
    # dry_run defaults to False -> real orders possible with a real broker.
    return Config(max_positions_notional=Decimal("10000"))


def test_equity_fetch_failure_fails_closed_no_orders():
    allocator = Allocator(
        _live_config(), registry=_REGISTRY_SENTINEL, broker=_RaisingClientBroker()
    )

    result = allocator.allocate({}, {})

    assert result.fail_closed is True
    assert result.target_positions == {}
    assert result.strategy_budgets == {}
    assert result.equity_used is None
    assert any("fail-closed" in w.lower() for w in result.warnings)


def test_zero_equity_fails_closed_no_orders():
    allocator = Allocator(
        _live_config(), registry=_REGISTRY_SENTINEL, broker=_equity_broker("0")
    )

    result = allocator.allocate({}, {})

    assert result.fail_closed is True
    assert result.target_positions == {}


def test_negative_equity_fails_closed_no_orders():
    allocator = Allocator(
        _live_config(), registry=_REGISTRY_SENTINEL, broker=_equity_broker("-100.00")
    )

    result = allocator.allocate({}, {})

    assert result.fail_closed is True
    assert result.target_positions == {}


def test_dry_run_keeps_legacy_fallback_on_equity_failure():
    """In dry-run mode the legacy fallback is retained (no fail-closed)."""
    config = Config(max_positions_notional=Decimal("10000"))
    config.dry_run = True

    allocator = Allocator(
        config, registry=_REGISTRY_SENTINEL, broker=_RaisingClientBroker()
    )

    result = allocator.allocate({}, {})

    # Falls back to legacy (does not fail closed, does not raise).
    assert result.fail_closed is False
    assert result.target_positions == {}


def test_real_orders_possible_predicate():
    # Real broker + not dry-run -> real orders possible.
    a = Allocator(_live_config(), registry=_REGISTRY_SENTINEL, broker=_RaisingClientBroker())
    assert a._real_orders_possible() is True

    # dry-run -> not possible.
    cfg = Config(max_positions_notional=Decimal("10000"))
    cfg.dry_run = True
    b = Allocator(cfg, registry=_REGISTRY_SENTINEL, broker=_RaisingClientBroker())
    assert b._real_orders_possible() is False

    # No real broker (no client) -> not possible.
    class _Mockish:
        pass

    c = Allocator(_live_config(), registry=_REGISTRY_SENTINEL, broker=_Mockish())
    assert c._real_orders_possible() is False
