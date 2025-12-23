"""Main entry point for the trading bot."""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.app.config import is_live_trading_mode, load_config
from src.app.models import FillRecord, OrderRecord, TradeRecord
from src.app.order_pipeline import submit_signal_order
from src.app.reconciliation import reconcile_with_broker
from src.app.state import load_state, save_state
from src.broker import AlpacaBroker, MockBroker
from src.data import AlpacaDataProvider, MockDataProvider
from src.risk import RiskManager
from src.signals import SMAStrategy, is_market_hours
from src.signals.strategy import calculate_sma

# Load .env file from repo root BEFORE any config/env checks
# This ensures environment variables are available for both --preflight and normal execution
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_PATH = _REPO_ROOT / ".env"
load_dotenv(dotenv_path=_DOTENV_PATH, override=False)


def get_run_output_dir(run_id: str) -> Path:
    """
    Get the output directory for a specific run.

    Creates directory structure: out/runs/<run_id>/
    All run-scoped artifacts (CSV files, logs, summary) go here.

    Args:
        run_id: Unique run identifier

    Returns:
        Path to the run's output directory
    """
    run_dir = Path("out") / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def close_logging_handlers():
    """
    Close and remove all logging handlers to release file locks.

    This is critical on Windows where open file handles prevent file deletion.
    Flushes all handlers, closes them, and removes them from all loggers.
    """
    # Get all loggers
    loggers_to_clean = [logging.getLogger()]  # Root logger
    loggers_to_clean.extend([logging.getLogger(name) for name in logging.root.manager.loggerDict])

    # Close and remove handlers from each logger
    for logger in loggers_to_clean:
        handlers = logger.handlers[:]  # Copy list to avoid modification during iteration
        for handler in handlers:
            try:
                handler.flush()
                handler.close()
                logger.removeHandler(handler)
            except Exception as e:
                # Log to stderr if we can't use logging
                print(f"Warning: Error closing handler {handler}: {e}", file=sys.stderr)

    # Finally, call logging.shutdown() as a final cleanup
    logging.shutdown()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        argv: Command line arguments (for testing)

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="AI Trader - Automated trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in dry-run mode (default, no real orders)
  python -m src.app

  # Run in paper trading mode (simulated Alpaca account)
  python -m src.app --mode paper

  # Run in live trading mode (requires explicit acknowledgment)
  python -m src.app --mode live --i-understand-live-trading

  # Run with custom symbols and max iterations
  python -m src.app --symbols AAPL,MSFT --max-iterations 10
""",
    )

    parser.add_argument(
        "--mode",
        choices=["dry-run", "paper", "live"],
        default="dry-run",
        help="Trading mode (default: dry-run for safety)",
    )

    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional run ID for this session (default: auto-generated UUID)",
    )

    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of symbols to trade (default: from config/env)",
    )

    parser.add_argument(
        "--max-iterations",
        "--iterations",
        type=int,
        default=None,
        help="Maximum number of trading loop iterations (default: 5)",
    )

    parser.add_argument(
        "--i-understand-live-trading",
        action="store_true",
        help="Acknowledge understanding of live trading risks (required for --mode live)",
    )

    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate configuration and connectivity without running the trading loop",
    )

    parser.add_argument(
        "--paper-test-order",
        nargs=2,
        metavar=("SYMBOL", "QTY"),
        help="Submit a single test MARKET order in paper mode and exit (e.g., --paper-test-order AAPL 1)",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly 1 trading loop iteration (default: 5 iterations)",
    )

    parser.add_argument(
        "--compute-after-hours",
        action="store_true",
        help="Fetch bars and compute indicators even when market is closed (for diagnostics)",
    )

    parser.add_argument(
        "--allow-after-hours-orders",
        action="store_true",
        help="Allow order submission when market is closed (requires --compute-after-hours, refused in live mode)",
    )

    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help="Reconcile state with broker (sync orders/positions) and exit without running trading loop",
    )

    return parser.parse_args(argv)


def run_paper_test_order(symbol: str, quantity: int) -> int:
    """
    Submit a single test MARKET order in paper mode.

    Args:
        symbol: Stock symbol to trade
        quantity: Number of shares

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import os

    print(f"Paper test order: {symbol} x {quantity}")

    # Check for API credentials
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        print(
            "ERROR: Paper test order requires Alpaca API credentials.\n"
            "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
            file=sys.stderr,
        )
        return 1

    print("  [OK] API credentials found")

    # Initialize Alpaca broker for paper trading
    try:
        broker = AlpacaBroker(api_key, secret_key, "https://paper-api.alpaca.markets")
        print("  [OK] Alpaca broker initialized (paper mode)")
    except Exception as e:
        print(f"ERROR: Failed to initialize broker: {e}", file=sys.stderr)
        return 1

    # Generate client order ID
    client_order_id = f"test-{uuid.uuid4()}"
    print(f"  Client order ID: {client_order_id}")

    # Submit order
    try:
        from src.app.models import OrderSide

        order = broker.submit_order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            client_order_id=client_order_id,
        )
        print("  [OK] Order submitted successfully!")
        print(f"  Order ID: {order.id}")
        print(f"  Status: {order.status.value}")
        print(f"  Symbol: {order.symbol}")
        print(f"  Side: {order.side.value}")
        print(f"  Quantity: {order.quantity}")
        if order.filled_price:
            print(f"  Filled Price: ${order.filled_price}")
        print("\nTest order completed successfully!")
        return 0
    except Exception as e:
        print(f"ERROR: Failed to submit order: {e}", file=sys.stderr)
        return 1


def run_preflight_check(mode: str, base_url: str | None = None) -> int:
    """
    Run preflight checks for the given mode.

    Args:
        mode: Trading mode (dry-run, paper, or live)
        base_url: Alpaca base URL (required for paper/live modes)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import os
    import urllib.request

    if mode == "dry-run":
        print("Preflight check: dry-run mode")
        print("  [OK] Dry-run/mock mode requires no Alpaca connectivity")
        print("  Status: OK")
        return 0

    # For paper/live modes, check API keys
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        print(
            f"ERROR: {mode.capitalize()} mode requires Alpaca API credentials.\n"
            "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
            file=sys.stderr,
        )
        return 1

    print(f"Preflight check: {mode} mode")
    print("  [OK] API credentials found")

    # Test connectivity to Alpaca
    print(f"  Testing connectivity to {base_url}...")

    account_url = f"{base_url}/v2/account"
    req = urllib.request.Request(account_url)
    req.add_header("APCA-API-KEY-ID", api_key)
    req.add_header("APCA-API-SECRET-KEY", secret_key)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                import json

                data = json.loads(response.read().decode("utf-8"))
                print(f"  [OK] Connection successful (HTTP {response.status})")
                print(f"  Account ID: {data.get('id', 'N/A')}")
                print(f"  Status: {data.get('status', 'N/A')}")
                print(f"  Currency: {data.get('currency', 'N/A')}")
                print(f"  Buying Power: ${data.get('buying_power', 'N/A')}")
                print("\nPreflight status: OK")
                return 0
            else:
                print(
                    f"ERROR: Unexpected response status: {response.status}",
                    file=sys.stderr,
                )
                return 1
    except urllib.error.HTTPError as e:
        print(
            f"ERROR: HTTP {e.code} - {e.reason}\nResponse: {e.read().decode('utf-8')[:200]}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed - {e.reason}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the trading bot CLI.

    Args:
        argv: Command line arguments (for testing)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args(argv)

    # Handle paper test order (must be in paper mode)
    if args.paper_test_order:
        symbol, qty_str = args.paper_test_order
        try:
            quantity = int(qty_str)
            if quantity <= 0:
                print("ERROR: Quantity must be positive", file=sys.stderr)
                return 1
        except ValueError:
            print(f"ERROR: Invalid quantity '{qty_str}', must be an integer", file=sys.stderr)
            return 1

        # Refuse to run in live mode
        if args.mode == "live":
            print(
                "ERROR: --paper-test-order cannot be used with --mode live.\n"
                "Test orders are only allowed in paper mode for safety.",
                file=sys.stderr,
            )
            return 1

        # Default to paper mode if not specified
        if args.mode == "dry-run":
            print("INFO: Switching to paper mode for test order (dry-run cannot submit orders)")
            args.mode = "paper"

        return run_paper_test_order(symbol, quantity)

    # Safety gate: require explicit acknowledgment for live trading
    if args.mode == "live" and not args.i_understand_live_trading:
        print(
            "ERROR: Live trading mode requires explicit acknowledgment.\n"
            "Use --i-understand-live-trading to proceed with live trading.\n"
            "WARNING: Live trading involves real money and real risk.",
            file=sys.stderr,
        )
        return 1

    # Safety gate: refuse after-hours orders in live mode
    if args.allow_after_hours_orders and args.mode == "live":
        print(
            "ERROR: --allow-after-hours-orders cannot be used with --mode live.\n"
            "After-hours order submission is only allowed in paper/dry-run modes for safety.",
            file=sys.stderr,
        )
        return 1

    # Validate: --allow-after-hours-orders requires --compute-after-hours
    if args.allow_after_hours_orders and not args.compute_after_hours:
        print(
            "ERROR: --allow-after-hours-orders requires --compute-after-hours.\n"
            "Use both flags together to enable after-hours diagnostics and orders.",
            file=sys.stderr,
        )
        return 1

    # If preflight mode is enabled, run preflight checks and exit
    if args.preflight:
        # Determine base URL based on mode
        if args.mode == "paper":
            base_url = "https://paper-api.alpaca.markets"
        elif args.mode == "live":
            base_url = "https://api.alpaca.markets"
        else:
            base_url = None

        return run_preflight_check(args.mode, base_url)

    # Environment preflight check: paper/live modes require Alpaca API credentials
    if args.mode in ("paper", "live"):
        import os

        if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
            print(
                f"ERROR: {args.mode.capitalize()} mode requires Alpaca API credentials.\n"
                "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
                file=sys.stderr,
            )
            return 1

    # Parse symbols if provided
    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    # Handle --once flag
    iterations = 1 if args.once else None

    # Call the trading loop with parsed arguments
    try:
        run_trading_loop(
            mode=args.mode,
            run_id=args.run_id,
            symbols=symbols,
            max_iterations=args.max_iterations or iterations,
            compute_after_hours=args.compute_after_hours,
            allow_after_hours_orders=args.allow_after_hours_orders,
            reconcile_only=args.reconcile_only,
        )
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def setup_logging(log_level: str, run_id: str) -> logging.Logger:
    """Set up logging configuration."""
    # Create log file in run-specific directory
    run_dir = get_run_output_dir(run_id)
    log_file = run_dir / "trading.log"

    # Configure logging with run_id in format
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=f"%(asctime)s - [RUN:{run_id[:8]}] - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
        force=True,  # Force reconfiguration
    )

    logger = logging.getLogger("ai-trader")
    logger.info(f"Logging initialized. Log file: {log_file}")
    logger.info(f"Run ID: {run_id}")
    return logger


def setup_outputs(run_id: str):
    """Ensure output directories exist and initialize CSV files for this run."""
    # Create global out directory and run-specific directory
    Path("out").mkdir(exist_ok=True)
    run_dir = get_run_output_dir(run_id)

    # Always create trades.csv with header in run directory
    csv_path = run_dir / "trades.csv"
    if not csv_path.exists():
        with open(csv_path, "w") as f:
            f.write(TradeRecord.csv_header() + "\n")

    # Always create orders.csv with header in run directory
    orders_path = run_dir / "orders.csv"
    if not orders_path.exists():
        with open(orders_path, "w") as f:
            f.write(OrderRecord.csv_header() + "\n")

    # Always create fills.csv with header in run directory
    fills_path = run_dir / "fills.csv"
    if not fills_path.exists():
        with open(fills_path, "w") as f:
            f.write(FillRecord.csv_header() + "\n")


def write_trade_to_csv(trade: TradeRecord, run_id: str):
    """Append trade to CSV file in run directory."""
    run_dir = get_run_output_dir(run_id)
    csv_path = run_dir / "trades.csv"

    # Append trade
    with open(csv_path, "a") as f:
        f.write(trade.to_csv_row() + "\n")


def write_order_to_csv(order: OrderRecord, run_id: str):
    """Append order to orders.csv in run directory."""
    run_dir = get_run_output_dir(run_id)
    csv_path = run_dir / "orders.csv"

    with open(csv_path, "a") as f:
        f.write(order.to_csv_row() + "\n")


def write_fill_to_csv(fill: FillRecord, run_id: str):
    """Append fill to fills.csv in run directory."""
    run_dir = get_run_output_dir(run_id)
    csv_path = run_dir / "fills.csv"

    with open(csv_path, "a") as f:
        f.write(fill.to_csv_row() + "\n")


def run_trading_loop(iterations: int = 5, **kwargs):
    """
    Run the main trading loop.

    Args:
        iterations: Number of iterations to run (for testing/demo)
        **kwargs: Additional options from CLI:
            - mode: Trading mode override (dry-run, paper, live)
            - run_id: Custom run ID (default: auto-generated)
            - symbols: List of symbols to trade (default: from config)
            - max_iterations: Maximum iterations (overrides iterations param)
            - compute_after_hours: Fetch bars and compute signals even when market closed
            - allow_after_hours_orders: Allow order submission when market closed (requires compute_after_hours)
            - reconcile_only: Reconcile state with broker and exit without running trading loop
    """
    # Extract CLI overrides
    mode_override = kwargs.get("mode")
    run_id_override = kwargs.get("run_id")
    symbols_override = kwargs.get("symbols")
    max_iterations = kwargs.get("max_iterations")
    compute_after_hours = kwargs.get("compute_after_hours", False)
    allow_after_hours_orders = kwargs.get("allow_after_hours_orders", False)
    reconcile_only = kwargs.get("reconcile_only", False)

    # Use max_iterations if provided
    if max_iterations is not None:
        iterations = max_iterations

    # Generate RUN_ID for this session
    run_id = run_id_override if run_id_override is not None else str(uuid.uuid4())

    # Load configuration
    config = load_config()

    # Apply mode override from CLI
    if mode_override is not None:
        if mode_override == "dry-run":
            config.dry_run = True
            # Keep existing mode (mock or alpaca)
        elif mode_override == "paper":
            config.mode = "alpaca"
            config.alpaca_base_url = "https://paper-api.alpaca.markets"
            config.dry_run = False
        elif mode_override == "live":
            config.mode = "alpaca"
            config.alpaca_base_url = "https://api.alpaca.markets"
            config.dry_run = False

    # Apply symbols override from CLI
    if symbols_override is not None:
        config.allowed_symbols = symbols_override

    logger = setup_logging(config.log_level, run_id)

    try:
        logger.info("=" * 60)
        logger.info("AI Trader Starting")
        logger.info("=" * 60)
        logger.info(f"Mode: {config.mode}")
        if config.dry_run:
            logger.warning("=" * 60)
            logger.warning("DRY-RUN MODE ENABLED - NO ORDERS WILL BE SUBMITTED")
            logger.warning("=" * 60)
        logger.info(f"Allowed symbols: {config.allowed_symbols}")
        logger.info(f"Max positions: {config.max_positions}")
        logger.info(f"Max order quantity: {config.max_order_quantity}")
        logger.info(f"Max daily loss: {config.max_daily_loss}")
        logger.info(f"SMA periods: fast={config.sma_fast_period}, slow={config.sma_slow_period}")

        # Ensure output directories exist
        setup_outputs(run_id)

        # Load or initialize state
        state = load_state()
        if state.run_id == "initial":
            logger.info("No previous state found, starting fresh")
            state.run_id = run_id
        else:
            logger.info(
                f"Loaded previous state with {len(state.submitted_client_order_ids)} known orders"
            )
            # Update run_id for new session
            state.run_id = run_id

        # SAFETY GATE: Check live trading requirements
        if is_live_trading_mode(config):
            if not config.enable_live_trading or not config.i_understand_live_trading_risk:
                error_msg = (
                    "Live trading disabled. Set ENABLE_LIVE_TRADING=true and "
                    "I_UNDERSTAND_LIVE_TRADING_RISK=true to proceed."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            logger.warning("=" * 60)
            logger.warning("LIVE TRADING MODE ENABLED - REAL MONEY AT RISK")
            logger.warning("=" * 60)

        # Initialize components based on mode
        if config.mode == "mock":
            logger.info("Using Mock data provider and broker (offline mode)")
            data_provider = MockDataProvider()
            broker = MockBroker()
        elif config.mode == "alpaca":
            if not config.alpaca_api_key or not config.alpaca_secret_key:
                logger.error("Alpaca mode requires ALPACA_API_KEY and ALPACA_SECRET_KEY")
                # If user explicitly requested paper/live mode, fail instead of fallback
                if mode_override in ("paper", "live"):
                    raise RuntimeError(
                        f"Cannot use {mode_override} mode: ALPACA_API_KEY and ALPACA_SECRET_KEY "
                        "environment variables are required but not set."
                    )
                logger.info("Falling back to Mock mode")
                data_provider = MockDataProvider()
                broker = MockBroker()
            else:
                logger.info("Using Alpaca data provider and broker")
                try:
                    data_provider = AlpacaDataProvider(
                        config.alpaca_api_key, config.alpaca_secret_key, config.alpaca_base_url
                    )
                    broker = AlpacaBroker(
                        config.alpaca_api_key, config.alpaca_secret_key, config.alpaca_base_url
                    )
                except NotImplementedError:
                    # If user explicitly requested paper/live mode, fail instead of fallback
                    if mode_override in ("paper", "live"):
                        raise RuntimeError(
                            f"Cannot use {mode_override} mode: alpaca-py library is required but not installed. "
                            "Install with: pip install alpaca-py"
                        ) from None
                    logger.warning("Alpaca implementation requires alpaca-py library")
                    logger.info("Falling back to Mock mode")
                    data_provider = MockDataProvider()
                    broker = MockBroker()
        else:
            logger.error(f"Unknown mode: {config.mode}")
            return

        # Initialize risk manager and strategy
        risk_manager = RiskManager(config)
        strategy = SMAStrategy(config)

        # Reconcile state with broker before starting trading loop
        logger.info("")
        logger.info("=" * 60)
        logger.info("RECONCILIATION")
        logger.info("=" * 60)
        reconciliation_result = reconcile_with_broker(config, broker, state, risk_manager)
        logger.info("=" * 60)
        logger.info("")

        # If reconcile-only mode, print summary and exit
        if reconcile_only:
            logger.info("Reconcile-only mode: Exiting without running trading loop")
            # Save state after reconciliation when in reconcile-only mode
            save_state(state)
            print("\n" + "=" * 60)
            print("RECONCILIATION SUMMARY")
            print("=" * 60)
            print(f"Broker open orders: {reconciliation_result.broker_open_orders_count}")
            print(f"Local orders added: {reconciliation_result.local_orders_added}")
            print(f"Broker positions: {reconciliation_result.broker_positions_count}")
            print(f"Positions synced: {reconciliation_result.positions_synced}")
            print(f"Positions added: {reconciliation_result.positions_added}")
            print(f"Positions removed: {reconciliation_result.positions_removed}")
            print("=" * 60)
            return

        # Trading loop
        logger.info("Starting trading loop...")
        trades_executed = 0

        for iteration in range(iterations):
            logger.info(f"\n--- Iteration {iteration + 1}/{iterations} ---")

            try:
                # Fetch market data
                bars_data = data_provider.get_latest_bars(
                    config.allowed_symbols, limit=config.sma_slow_period + 1
                )

                # Log if no data fetched at all
                if not bars_data:
                    logger.warning(
                        "No market data received for any symbol. "
                        "This may indicate API issues or market closure."
                    )
                    continue

                # Process each symbol
                for symbol in config.allowed_symbols:
                    if symbol not in bars_data:
                        logger.warning(f"No data for {symbol} - symbol may be invalid or delisted")
                        continue

                    bars = bars_data[symbol]
                    if not bars:
                        logger.warning(
                            f"{symbol}: Empty bars list returned. "
                            "Market may be closed or symbol has no recent data."
                        )
                        continue

                    latest_bar = bars[-1]
                    current_time = latest_bar.timestamp

                    # Log symbol processing start
                    logger.info(f"\n  Processing {symbol}:")
                    logger.info(
                        f"    Timestamp: {current_time.strftime('%Y-%m-%d %H:%M:%S')} ({current_time.strftime('%A')})"
                    )
                    logger.info(f"    Bars fetched: {len(bars)}")
                    logger.info(f"    Current price: ${latest_bar.close}")

                    # Check market hours
                    in_market_hours = is_market_hours(current_time, config)
                    market_open = f"{config.market_open_hour:02d}:{config.market_open_minute:02d}"
                    market_close = (
                        f"{config.market_close_hour:02d}:{config.market_close_minute:02d}"
                    )

                    if not in_market_hours:
                        logger.info(
                            f"    Market hours: CLOSED (current: {current_time.strftime('%H:%M')}, "
                            f"allowed: {market_open}-{market_close} on weekdays)"
                        )
                        if not compute_after_hours:
                            logger.info("    Signal: HOLD (market closed)")
                            continue
                        else:
                            logger.info("    Note: Computing signals after-hours for diagnostics")
                    else:
                        logger.info(
                            f"    Market hours: OPEN (allowed: {market_open}-{market_close})"
                        )

                    # Calculate and log SMAs
                    fast_sma = calculate_sma(bars, config.sma_fast_period)
                    slow_sma = calculate_sma(bars, config.sma_slow_period)

                    if fast_sma is None or slow_sma is None:
                        logger.info(
                            f"    SMA Fast ({config.sma_fast_period}): insufficient data (need {config.sma_fast_period} bars)"
                        )
                        logger.info(
                            f"    SMA Slow ({config.sma_slow_period}): insufficient data (need {config.sma_slow_period} bars)"
                        )
                        has_position = symbol in risk_manager.positions
                        logger.info(f"    Current position: {'YES' if has_position else 'NO'}")
                        logger.info("    --- Decision Summary ---")
                        logger.info("    Decision: HOLD")
                        logger.info("    SMA Signal: Insufficient data for indicator calculation")
                        logger.info(f"    Position Status: {'Long' if has_position else 'Flat'}")
                        logger.info("    Final Action: HOLD (insufficient data)")
                        continue
                    else:
                        logger.info(f"    SMA Fast ({config.sma_fast_period}): ${fast_sma:.2f}")
                        logger.info(f"    SMA Slow ({config.sma_slow_period}): ${slow_sma:.2f}")

                    # Check if we have a position
                    has_position = symbol in risk_manager.positions
                    logger.info(f"    Current position: {'YES' if has_position else 'NO'}")

                    # Generate signal
                    signal = strategy.generate_signals(symbol, bars, has_position)

                    # Log detailed decision summary
                    logger.info("    --- Decision Summary ---")
                    if signal:
                        logger.info(f"    Decision: {signal.side.value.upper()}")
                        logger.info(f"    SMA Signal: {signal.reason}")
                        logger.info(
                            f"    SMA Crossover: Fast (${fast_sma:.2f}) {'>' if fast_sma > slow_sma else '<'} Slow (${slow_sma:.2f})"
                        )
                        logger.info(f"    Position Status: {'Long' if has_position else 'Flat'}")

                        # Check if we should block after-hours order submission
                        if not in_market_hours and not allow_after_hours_orders:
                            logger.warning(
                                "    Gate BLOCKED: Market closed (after-hours orders disabled)"
                            )
                            logger.info(
                                "    Use --compute-after-hours --allow-after-hours-orders to submit orders after hours"
                            )
                            logger.info("    Final Action: HOLD (market hours gate)")
                            continue

                        if not in_market_hours and allow_after_hours_orders:
                            logger.warning(
                                "    Gate WARNING: Submitting AFTER HOURS (--allow-after-hours-orders enabled)"
                            )

                        # Determine quantity (simple fixed quantity for MVP)
                        quantity = 10

                        # Submit order through centralized pipeline
                        # This enforces ALL risk checks and idempotency before broker calls
                        result = submit_signal_order(
                            signal=signal,
                            quantity=quantity,
                            config=config,
                            broker=broker,
                            risk_manager=risk_manager,
                            state=state,
                            run_id=run_id,
                            write_order_to_csv_fn=write_order_to_csv,
                            write_fill_to_csv_fn=write_fill_to_csv,
                            write_trade_to_csv_fn=write_trade_to_csv,
                            strategy_name="SMA",
                        )

                        # Log final outcome
                        if result.success:
                            if config.dry_run:
                                logger.info(
                                    f"    Final Action: {signal.side.value.upper()} (dry-run)"
                                )
                            else:
                                logger.info(
                                    f"    Final Action: {signal.side.value.upper()} (order submitted)"
                                )
                        else:
                            logger.warning(f"    Gate BLOCKED: {result.reason}")
                            logger.info("    Final Action: HOLD (blocked by gate)")

                        if result.success and result.order is not None and not config.dry_run:
                            trades_executed += 1

                            # Update last processed timestamp
                            state.last_processed_timestamp[symbol] = current_time.isoformat()

                            # Save state after each order
                            save_state(state)
                    else:
                        logger.info("    Decision: HOLD")
                        logger.info("    SMA Signal: No crossover detected")
                        logger.info(
                            f"    SMA Crossover: Fast (${fast_sma:.2f}) {'>' if fast_sma > slow_sma else '<'} Slow (${slow_sma:.2f})"
                        )
                        logger.info(f"    Position Status: {'Long' if has_position else 'Flat'}")
                        logger.info("    Final Action: HOLD (no signal)")

            except Exception as e:
                logger.error(f"Error in trading loop iteration: {e}", exc_info=True)

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Trading session complete")
        logger.info("=" * 60)
        logger.info(f"Trades executed: {trades_executed}")
        logger.info(f"Daily PnL: ${risk_manager.get_daily_pnl():.2f}")
        logger.info(f"Open positions: {len(risk_manager.get_positions())}")

        for pos in risk_manager.get_positions():
            logger.info(
                f"  {pos.symbol}: {pos.quantity} shares @ ${pos.avg_price:.2f} "
                f"(current: ${pos.current_price:.2f}, PnL: ${pos.unrealized_pnl:.2f})"
            )

        # Count total trades in this run's CSV file
        run_dir = get_run_output_dir(run_id)
        csv_path = run_dir / "trades.csv"
        total_trades_in_file = 0
        if csv_path.exists():
            with open(csv_path) as f:
                # Count lines (subtract 1 for header)
                total_trades_in_file = len(f.readlines()) - 1

        # Write summary JSON to run directory
        summary = {
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
            "mode": config.mode,
            "session_trades_executed": trades_executed,
            "total_trades_in_file": total_trades_in_file,
            "daily_pnl": float(risk_manager.get_daily_pnl()),
            "total_orders_submitted": len(state.submitted_client_order_ids),
            "open_positions": [
                {
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_price": float(pos.avg_price),
                    "current_price": float(pos.current_price),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                }
                for pos in risk_manager.get_positions()
            ],
        }

        summary_file = run_dir / "summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"\nSummary written to {summary_file}")
        logger.info(f"Logs available in {run_dir}")

        # Report trade counts
        if csv_path.exists():
            logger.info(f"Trades executed this session: {trades_executed}")
            if total_trades_in_file > 0:
                logger.info(f"Total trades in {csv_path}: {total_trades_in_file}")
            else:
                logger.info(f"Trades file created at {csv_path} (empty)")
        else:
            logger.warning("Trades file not created (unexpected)")

        logger.info(f"Orders available in {run_dir / 'orders.csv'}")
        logger.info(f"Fills available in {run_dir / 'fills.csv'}")
        logger.info("State saved to out/state.json")

    finally:
        # Always close logging handlers to release file locks (critical on Windows)
        close_logging_handlers()


if __name__ == "__main__":
    raise SystemExit(main())
