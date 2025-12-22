"""Main entry point for the trading bot."""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from src.app.config import is_live_trading_mode, load_config
from src.app.models import FillRecord, OrderRecord, TradeRecord
from src.app.order_pipeline import submit_signal_order
from src.app.state import load_state, save_state
from src.broker import AlpacaBroker, MockBroker
from src.data import AlpacaDataProvider, MockDataProvider
from src.risk import RiskManager
from src.signals import SMAStrategy, is_market_hours
from src.signals.strategy import calculate_sma


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
        type=int,
        default=None,
        help="Maximum number of trading loop iterations (default: 5)",
    )

    parser.add_argument(
        "--i-understand-live-trading",
        action="store_true",
        help="Acknowledge understanding of live trading risks (required for --mode live)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the trading bot CLI.

    Args:
        argv: Command line arguments (for testing)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args(argv)

    # Safety gate: require explicit acknowledgment for live trading
    if args.mode == "live" and not args.i_understand_live_trading:
        print(
            "ERROR: Live trading mode requires explicit acknowledgment.\n"
            "Use --i-understand-live-trading to proceed with live trading.\n"
            "WARNING: Live trading involves real money and real risk.",
            file=sys.stderr,
        )
        return 1

    # Parse symbols if provided
    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    # Call the trading loop with parsed arguments
    try:
        run_trading_loop(
            mode=args.mode,
            run_id=args.run_id,
            symbols=symbols,
            max_iterations=args.max_iterations,
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
    """
    # Extract CLI overrides
    mode_override = kwargs.get("mode")
    run_id_override = kwargs.get("run_id")
    symbols_override = kwargs.get("symbols")
    max_iterations = kwargs.get("max_iterations")

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

                # Process each symbol
                for symbol in config.allowed_symbols:
                    if symbol not in bars_data:
                        logger.warning(f"No data for {symbol}")
                        continue

                    bars = bars_data[symbol]
                    if not bars:
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
                        logger.info("    Signal: HOLD (market closed)")
                        continue
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
                        logger.info("    Signal: HOLD (insufficient data)")
                        continue
                    else:
                        logger.info(f"    SMA Fast ({config.sma_fast_period}): ${fast_sma:.2f}")
                        logger.info(f"    SMA Slow ({config.sma_slow_period}): ${slow_sma:.2f}")

                    # Check if we have a position
                    has_position = symbol in risk_manager.positions
                    logger.info(f"    Current position: {'YES' if has_position else 'NO'}")

                    # Generate signal
                    signal = strategy.generate_signals(symbol, bars, has_position)

                    if signal:
                        logger.info(f"    Signal: {signal.side.value.upper()}")
                        logger.info(f"    Reason: {signal.reason}")

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

                        if result.success and result.order is not None and not config.dry_run:
                            trades_executed += 1

                            # Update last processed timestamp
                            state.last_processed_timestamp[symbol] = current_time.isoformat()

                            # Save state after each order
                            save_state(state)
                    else:
                        logger.info("    Signal: HOLD (no crossover detected)")

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
