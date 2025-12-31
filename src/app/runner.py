"""Strategy runner for shadow mode (no actual order placement) and paper execution."""

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
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


@dataclass
class RunResult:
    """Result of a single run (shadow or paper mode)."""

    mode: str  # "shadow" or "paper"
    dry_run: bool
    orders_placed: int
    orders_skipped: int
    strategy_weights: dict[str, float]  # strategy_name -> weight
    timestamp: str  # ISO format


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

        # Store intents for allocator and shadow PnL
        strategy_intents[strategy.name] = intents

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

    # ============================================================================
    # Shadow PnL Performance Tracking
    # ============================================================================

    from .allocator import Allocator
    from .shadow_pnl import ShadowPnLCalculator
    from .state import (
        initialize_strategy_states,
        load_strategy_state,
        print_strategy_state_summary,
        save_strategy_state,
        update_strategy_weights,
    )

    # Extract current prices for allocator
    current_prices = {symbol: Decimal(str(data["price"])) for symbol, data in market_data.items()}

    # Run allocator to get strategy budgets
    allocator = Allocator(config)
    allocation_result = allocator.allocate(strategy_intents, current_prices)

    print("Capital Allocation")
    print("-" * 80)
    print(f"Total capital: ${config.max_positions_notional}")
    for strategy_name, budget in allocation_result.strategy_budgets.items():
        print(f"  {strategy_name}: ${budget:.2f}")
    print()

    # Load strategy states
    strategy_states = load_strategy_state()
    strategy_states = initialize_strategy_states(
        strategy_states, [s.name for s in strategies]
    )

    # Create shadow PnL calculator
    calculator = ShadowPnLCalculator(min_samples=config.performance_min_samples)

    # Compute notional exposures
    strategy_notionals = calculator.compute_strategy_notional_exposure(
        strategy_intents, allocation_result.strategy_budgets, current_prices
    )

    # Compute returns
    symbol_returns = calculator.compute_symbol_returns(market_data, universe)

    # Update performance (only if returns available)
    if symbol_returns:
        calculator.update_strategy_performance(
            strategy_states, strategy_notionals, symbol_returns
        )

        # Update weights (only if all strategies have >= min_samples)
        strategy_states = update_strategy_weights(
            strategy_states, min_samples=config.performance_min_samples
        )

        # Save state
        save_strategy_state(strategy_states)

        # Print summary
        print_strategy_state_summary(strategy_states, config.performance_min_samples)
    else:
        # First run: no previous prices, just save initialized state
        save_strategy_state(strategy_states)
        print()
        print("=" * 80)
        print("Shadow PnL: First run (no previous prices)")
        print("Performance tracking will begin on next run.")
        print("=" * 80)

    # ============================================================================
    # End Shadow PnL Performance Tracking
    # ============================================================================

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

    # Return execution result
    return RunResult(
        mode="shadow",
        dry_run=False,
        orders_placed=0,
        orders_skipped=0,
        strategy_weights={name: state.weight for name, state in strategy_states.items()},
        timestamp=datetime.now(UTC).isoformat(),
    )


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

    # ============================================================================
    # Shadow PnL Performance Tracking (for dry-run mode)
    # ============================================================================

    if dry_run:
        from .shadow_pnl import ShadowPnLCalculator
        from .state import (
            initialize_strategy_states,
            load_strategy_state,
            print_strategy_state_summary,
            save_strategy_state,
            update_strategy_weights,
        )

        # Load strategy states
        strategy_states = load_strategy_state()
        strategy_states = initialize_strategy_states(
            strategy_states, [s.name for s in strategies]
        )

        # Create shadow PnL calculator
        calculator = ShadowPnLCalculator(min_samples=config.performance_min_samples)

        # Compute notional exposures
        strategy_notionals = calculator.compute_strategy_notional_exposure(
            strategy_intents, allocation_result.strategy_budgets, current_prices
        )

        # Compute returns
        symbol_returns = calculator.compute_symbol_returns(market_data, universe)

        # Update performance (only if returns available)
        if symbol_returns:
            calculator.update_strategy_performance(
                strategy_states, strategy_notionals, symbol_returns
            )

            # Update weights (only if all strategies have >= min_samples)
            strategy_states = update_strategy_weights(
                strategy_states, min_samples=config.performance_min_samples
            )

            # Save state
            save_strategy_state(strategy_states)

            # Print summary
            print()
            print_strategy_state_summary(strategy_states, config.performance_min_samples)
            print()
            print("Note: No fills occurred. Performance tracking uses mark-to-market returns.")
            print()
        else:
            # First run: no previous prices, just save initialized state
            save_strategy_state(strategy_states)
            print()
            print("=" * 80)
            print("Shadow PnL: First run (no previous prices)")
            print("Performance tracking will begin on next run.")
            print("=" * 80)
            print()

    # ============================================================================
    # End Shadow PnL Performance Tracking
    # ============================================================================

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

    # Return execution result
    if dry_run:
        # Dry-run mode: get strategy weights
        strategy_weights = {name: state.weight for name, state in strategy_states.items()}
    else:
        # Paper mode: no strategy weights tracked without dry-run
        strategy_weights = {}

    return RunResult(
        mode="paper",
        dry_run=dry_run,
        orders_placed=len(execution_result.orders_placed),
        orders_skipped=len(execution_result.orders_skipped),
        strategy_weights=strategy_weights,
        timestamp=datetime.now(UTC).isoformat(),
    )


def run_loop(mode: str, dry_run: bool, sleep_seconds: int):
    """
    Run in loop mode: execute strategy runner repeatedly with sleep intervals.

    Catches exceptions and logs errors to logs/loop_errors.log.
    Writes status summaries to logs/loop_status.log.

    Args:
        mode: "shadow" or "paper"
        dry_run: Whether to run paper mode in dry-run
        sleep_seconds: Seconds to sleep between iterations
    """
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    status_log = log_dir / "loop_status.log"
    error_log = log_dir / "loop_errors.log"

    print("=" * 80)
    print("LOOP MODE ENABLED")
    print("=" * 80)
    print(f"Mode: {mode}")
    print(f"Dry-run: {dry_run}")
    print(f"Sleep interval: {sleep_seconds} seconds ({sleep_seconds / 3600:.1f} hours)")
    print(f"Status log: {status_log}")
    print(f"Error log: {error_log}")
    print("Press Ctrl+C to stop")
    print("=" * 80)
    print()

    iteration = 0
    while True:
        iteration += 1
        run_timestamp = datetime.now(UTC).isoformat()

        print(f"\n{'='*80}")
        print(f"LOOP ITERATION {iteration} - {run_timestamp}")
        print(f"{'='*80}\n")

        try:
            # Run the appropriate mode
            if mode == "shadow":
                result = run_shadow_mode()
            elif mode == "paper":
                result = run_paper_mode(dry_run=dry_run)
            else:
                raise ValueError(f"Invalid mode: {mode}")

            # Log successful run to status log
            weights_str = ", ".join(
                f"{name}={weight:.2%}" for name, weight in result.strategy_weights.items()
            )
            status_line = (
                f"[{run_timestamp}] SUCCESS | "
                f"mode={result.mode} | "
                f"dry_run={result.dry_run} | "
                f"orders_placed={result.orders_placed} | "
                f"orders_skipped={result.orders_skipped} | "
                f"weights=[{weights_str}]\n"
            )

            with open(status_log, "a") as f:
                f.write(status_line)

            print(f"\n{'='*80}")
            print(f"ITERATION {iteration} COMPLETE")
            print(f"Status logged to: {status_log}")
            print(f"{'='*80}\n")

        except Exception as e:
            # Log error to error log
            error_timestamp = datetime.now(UTC).isoformat()
            error_msg = (
                f"\n{'='*80}\n"
                f"ERROR at {error_timestamp} (iteration {iteration})\n"
                f"{'='*80}\n"
                f"{traceback.format_exc()}\n"
            )

            with open(error_log, "a") as f:
                f.write(error_msg)

            # Also log to status log
            status_line = (
                f"[{run_timestamp}] ERROR | "
                f"mode={mode} | "
                f"dry_run={dry_run} | "
                f"exception={type(e).__name__}: {str(e)}\n"
            )

            with open(status_log, "a") as f:
                f.write(status_line)

            print(f"\n{'='*80}")
            print(f"ERROR IN ITERATION {iteration}")
            print(f"Exception: {type(e).__name__}: {str(e)}")
            print(f"Error logged to: {error_log}")
            print(f"Continuing to next iteration...")
            print(f"{'='*80}\n")

        # Sleep before next iteration
        print(f"Sleeping for {sleep_seconds} seconds ({sleep_seconds / 3600:.1f} hours)...")
        print(f"Next run at: {datetime.now(UTC).replace(microsecond=0) + __import__('datetime').timedelta(seconds=sleep_seconds)}")
        print()

        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print("\n\nKeyboard interrupt received. Shutting down loop mode...")
            print(f"Total iterations completed: {iteration}")
            sys.exit(0)


def _single_instance_guard(name: str) -> bool:
    """
    Enforce single instance using Windows named mutex.

    This prevents duplicate concurrent executions when started by Task Scheduler.
    Windows-only (os.name == "nt"), fail-safe (returns True if mutex fails).

    Args:
        name: Mutex name (e.g., "Global\\AI_TRADER__PAPER_DRYRUN_LOOP")

    Returns:
        True if this is the only instance, False if another instance exists
    """
    if os.name != "nt":
        # Not Windows - skip mutex guard
        return True

    try:
        import ctypes
        from ctypes import wintypes

        # Windows API constants
        ERROR_ALREADY_EXISTS = 183

        # CreateMutexW signature: HANDLE CreateMutexW(
        #   LPSECURITY_ATTRIBUTES lpMutexAttributes,
        #   BOOL                  bInitialOwner,
        #   LPCWSTR               lpName
        # )
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,  # lpMutexAttributes
            wintypes.BOOL,  # bInitialOwner
            wintypes.LPCWSTR,  # lpName
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        # Create or open mutex
        mutex_handle = kernel32.CreateMutexW(None, True, name)

        if not mutex_handle:
            # Mutex creation failed - fail-safe: allow execution
            print(f"WARNING: Failed to create mutex '{name}'. Continuing anyway.")
            return True

        # Check if mutex already existed
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            # Another instance is running
            return False

        # Successfully acquired mutex - hold it for life of process
        # (Windows will release on process exit)
        return True

    except Exception as e:
        # Fail-safe: if mutex logic fails, allow execution
        print(f"WARNING: Exception in single-instance guard: {e}. Continuing anyway.")
        return True


def main():
    """Main entry point with argument parsing."""
    # CRITICAL: Single-instance guard BEFORE argument parsing
    # Prevents duplicate concurrent executions (e.g., from Task Scheduler)
    mutex_name = "Global\\AI_TRADER__PAPER_DRYRUN_LOOP"
    if not _single_instance_guard(mutex_name):
        print("=" * 80)
        print("SINGLE INSTANCE GUARD: Another instance is already running")
        print("=" * 80)
        print(f"Mutex name: {mutex_name}")
        print("Exiting to prevent duplicate execution.")
        print()
        print("If you believe this is an error, check for other python processes")
        print("running 'src.app.runner' and terminate them before retrying.")
        print("=" * 80)
        sys.exit(0)

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

    # Loop control flags
    loop_group = parser.add_mutually_exclusive_group()
    loop_group.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Run once and exit (default behavior)",
    )
    loop_group.add_argument(
        "--loop",
        action="store_true",
        help="Run in loop mode (repeats every --sleep-seconds)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=3600,
        help="Seconds to sleep between loop iterations (default: 3600 = 1 hour)",
    )

    args = parser.parse_args()

    if args.mode == "shadow":
        if args.dry_run:
            print(
                "WARNING: --dry-run flag has no effect in shadow mode (shadow mode never places orders)"
            )
            print()

    # Run in loop or once
    if args.loop:
        run_loop(mode=args.mode, dry_run=args.dry_run, sleep_seconds=args.sleep_seconds)
    else:
        # Default: run once
        if args.mode == "shadow":
            run_shadow_mode()
        elif args.mode == "paper":
            run_paper_mode(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
