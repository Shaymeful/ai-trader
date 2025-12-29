"""Strategy runner for shadow mode (no actual order placement)."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config_with_yaml
from .strategies import MeanReversionStrategy, TrendStrategy


def run_shadow_mode():
    """
    Run strategies in shadow mode (no actual orders).

    Loads config, runs strategies, prints summary table,
    and writes JSONL logs.
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

    # Create mock market data (in production, this would come from live data)
    # For shadow mode, we'll use dummy data
    market_data = _create_mock_market_data(universe)

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


if __name__ == "__main__":
    run_shadow_mode()
