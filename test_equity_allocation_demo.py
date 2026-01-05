"""Demo script to test equity-based allocation with simulated broker."""

from decimal import Decimal

from src.app import allocation
from src.app.allocator import Allocator
from src.app.config import Config
from src.app.ledger import Ledger
from src.app.strategies.base import PositionIntent
from src.app.strategy_registry import StrategyRegistry


class MockBrokerWithEquity:
    """Mock broker that provides account equity for testing."""

    def __init__(self, equity: float):
        self.equity = equity

    class MockAccount:
        def __init__(self, equity: float):
            self.equity = str(equity)

    class MockClient:
        def __init__(self, equity: float):
            self._equity = equity

        def get_account(self):
            return MockBrokerWithEquity.MockAccount(self._equity)

    def __init__(self, equity: float):
        self.client = self.MockClient(equity)


def test_equity_allocation():
    """Test equity-based allocation with registry and mock broker."""

    print("=" * 80)
    print("TESTING EQUITY-BASED ALLOCATION")
    print("=" * 80)
    print()

    # 1. Initialize registry (loads from config/strategies.yaml)
    print("1. Loading strategy registry...")
    registry = StrategyRegistry()
    state = registry.get_state()
    print(f"   Loaded {len(state.strategies)} strategies")

    enabled = registry.get_enabled_strategies()
    print(f"   Enabled strategies: {[s.strategy_id for s in enabled]}")
    print()

    # 2. Create mock broker with equity
    equity_amount = 50000.0
    print(f"2. Creating mock broker with ${equity_amount:,.2f} equity...")
    broker = MockBrokerWithEquity(equity_amount)
    print()

    # 3. Create test intents from strategies
    print("3. Creating test intents...")
    strategy_intents = {
        "Trend_MA20": [
            PositionIntent("AAPL", 10, 0.85, "Strong uptrend"),
            PositionIntent("SPY", 5, 0.75, "Bullish momentum"),
        ],
        "MeanRev_Z1.0": [
            PositionIntent("AAPL", -3, 0.60, "Overbought correction"),
            PositionIntent("GOOGL", 8, 0.70, "Oversold bounce"),
        ],
    }

    for strategy_name, intents in strategy_intents.items():
        print(f"   {strategy_name}:")
        for intent in intents:
            print(
                f"     - {intent.symbol}: {intent.target_quantity} shares (conviction={intent.conviction})"
            )
    print()

    # 4. Create current prices
    current_prices = {
        "AAPL": Decimal("150.00"),
        "SPY": Decimal("400.00"),
        "GOOGL": Decimal("140.00"),
    }
    print("4. Market prices:")
    for symbol, price in current_prices.items():
        print(f"   {symbol}: ${price}")
    print()

    # 5. Create config and ledger
    config = Config(
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_trading_base_url="",
        alpaca_data_base_url="",
        allowed_symbols=["AAPL", "SPY", "GOOGL"],
        max_order_notional=10000,
        max_positions_notional=10000,
        max_daily_loss=1000,
        timeframe="1h",
    )
    ledger = Ledger()

    # 6. Run allocation
    print("5. Running allocation...")
    print("-" * 80)
    allocator = Allocator(config, registry=registry, broker=broker, ledger=ledger)
    result = allocator.allocate(strategy_intents, current_prices)
    print()

    # 7. Display results
    print("=" * 80)
    print("ALLOCATION RESULTS")
    print("=" * 80)
    print()

    if result.equity_used:
        print("[SUCCESS] EQUITY-BASED ALLOCATION MODE")
        print(f"Account Equity: ${result.equity_used:,.2f}")
        print()
    else:
        print("[WARNING] LEGACY ALLOCATION MODE (fallback)")
        print()

    if result.weight_summary:
        ws = result.weight_summary
        print(f"Enabled Strategies: {ws['enabled_ids']}")
        print(f"Sum of configured weights: {ws['sum_enabled_weights']:.3f}")
        print()
        print("Weight Normalization:")
        print(f"  {'Strategy':<20} {'Configured':>12} {'Normalized':>12}")
        print("  " + "-" * 46)
        for strategy_id in ws["enabled_ids"]:
            configured = ws["configured_weights"][strategy_id]
            normalized = ws["normalized_weights"][strategy_id]
            print(f"  {strategy_id:<20} {configured:>12.3f} {normalized:>12.3f}")
        print()

    print("Strategy Budgets:")
    print(f"  {'Strategy':<20} {'Budget':>15}")
    print("  " + "-" * 37)
    for strategy_name, budget in result.strategy_budgets.items():
        print(f"  {strategy_name:<20} ${budget:>14,.2f}")
    print()

    print("Target Positions (after netting):")
    print(f"  {'Symbol':<10} {'Quantity':>10}")
    print("  " + "-" * 22)
    if result.target_positions:
        for symbol, qty in result.target_positions.items():
            print(f"  {symbol:<10} {qty:>10}")
    else:
        print("  (none)")
    print()

    if result.warnings:
        print("⚠ Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
        print()

    # 8. Show netting explanation
    print("=" * 80)
    print("NETTING EXPLANATION")
    print("=" * 80)
    print()
    print("Multi-strategy intents for AAPL:")
    print("  Trend_MA20:    +10 shares @ $150 = +$1,500 notional")
    print("  MeanRev_Z1.0:   -3 shares @ $150 = -$450 notional")
    print("  Net:            +7 shares @ $150 = +$1,050 notional")
    print()
    print("[OK] Netting combines conflicting strategies into single position!")
    print()

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_equity_allocation()
