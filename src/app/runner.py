"""Strategy runner for shadow mode (no actual order placement) and paper execution."""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from src.broker import AlpacaBroker, MockBroker

from .allocator import Allocator
from .config import load_config_with_yaml, validate_alpaca_credentials
from .data_providers import MarketDataProvider
from .data_providers.hourly_provider import HourlyMarketDataProvider, MockMarketDataProvider
from .execution import AlpacaExecutor
from .strategies import MeanReversionStrategy, TrendStrategy


def run_shadow_mode(provider: MarketDataProvider | None = None):
    """
    Run strategies in shadow mode (no actual orders).

    Loads config, runs strategies, prints summary table,
    and writes JSONL logs.

    Args:
        provider: Optional market data provider. If None, creates an Alpaca
                  provider using credentials from config/environment.
    """
    # Load configuration from YAML + env
    config = load_config_with_yaml()

    print("=" * 80)
    print("SHADOW MODE: Strategy Runner (No Orders)")
    print("=" * 80)
    print(f"Timeframe: {config.timeframe}")
    print(f"Universe: {', '.join(config.universe_symbols or config.allowed_symbols)}")
    print(f"Max Order USD: ${config.max_order_notional}")
    print(f"Max Daily Loss USD: ${config.max_daily_loss}")
    print(f"Max Gross Exposure USD: ${config.max_positions_notional}")
    print()

    # Use universe from YAML if available, otherwise fall back to allowed_symbols
    universe = config.universe_symbols if config.universe_symbols else config.allowed_symbols

    if not universe:
        print("ERROR: No symbols in universe. Check config/config.yaml or ALLOWED_SYMBOLS env var.")
        sys.exit(1)

    # Create market data provider if not injected
    if provider is None:
        # Check if credentials are available
        if config.alpaca_api_key and config.alpaca_secret_key:
            print(f"Using Alpaca hourly data provider (base_url: {config.alpaca_base_url})")
            provider = HourlyMarketDataProvider(
                api_key=config.alpaca_api_key,
                secret_key=config.alpaca_secret_key,
                lookback_bars=50,
                ma_period=20,
            )
        else:
            print("WARNING: No Alpaca credentials found. Using mock data provider.")
            print("Set ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY to use real data.")
            provider = MockMarketDataProvider()
    print()

    # Fetch market data
    print("Fetching market data...")
    market_data = provider.get_market_data(universe)

    # Check for symbols with insufficient data
    missing_symbols = [s for s in universe if s not in market_data]
    if missing_symbols:
        print(
            f"WARNING: No data available for {len(missing_symbols)} symbols: {', '.join(missing_symbols)}"
        )
        print("These symbols will be skipped in strategy generation.")
        print()

    # Initialize strategies
    strategies = [
        TrendStrategy(ma_period=20),
        MeanReversionStrategy(zscore_threshold=1.0),
    ]

    # Run each strategy and collect intents
    all_results = []

    print("Running strategies...")
    print()

    for strategy in strategies:
        intents = strategy.generate_intents(universe, market_data)

        print(f"Strategy: {strategy.name}")
        print("-" * 80)

        if not intents:
            print("  No intents generated")
        else:
            # Print summary table
            print(f"  {'Symbol':<8} {'Target Qty':>10} {'Conviction':>10} {'Reason':<40}")
            print("  " + "-" * 78)
            for intent in intents:
                print(
                    f"  {intent.symbol:<8} {intent.target_quantity:>10} "
                    f"{intent.conviction:>10.2f} {intent.reason:<40}"
                )

        print()

        # Collect results for JSONL logging
        for intent in intents:
            all_results.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "strategy": strategy.name,
                    "symbol": intent.symbol,
                    "target_quantity": intent.target_quantity,
                    "conviction": intent.conviction,
                    "reason": intent.reason,
                    "market_price": market_data.get(intent.symbol, {}).get("price"),
                }
            )

    # Write JSONL log
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"shadow_run_{timestamp}.jsonl"

    with open(log_file, "w") as f:
        for result in all_results:
            f.write(json.dumps(result) + "\n")

    print(f"Results logged to: {log_file}")
    print()
    print("=" * 80)
    print("Shadow mode run complete. No orders were placed.")
    print("=" * 80)


def _create_mock_market_data(universe: list[str]) -> dict:
    """
    Create mock market data for testing.

    In production, this would fetch real market data from a data provider.

    Args:
        universe: List of symbols

    Returns:
        Dictionary of symbol -> data
    """
    import random

    random.seed(42)  # Reproducible for testing

    mock_data = {}
    for symbol in universe:
        base_price = random.uniform(50, 500)
        ma = base_price * random.uniform(0.95, 1.05)
        zscore = random.uniform(-2.0, 2.0)

        mock_data[symbol] = {
            "price": round(base_price, 2),
            "ma": round(ma, 2),
            "zscore": round(zscore, 2),
        }

    return mock_data


def run_paper_mode(provider: MarketDataProvider | None = None, dry_run: bool = False):
    """
    Run strategies in paper execution mode (places orders to Alpaca paper).

    Loads config, runs strategies, allocates capital, reconciles positions,
    and executes orders (or dry-run).

    Args:
        provider: Optional market data provider. If None, creates an Alpaca
                  provider using credentials from config/environment.
        dry_run: If True, print orders without placing them
    """
    # Load configuration from YAML + env
    config = load_config_with_yaml()

    print("=" * 80)
    print(f"PAPER MODE: Strategy Runner {'(DRY-RUN)' if dry_run else '(LIVE ORDERS)'}")
    print("=" * 80)
    print(f"Timeframe: {config.timeframe}")
    print(f"Universe: {', '.join(config.universe_symbols or config.allowed_symbols)}")
    print(f"Max Order USD: ${config.max_order_notional}")
    print(f"Max Daily Loss USD: ${config.max_daily_loss}")
    print(f"Max Gross Exposure USD: ${config.max_positions_notional}")
    print(f"Dry-run: {dry_run}")
    print()

    # Validate Alpaca credentials for paper mode
    if not dry_run:
        valid, error_msg = validate_alpaca_credentials("paper", require_credentials=True)
        if not valid:
            print(error_msg)
            sys.exit(1)

    # Use universe from YAML if available, otherwise fall back to allowed_symbols
    universe = config.universe_symbols if config.universe_symbols else config.allowed_symbols

    if not universe:
        print("ERROR: No symbols in universe. Check config/config.yaml or ALLOWED_SYMBOLS env var.")
        sys.exit(1)

    # Create market data provider if not injected
    if provider is None:
        # Check if credentials are available
        if config.alpaca_api_key and config.alpaca_secret_key:
            print(f"Using Alpaca hourly data provider (base_url: {config.alpaca_base_url})")
            provider = HourlyMarketDataProvider(
                api_key=config.alpaca_api_key,
                secret_key=config.alpaca_secret_key,
                lookback_bars=50,
                ma_period=20,
            )
        else:
            print("WARNING: No Alpaca credentials found. Using mock data provider.")
            print("Set ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY to use real data.")
            provider = MockMarketDataProvider()
    print()

    # Create broker
    if dry_run or not config.alpaca_api_key:
        print("Using MockBroker (dry-run or no credentials)")
        broker = MockBroker()
    else:
        print(f"Using AlpacaBroker (paper trading at {config.alpaca_base_url})")
        broker = AlpacaBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=config.alpaca_base_url,
        )
    print()

    # Fetch market data
    print("Fetching market data...")
    market_data = provider.get_market_data(universe)

    # Check for symbols with insufficient data
    missing_symbols = [s for s in universe if s not in market_data]
    if missing_symbols:
        print(
            f"WARNING: No data available for {len(missing_symbols)} symbols: {', '.join(missing_symbols)}"
        )
        print("These symbols will be skipped in strategy generation.")
        print()

    # Extract prices for allocator
    current_prices = {symbol: Decimal(str(data["price"])) for symbol, data in market_data.items()}

    # Initialize strategies
    strategies = [
        TrendStrategy(ma_period=20),
        MeanReversionStrategy(zscore_threshold=1.0),
    ]

    # Run each strategy and collect intents
    strategy_intents = {}

    print("Running strategies...")
    print()

    for strategy in strategies:
        intents = strategy.generate_intents(universe, market_data)

        print(f"Strategy: {strategy.name}")
        print("-" * 80)

        if not intents:
            print("  No intents generated")
        else:
            # Print summary table
            print(f"  {'Symbol':<8} {'Target Qty':>10} {'Conviction':>10} {'Reason':<40}")
            print("  " + "-" * 78)
            for intent in intents:
                print(
                    f"  {intent.symbol:<8} {intent.target_quantity:>10} "
                    f"{intent.conviction:>10.2f} {intent.reason:<40}"
                )

        print()
        strategy_intents[strategy.name] = intents

    # Allocate capital across strategies
    print("Allocating capital across strategies...")
    allocator = Allocator(config)
    allocation_result = allocator.allocate(strategy_intents, current_prices)

    print(f"Target positions: {allocation_result.target_positions}")
    print(f"Strategy budgets: {allocation_result.strategy_budgets}")
    if allocation_result.warnings:
        print("Allocation warnings:")
        for warning in allocation_result.warnings:
            print(f"  - {warning}")
    print()

    # Execute orders
    print("Executing orders...")
    executor = AlpacaExecutor(broker, config, dry_run=dry_run)
    execution_result = executor.reconcile_and_execute(
        allocation_result.target_positions,
        current_prices,
    )

    # Print summary
    print()
    print("=" * 80)
    print(f"Execution Summary {'(DRY-RUN)' if dry_run else ''}")
    print("=" * 80)
    print(f"Orders placed: {len(execution_result.orders_placed)}")
    print(f"Orders skipped: {len(execution_result.orders_skipped)}")
    print(f"Total risk used: ${execution_result.total_risk_used:.2f}")
    print()

    if execution_result.orders_skipped:
        print("Skipped orders:")
        for symbol, reason in execution_result.orders_skipped:
            print(f"  {symbol}: {reason}")
        print()

    # Write JSONL log
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    mode_str = "paper_dryrun" if dry_run else "paper"
    log_file = log_dir / f"{mode_str}_run_{timestamp}.jsonl"

    log_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "paper",
        "dry_run": dry_run,
        "strategy_intents": {
            name: [
                {
                    "symbol": i.symbol,
                    "target_quantity": i.target_quantity,
                    "conviction": i.conviction,
                    "reason": i.reason,
                }
                for i in intents
            ]
            for name, intents in strategy_intents.items()
        },
        "allocation": {
            "target_positions": allocation_result.target_positions,
            "strategy_budgets": {
                k: float(v) for k, v in allocation_result.strategy_budgets.items()
            },
            "warnings": allocation_result.warnings,
        },
        "execution": {
            "orders_placed": execution_result.orders_placed,
            "orders_skipped": [
                {"symbol": s, "reason": r} for s, r in execution_result.orders_skipped
            ],
            "total_risk_used": float(execution_result.total_risk_used),
        },
    }

    with open(log_file, "w") as f:
        f.write(json.dumps(log_data) + "\n")

    print(f"Results logged to: {log_file}")
    print("=" * 80)


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(description="AI Trader Strategy Runner")
    parser.add_argument(
        "--mode",
        choices=["shadow", "paper"],
        default="shadow",
        help="Execution mode: shadow (no orders) or paper (place orders)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode: print orders without placing them (only for paper mode)",
    )

    args = parser.parse_args()

    if args.mode == "shadow":
        if args.dry_run:
            print(
                "WARNING: --dry-run flag has no effect in shadow mode (shadow mode never places orders)"
            )
            print()
        run_shadow_mode()
    elif args.mode == "paper":
        run_paper_mode(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
