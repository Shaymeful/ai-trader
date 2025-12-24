"""Main entry point for the trading bot."""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from src.app.config import Config, is_live_trading_mode, load_config
from src.app.models import FillRecord, OrderRecord, OrderSide, TradeRecord
from src.app.order_pipeline import submit_signal_order
from src.app.reconciliation import reconcile_with_broker
from src.app.state import load_state, save_state
from src.broker import AlpacaBroker, MockBroker
from src.data import AlpacaDataProvider, MockDataProvider
from src.risk import RiskManager
from src.signals import SMAStrategy, get_exchange_time, is_market_hours
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


def print_dry_run_preview(
    symbol: str,
    decision: str,
    qty: int | None = None,
    limit_price: Decimal | None = None,
    reason: str = "",
):
    """
    Print a concise dry-run preview row to console.

    Args:
        symbol: Trading symbol
        decision: BUY, SELL, or HOLD
        qty: Order quantity (if applicable)
        limit_price: Limit price (if applicable)
        reason: Brief reason for decision
    """
    qty_str = f"{qty:>3}" if qty else "  -"
    price_str = f"${limit_price:>7.2f}" if limit_price else "     N/A"
    reason_truncated = reason[:50] if len(reason) <= 50 else reason[:47] + "..."

    print(f"  {symbol:<6} {decision:<4} {qty_str}  {price_str}  {reason_truncated}")


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
        "--dry-run",
        action="store_true",
        help="Run full pipeline (signals + risk checks + pricing) but never submit orders. "
        "Works with any mode (mock/paper/live) without requiring credentials or safety gates.",
    )

    parser.add_argument(
        "--paper-test-order",
        nargs=2,
        metavar=("SYMBOL", "QTY"),
        help="Submit a single test MARKET order in paper mode and exit (e.g., --paper-test-order AAPL 1)",
    )

    parser.add_argument(
        "--test-order",
        action="store_true",
        help="Submit a single test LIMIT buy (1 share) for first symbol in LIVE mode and exit. "
        "Requires: --mode live, --i-understand-live-trading, and ENABLE_LIVE_TRADING=true env var. "
        "Order must pass RiskManager checks.",
    )

    # Order management commands
    parser.add_argument(
        "--list-open-orders",
        action="store_true",
        help="List all open orders and exit. Requires live mode safety gates.",
    )

    parser.add_argument(
        "--cancel-order-id",
        type=str,
        metavar="ORDER_ID",
        help="Cancel order by broker order ID and exit. Requires live mode safety gates.",
    )

    parser.add_argument(
        "--cancel-client-order-id",
        type=str,
        metavar="CLIENT_ORDER_ID",
        help="Cancel order by client order ID and exit. Requires live mode safety gates.",
    )

    parser.add_argument(
        "--replace-order-id",
        type=str,
        metavar="ORDER_ID",
        help="Replace/modify order by broker order ID. Requires --limit-price and live mode safety gates.",
    )

    parser.add_argument(
        "--limit-price",
        type=float,
        metavar="PRICE",
        help="New limit price for --replace-order-id",
    )

    parser.add_argument(
        "--qty",
        type=int,
        metavar="QUANTITY",
        help="New quantity for --replace-order-id (optional)",
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

    parser.add_argument(
        "--max-daily-loss",
        type=float,
        default=500,
        help="Maximum daily loss threshold in dollars (default: 500)",
    )

    parser.add_argument(
        "--max-order-notional",
        type=float,
        default=500,
        help="Maximum order notional value in dollars (default: 500)",
    )

    parser.add_argument(
        "--max-positions-notional",
        type=float,
        default=10000,
        help="Maximum total positions exposure in dollars (default: 10000)",
    )

    parser.add_argument(
        "--use-limit-orders",
        action="store_true",
        default=True,
        help="Use limit orders instead of market orders (default: true)",
    )

    parser.add_argument(
        "--no-limit-orders",
        action="store_false",
        dest="use_limit_orders",
        help="Disable limit orders, use market orders",
    )

    parser.add_argument(
        "--max-spread-bps",
        type=float,
        default=20,
        help="Maximum allowed spread in basis points (default: 20)",
    )

    parser.add_argument(
        "--min-edge-bps",
        type=float,
        default=0,
        help="Minimum edge required in basis points (default: 0, disabled)",
    )

    parser.add_argument(
        "--cost-diagnostics",
        action="store_true",
        default=True,
        help="Enable cost diagnostics reporting (default: true)",
    )

    parser.add_argument(
        "--no-cost-diagnostics",
        action="store_false",
        dest="cost_diagnostics",
        help="Disable cost diagnostics reporting",
    )

    parser.add_argument(
        "--min-avg-volume",
        type=int,
        default=1_000_000,
        help="Minimum average daily volume threshold (default: 1000000)",
    )

    parser.add_argument(
        "--min-price",
        type=float,
        default=2.00,
        help="Minimum price to prevent penny stocks (default: 2.00)",
    )

    parser.add_argument(
        "--max-price",
        type=float,
        default=1000.00,
        help="Maximum price sanity cap (default: 1000.00)",
    )

    parser.add_argument(
        "--require-quote",
        action="store_true",
        default=True,
        help="Require valid bid/ask quote to trade (default: true)",
    )

    parser.add_argument(
        "--no-require-quote",
        action="store_false",
        dest="require_quote",
        help="Disable quote requirement",
    )

    parser.add_argument(
        "--symbol-whitelist",
        type=str,
        default="",
        help="Comma-separated symbol whitelist (default: empty = allow all)",
    )

    parser.add_argument(
        "--symbol-blacklist",
        type=str,
        default="",
        help="Comma-separated symbol blacklist (default: empty)",
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


def run_live_test_order(config: Config, i_understand_live_trading: bool) -> int:
    """
    Submit a single test LIMIT buy order (1 share) for first symbol in LIVE mode.

    Safety gates:
    - Requires mode=live
    - Requires --i-understand-live-trading flag
    - Requires ENABLE_LIVE_TRADING=true environment variable
    - Must pass RiskManager checks

    Args:
        config: Configuration with symbols and risk parameters
        i_understand_live_trading: Whether user acknowledged live trading risks

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import os

    print("=" * 70)
    print("TEST ORDER MODE - LIVE TRADING")
    print("=" * 70)

    # Safety gate 1: Check we're using live Alpaca API (not paper or dry-run)
    # After mode override, --mode live sets alpaca_base_url to live API
    if config.alpaca_base_url != "https://api.alpaca.markets":
        print(
            f"ERROR: --test-order requires --mode live (current base URL: {config.alpaca_base_url})",
            file=sys.stderr,
        )
        return 1

    # Safety gate 2: Check --i-understand-live-trading flag
    if not i_understand_live_trading:
        print(
            "ERROR: --test-order requires --i-understand-live-trading flag.\n"
            "Live trading involves real money and real risk.",
            file=sys.stderr,
        )
        return 1

    # Safety gate 3: Check ENABLE_LIVE_TRADING environment variable
    enable_live_trading = os.getenv("ENABLE_LIVE_TRADING", "").lower()
    if enable_live_trading != "true":
        print(
            "ERROR: --test-order requires ENABLE_LIVE_TRADING=true environment variable.\n"
            f"Current value: {os.getenv('ENABLE_LIVE_TRADING', '(not set)')}",
            file=sys.stderr,
        )
        return 1

    print("  [OK] All safety gates passed")
    print("  [OK] Mode: live")
    print("  [OK] User acknowledged live trading risks")
    print("  [OK] ENABLE_LIVE_TRADING=true")

    # Get first symbol
    if not config.allowed_symbols:
        print("ERROR: No symbols configured", file=sys.stderr)
        return 1

    symbol = config.allowed_symbols[0]
    print(f"\n  Symbol: {symbol}")
    print("  Quantity: 1 share")

    # Check for API credentials
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        print(
            "ERROR: Live test order requires Alpaca API credentials.\n"
            "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
            file=sys.stderr,
        )
        return 1

    print("  [OK] API credentials found")

    # Initialize Alpaca broker for LIVE trading
    try:
        broker = AlpacaBroker(api_key, secret_key, "https://api.alpaca.markets")
        print("  [OK] Alpaca broker initialized (LIVE mode)")
    except Exception as e:
        print(f"ERROR: Failed to initialize broker: {e}", file=sys.stderr)
        return 1

    # Get current quote to determine limit price
    try:
        quote = broker.get_quote(symbol)
        print("\n  Current quote:")
        print(f"    Bid: ${quote.bid}")
        print(f"    Ask: ${quote.ask}")
        print(f"    Last: ${quote.last}")
    except Exception as e:
        print(f"ERROR: Failed to get quote for {symbol}: {e}", file=sys.stderr)
        return 1

    # Calculate limit price: bid - small offset (so it likely posts, not crosses)
    # Use bid price, or fall back to last trade if bid is unavailable
    base_price = quote.bid if quote.bid > 0 else quote.last
    if base_price <= 0:
        print(
            f"ERROR: Invalid price for {symbol}: bid={quote.bid}, last={quote.last}",
            file=sys.stderr,
        )
        return 1

    # Offset: 0.01 (1 cent) below bid to ensure we post
    limit_price = base_price - Decimal("0.01")
    print(f"  Limit price: ${limit_price} (bid - $0.01)")

    # Initialize RiskManager to validate order
    from src.risk import RiskManager

    risk_manager = RiskManager(config)
    print("\n  Validating order through RiskManager...")

    # Check order notional
    notional_check = risk_manager.check_order_notional(1, limit_price)
    if not notional_check.passed:
        print(f"ERROR: Order failed risk check: {notional_check.reason}", file=sys.stderr)
        return 1
    print("    [OK] Order notional check passed")

    # Check max positions exposure
    exposure_check = risk_manager.check_positions_exposure(
        new_order_quantity=1, new_order_price=limit_price
    )
    if not exposure_check.passed:
        print(f"ERROR: Order failed risk check: {exposure_check.reason}", file=sys.stderr)
        return 1
    print("    [OK] Positions exposure check passed")

    # Generate client order ID
    client_order_id = f"test-{uuid.uuid4()}"
    print(f"\n  Client order ID: {client_order_id}")

    # Submit LIMIT order
    try:
        from src.app.models import OrderSide, OrderType

        order = broker.submit_order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=1,
            client_order_id=client_order_id,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
        )
        print("\n" + "=" * 70)
        print("TEST ORDER SUBMITTED SUCCESSFULLY")
        print("=" * 70)
        print(f"  Order ID: {order.id}")
        print(f"  Client Order ID: {client_order_id}")
        print(f"  Status: {order.status.value}")
        print(f"  Symbol: {order.symbol}")
        print(f"  Side: {order.side.value}")
        print(f"  Type: {order.type.value}")
        print(f"  Quantity: {order.quantity}")
        print(f"  Limit Price: ${order.price}")
        if order.filled_price:
            print(f"  Filled Price: ${order.filled_price}")
        print("=" * 70)
        print("\nWARNING: This was a REAL order in LIVE mode with real money.")
        print("Monitor your Alpaca dashboard to track this order.")
        return 0
    except Exception as e:
        print(f"ERROR: Failed to submit order: {e}", file=sys.stderr)
        return 1


def _check_live_trading_safety_gates(
    config: Config, i_understand_live_trading: bool, command: str
) -> tuple[bool, str | None]:
    """
    Check if live trading safety gates are satisfied.

    Returns:
        (passes, error_message): True if gates pass, False with error message otherwise
    """
    import os

    # Only enforce safety gates for live mode
    if config.alpaca_base_url != "https://api.alpaca.markets":
        return (True, None)

    if not i_understand_live_trading:
        return (
            False,
            f"ERROR: {command} in live mode requires --i-understand-live-trading flag.\n"
            "This operation affects live trading account.",
        )

    enable_live_trading = os.getenv("ENABLE_LIVE_TRADING", "").lower()
    if enable_live_trading != "true":
        return (
            False,
            f"ERROR: {command} in live mode requires ENABLE_LIVE_TRADING=true environment variable.\n"
            f"Current value: {os.getenv('ENABLE_LIVE_TRADING', '(not set)')}",
        )

    return (True, None)


def run_list_open_orders(config: Config, i_understand_live_trading: bool) -> int:
    """
    List all open orders and exit.

    Supports all trading modes:
    - mock/dry-run: Uses MockBroker (no network, no credentials required)
    - paper: Uses Alpaca paper endpoint (requires API keys)
    - live: Uses Alpaca live endpoint (requires API keys + safety flags)

    Args:
        config: Configuration with broker settings
        i_understand_live_trading: Whether user acknowledged live trading risks

    Returns:
        Exit code: 0=success, 1=user error, 2=network/broker error
    """
    import os

    # Determine mode - check mock first
    is_mock = config.mode in ("mock", "dry-run")
    is_live = config.alpaca_base_url == "https://api.alpaca.markets" and not is_mock

    # Print header
    print("=" * 70)
    if is_mock:
        print("LIST OPEN ORDERS - MOCK MODE")
    elif is_live:
        print("LIST OPEN ORDERS - LIVE MODE")
    else:
        print("LIST OPEN ORDERS - PAPER MODE")
    print("=" * 70)

    # Safety gate checks for live mode only
    if is_live:
        passes, error_msg = _check_live_trading_safety_gates(
            config, i_understand_live_trading, "--list-open-orders"
        )
        if not passes:
            print(error_msg, file=sys.stderr)
            return 1

    # Initialize broker
    try:
        if is_mock:
            broker = MockBroker()
            print("  [OK] Using MockBroker (offline mode)")
        else:
            # Paper or live mode - need API keys
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")

            if not api_key or not secret_key:
                print(
                    "ERROR: Alpaca mode requires API credentials.\n"
                    "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
                    file=sys.stderr,
                )
                return 1

            broker = AlpacaBroker(api_key, secret_key, config.alpaca_base_url)
            print(f"  [OK] Connected to Alpaca ({'LIVE' if is_live else 'PAPER'} mode)")
    except Exception as e:
        print(f"ERROR: Failed to initialize broker: {e}", file=sys.stderr)
        return 2

    # List open orders
    try:
        orders = broker.list_open_orders_detailed()

        if not orders:
            print("\n✓ No open orders found.")
            print("=" * 70)
            return 0

        print(f"\n{'Open Orders':<40} Count: {len(orders)}")
        print("-" * 120)

        # Print table header
        print(
            f"{'Symbol':<8} {'Side':<5} {'Qty':>5} {'Type':<7} {'Limit':>10} {'Status':<10} "
            f"{'Order ID':<20} {'Client Order ID':<20}"
        )
        print("-" * 120)

        # Print each order
        for order in orders:
            limit_price = f"${order.price:.2f}" if order.price else "N/A"
            client_id = getattr(order, "client_order_id", "N/A")
            print(
                f"{order.symbol:<8} {order.side.value:<5} {order.quantity:>5} {order.type.value:<7} "
                f"{limit_price:>10} {order.status.value:<10} {order.id:<20} {client_id:<20}"
            )

        print("-" * 120)
        print("=" * 70)
        return 0
    except Exception as e:
        print(f"ERROR: Failed to list orders: {e}", file=sys.stderr)
        return 2


def run_cancel_order(
    config: Config,
    i_understand_live_trading: bool,
    order_id: str | None,
    client_order_id: str | None,
) -> int:
    """
    Cancel an order by ID and exit.

    Supports all trading modes:
    - mock/dry-run: Uses MockBroker (no network, no credentials required)
    - paper: Uses Alpaca paper endpoint (requires API keys)
    - live: Uses Alpaca live endpoint (requires API keys + safety flags)

    Args:
        config: Configuration with broker settings
        i_understand_live_trading: Whether user acknowledged live trading risks
        order_id: Broker order ID to cancel (if provided)
        client_order_id: Client order ID to cancel (if provided)

    Returns:
        Exit code: 0=success, 1=user error, 2=network/broker error
    """
    import os

    # Validate inputs
    if not order_id and not client_order_id:
        print("ERROR: No order ID provided", file=sys.stderr)
        return 1

    # Determine mode - check mock first
    is_mock = config.mode in ("mock", "dry-run")
    is_live = config.alpaca_base_url == "https://api.alpaca.markets" and not is_mock

    # Print header
    print("=" * 70)
    if is_mock:
        print("CANCEL ORDER - MOCK MODE")
    elif is_live:
        print("CANCEL ORDER - LIVE MODE")
    else:
        print("CANCEL ORDER - PAPER MODE")
    print("=" * 70)

    # Safety gate checks for live mode only
    if is_live:
        passes, error_msg = _check_live_trading_safety_gates(
            config, i_understand_live_trading, "--cancel-order"
        )
        if not passes:
            print(error_msg, file=sys.stderr)
            return 1

    # Initialize broker
    try:
        if is_mock:
            broker = MockBroker()
            print("  [OK] Using MockBroker (offline mode)")
        else:
            # Paper or live mode - need API keys
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")

            if not api_key or not secret_key:
                print(
                    "ERROR: Alpaca mode requires API credentials.\n"
                    "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
                    file=sys.stderr,
                )
                return 1

            broker = AlpacaBroker(api_key, secret_key, config.alpaca_base_url)
            print(f"  [OK] Connected to Alpaca ({'LIVE' if is_live else 'PAPER'} mode)")
    except Exception as e:
        print(f"ERROR: Failed to initialize broker: {e}", file=sys.stderr)
        return 2

    # Cancel order
    try:
        if order_id:
            print(f"\nCanceling order by ID: {order_id}")
            success = broker.cancel_order(order_id)
        else:
            print(f"\nCanceling order by client ID: {client_order_id}")
            success = broker.cancel_order_by_client_id(client_order_id)

        if success:
            print("\n" + "=" * 70)
            print("✓ ORDER CANCELED SUCCESSFULLY")
            print("=" * 70)

            # Verify cancellation (only for broker order IDs)
            if order_id:
                try:
                    status = broker.get_order_status(order_id)
                    print(f"  Verified status: {status.status.value}")
                except Exception:
                    print("  Note: Could not verify final status")

            print("=" * 70)
            return 0
        else:
            print(
                "\nERROR: Failed to cancel order (order may not exist or already filled)",
                file=sys.stderr,
            )
            return 2
    except Exception as e:
        print(f"\nERROR: Failed to cancel order: {e}", file=sys.stderr)
        return 2


def run_replace_order(
    config: Config,
    i_understand_live_trading: bool,
    order_id: str,
    limit_price: float,
    quantity: int | None,
) -> int:
    """
    Replace/modify an order and exit.

    Supports all trading modes:
    - mock/dry-run: Uses MockBroker (no network, no credentials required)
    - paper: Uses Alpaca paper endpoint (requires API keys)
    - live: Uses Alpaca live endpoint (requires API keys + safety flags)

    All modes validate replacement through RiskManager.

    Args:
        config: Configuration with broker settings and risk parameters
        i_understand_live_trading: Whether user acknowledged live trading risks
        order_id: Broker order ID to replace
        limit_price: New limit price
        quantity: New quantity (optional)

    Returns:
        Exit code: 0=success, 1=user error, 2=network/broker error
    """
    import os

    # Determine mode - check mock first
    is_mock = config.mode in ("mock", "dry-run")
    is_live = config.alpaca_base_url == "https://api.alpaca.markets" and not is_mock

    # Print header
    print("=" * 70)
    if is_mock:
        print("REPLACE ORDER - MOCK MODE")
    elif is_live:
        print("REPLACE ORDER - LIVE MODE")
    else:
        print("REPLACE ORDER - PAPER MODE")
    print("=" * 70)

    # Safety gate checks for live mode only
    if is_live:
        passes, error_msg = _check_live_trading_safety_gates(
            config, i_understand_live_trading, "--replace-order"
        )
        if not passes:
            print(error_msg, file=sys.stderr)
            return 1

    # Initialize broker
    try:
        if is_mock:
            broker = MockBroker()
            print("  [OK] Using MockBroker (offline mode)")
        else:
            # Paper or live mode - need API keys
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")

            if not api_key or not secret_key:
                print(
                    "ERROR: Alpaca mode requires API credentials.\n"
                    "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.",
                    file=sys.stderr,
                )
                return 1

            broker = AlpacaBroker(api_key, secret_key, config.alpaca_base_url)
            print(f"  [OK] Connected to Alpaca ({'LIVE' if is_live else 'PAPER'} mode)")
    except Exception as e:
        print(f"ERROR: Failed to initialize broker: {e}", file=sys.stderr)
        return 2

    # Get existing order details for risk check
    try:
        existing_order = broker.get_order_status(order_id)
        print(f"\nReplacing order: {order_id}")
        print(
            f"  Current: {existing_order.symbol} {existing_order.side.value} "
            f"{existing_order.quantity} @ ${existing_order.price}"
        )
        print(f"  New: limit_price=${limit_price}" + (f", quantity={quantity}" if quantity else ""))
    except Exception as e:
        print(f"ERROR: Could not fetch existing order: {e}", file=sys.stderr)
        return 2

    # Risk check: validate new order parameters
    from src.risk import RiskManager

    risk_manager = RiskManager(config)
    limit_price_decimal = Decimal(str(limit_price))
    check_quantity = quantity if quantity is not None else existing_order.quantity

    print("\n  Validating replacement through RiskManager...")

    # Check order notional
    notional_check = risk_manager.check_order_notional(check_quantity, limit_price_decimal)
    if not notional_check.passed:
        print(f"ERROR: Replacement failed risk check: {notional_check.reason}", file=sys.stderr)
        return 1
    print("    [OK] Order notional check passed")

    # Check max positions exposure
    exposure_check = risk_manager.check_positions_exposure(
        new_order_quantity=check_quantity, new_order_price=limit_price_decimal
    )
    if not exposure_check.passed:
        print(f"ERROR: Replacement failed risk check: {exposure_check.reason}", file=sys.stderr)
        return 1
    print("    [OK] Positions exposure check passed")

    # Replace order
    try:
        new_order = broker.replace_order(order_id, limit_price_decimal, quantity)

        print("\n" + "=" * 70)
        print("✓ ORDER REPLACED SUCCESSFULLY")
        print("=" * 70)
        print(f"  New Order ID: {new_order.id}")
        print(f"  Status: {new_order.status.value}")
        print(f"  Symbol: {new_order.symbol}")
        print(f"  Side: {new_order.side.value}")
        print(f"  Quantity: {new_order.quantity}")
        print(f"  Limit Price: ${new_order.price}")
        print("=" * 70)

        if is_live:
            print("\nWARNING: This replacement was executed in LIVE mode with real money.")
            print("Monitor your Alpaca dashboard to track this order.")

        return 0
    except Exception as e:
        print(f"ERROR: Failed to replace order: {e}", file=sys.stderr)
        return 2


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

    # Handle live test order
    if args.test_order:
        # Load config to get symbols and risk parameters
        try:
            config = load_config()

            # Apply mode override from CLI (same pattern as run_trading_loop)
            if args.mode == "dry-run":
                config.dry_run = True
                # Keep existing mode (mock or alpaca)
            elif args.mode == "paper":
                config.mode = "alpaca"
                config.alpaca_base_url = "https://paper-api.alpaca.markets"
                config.dry_run = False
            elif args.mode == "live":
                config.mode = "alpaca"
                config.alpaca_base_url = "https://api.alpaca.markets"
                config.dry_run = False

            # Apply symbols override from CLI
            if args.symbols:
                config.allowed_symbols = [s.strip() for s in args.symbols.split(",")]

            # Apply risk limit overrides from CLI
            if args.max_daily_loss is not None:
                config.max_daily_loss = Decimal(str(args.max_daily_loss))
            if args.max_order_notional is not None:
                config.max_order_notional = Decimal(str(args.max_order_notional))
            if args.max_positions_notional is not None:
                config.max_positions_notional = Decimal(str(args.max_positions_notional))

            # Apply cost control overrides from CLI
            if args.use_limit_orders is not None:
                config.use_limit_orders = args.use_limit_orders
            if args.max_spread_bps is not None:
                config.max_spread_bps = Decimal(str(args.max_spread_bps))
            if args.min_edge_bps is not None:
                config.min_edge_bps = Decimal(str(args.min_edge_bps))
            if args.cost_diagnostics is not None:
                config.cost_diagnostics = args.cost_diagnostics

            # Apply symbol eligibility overrides from CLI
            if args.min_avg_volume is not None:
                config.min_avg_volume = args.min_avg_volume
            if args.min_price is not None:
                config.min_price = Decimal(str(args.min_price))
            if args.max_price is not None:
                config.max_price = Decimal(str(args.max_price))
            if args.require_quote is not None:
                config.require_quote = args.require_quote
            if args.symbol_whitelist:
                config.symbol_whitelist = (
                    [s.strip() for s in args.symbol_whitelist.split(",") if s.strip()]
                    if args.symbol_whitelist
                    else []
                )
            if args.symbol_blacklist:
                config.symbol_blacklist = (
                    [s.strip() for s in args.symbol_blacklist.split(",") if s.strip()]
                    if args.symbol_blacklist
                    else []
                )
        except Exception as e:
            print(f"ERROR: Failed to load config: {e}", file=sys.stderr)
            return 1

        return run_live_test_order(config, args.i_understand_live_trading)

    # Handle order management commands
    if (
        args.list_open_orders
        or args.cancel_order_id
        or args.cancel_client_order_id
        or args.replace_order_id
    ):
        # Load config and apply mode overrides (same pattern as test-order)
        try:
            config = load_config()

            # Apply mode override from CLI
            if args.mode == "dry-run":
                config.dry_run = True
            elif args.mode == "paper":
                config.mode = "alpaca"
                config.alpaca_base_url = "https://paper-api.alpaca.markets"
                config.dry_run = False
            elif args.mode == "live":
                config.mode = "alpaca"
                config.alpaca_base_url = "https://api.alpaca.markets"
                config.dry_run = False

            # Apply CLI overrides for risk parameters (needed for replace)
            if args.max_daily_loss is not None:
                config.max_daily_loss = Decimal(str(args.max_daily_loss))
            if args.max_order_notional is not None:
                config.max_order_notional = Decimal(str(args.max_order_notional))
            if args.max_positions_notional is not None:
                config.max_positions_notional = Decimal(str(args.max_positions_notional))
        except Exception as e:
            print(f"ERROR: Failed to load config: {e}", file=sys.stderr)
            return 1

        # Handle list open orders
        if args.list_open_orders:
            return run_list_open_orders(config, args.i_understand_live_trading)

        # Handle cancel order
        if args.cancel_order_id or args.cancel_client_order_id:
            return run_cancel_order(
                config,
                args.i_understand_live_trading,
                args.cancel_order_id,
                args.cancel_client_order_id,
            )

        # Handle replace order
        if args.replace_order_id:
            if args.limit_price is None:
                print("ERROR: --replace-order-id requires --limit-price", file=sys.stderr)
                return 1
            return run_replace_order(
                config,
                args.i_understand_live_trading,
                args.replace_order_id,
                args.limit_price,
                args.qty,
            )

    # Safety gate: require explicit acknowledgment for live trading
    # Exception: Skip safety check when --dry-run is set (no orders will be submitted)
    if args.mode == "live" and not args.i_understand_live_trading and not args.dry_run:
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
    # Exception: Skip credential check when --dry-run is set (no orders will be submitted)
    if args.mode in ("paper", "live") and not args.dry_run:
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
            dry_run=args.dry_run,
            max_daily_loss=args.max_daily_loss,
            max_order_notional=args.max_order_notional,
            max_positions_notional=args.max_positions_notional,
            use_limit_orders=args.use_limit_orders,
            max_spread_bps=args.max_spread_bps,
            min_edge_bps=args.min_edge_bps,
            cost_diagnostics=args.cost_diagnostics,
            min_avg_volume=args.min_avg_volume,
            min_price=args.min_price,
            max_price=args.max_price,
            require_quote=args.require_quote,
            symbol_whitelist=args.symbol_whitelist,
            symbol_blacklist=args.symbol_blacklist,
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


def generate_cost_diagnostics(run_id: str):
    """
    Generate cost diagnostics report from fills.csv.

    Reads fills.csv and calculates:
    - Total trades
    - Total spread cost (sum of spread_bps for all trades)
    - Total slippage (sum of abs(slippage_bps))
    - Average spread_bps
    - Worst slippage_bps (by absolute value)

    Writes report to cost_report.txt in run directory.

    Args:
        run_id: Current run ID
    """
    from decimal import Decimal

    run_dir = get_run_output_dir(run_id)
    fills_path = run_dir / "fills.csv"

    # Check if fills.csv exists and has data
    if not fills_path.exists():
        return

    # Read fills and extract cost metrics
    fills_data = []
    with open(fills_path) as f:
        lines = f.readlines()
        if len(lines) <= 1:  # Only header or empty
            return

        # Parse CSV (skip header)
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 12:  # Has cost tracking fields
                try:
                    # Extract cost fields: slippage_bps and spread_bps_at_submit
                    slippage_bps = Decimal(parts[10]) if parts[10] else None
                    spread_bps = Decimal(parts[11]) if parts[11] else None

                    if slippage_bps is not None and spread_bps is not None:
                        fills_data.append(
                            {
                                "slippage_bps": slippage_bps,
                                "spread_bps": spread_bps,
                            }
                        )
                except (ValueError, IndexError):
                    # Skip malformed lines
                    continue

    # If no fills with cost data, skip report
    if not fills_data:
        return

    # Calculate metrics
    total_trades = len(fills_data)
    total_spread_cost = sum(f["spread_bps"] for f in fills_data)
    total_slippage = sum(abs(f["slippage_bps"]) for f in fills_data)
    avg_spread_bps = total_spread_cost / Decimal(total_trades)

    # Find worst slippage (by absolute value)
    worst_slippage = max(fills_data, key=lambda f: abs(f["slippage_bps"]))["slippage_bps"]

    # Write report
    report_path = run_dir / "cost_report.txt"
    with open(report_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("TRADING COST DIAGNOSTICS\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Run ID: {run_id}\n")
        f.write(f"Total Trades: {total_trades}\n\n")
        f.write("Cost Metrics:\n")
        f.write(f"  Total Spread Cost:    {total_spread_cost:>10.2f} bps\n")
        f.write(f"  Total Slippage:       {total_slippage:>10.2f} bps (absolute)\n")
        f.write(f"  Average Spread:       {avg_spread_bps:>10.2f} bps\n")
        f.write(f"  Worst Slippage:       {worst_slippage:>10.2f} bps\n")
        f.write("\n" + "=" * 60 + "\n")

    return report_path


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
            - max_daily_loss: Maximum daily loss threshold
            - max_order_notional: Maximum order notional value
            - max_positions_notional: Maximum total positions exposure
            - use_limit_orders: Use limit orders instead of market orders
            - max_spread_bps: Maximum allowed spread in basis points
            - min_edge_bps: Minimum edge required in basis points
            - cost_diagnostics: Enable cost diagnostics reporting
    """
    # Extract CLI overrides
    mode_override = kwargs.get("mode")
    run_id_override = kwargs.get("run_id")
    symbols_override = kwargs.get("symbols")
    max_iterations = kwargs.get("max_iterations")
    compute_after_hours = kwargs.get("compute_after_hours", False)
    allow_after_hours_orders = kwargs.get("allow_after_hours_orders", False)
    reconcile_only = kwargs.get("reconcile_only", False)
    dry_run_override = kwargs.get("dry_run", False)
    max_daily_loss_override = kwargs.get("max_daily_loss")
    max_order_notional_override = kwargs.get("max_order_notional")
    max_positions_notional_override = kwargs.get("max_positions_notional")
    use_limit_orders_override = kwargs.get("use_limit_orders")
    max_spread_bps_override = kwargs.get("max_spread_bps")
    min_edge_bps_override = kwargs.get("min_edge_bps")
    cost_diagnostics_override = kwargs.get("cost_diagnostics")
    min_avg_volume_override = kwargs.get("min_avg_volume")
    min_price_override = kwargs.get("min_price")
    max_price_override = kwargs.get("max_price")
    require_quote_override = kwargs.get("require_quote")
    symbol_whitelist_override = kwargs.get("symbol_whitelist")
    symbol_blacklist_override = kwargs.get("symbol_blacklist")

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

    # Apply dry-run override from CLI flag (overrides mode setting)
    # This allows --dry-run to work with any mode (mock, paper, live)
    if dry_run_override:
        config.dry_run = True

    # Apply symbols override from CLI
    if symbols_override is not None:
        config.allowed_symbols = symbols_override

    # Apply risk limit overrides from CLI
    if max_daily_loss_override is not None:
        from decimal import Decimal

        config.max_daily_loss = Decimal(str(max_daily_loss_override))
    if max_order_notional_override is not None:
        from decimal import Decimal

        config.max_order_notional = Decimal(str(max_order_notional_override))
    if max_positions_notional_override is not None:
        from decimal import Decimal

        config.max_positions_notional = Decimal(str(max_positions_notional_override))

    # Apply cost control overrides from CLI
    if use_limit_orders_override is not None:
        config.use_limit_orders = use_limit_orders_override
    if max_spread_bps_override is not None:
        from decimal import Decimal

        config.max_spread_bps = Decimal(str(max_spread_bps_override))
    if min_edge_bps_override is not None:
        from decimal import Decimal

        config.min_edge_bps = Decimal(str(min_edge_bps_override))
    if cost_diagnostics_override is not None:
        config.cost_diagnostics = cost_diagnostics_override

    # Apply symbol eligibility overrides from CLI
    if min_avg_volume_override is not None:
        config.min_avg_volume = min_avg_volume_override
    if min_price_override is not None:
        from decimal import Decimal

        config.min_price = Decimal(str(min_price_override))
    if max_price_override is not None:
        from decimal import Decimal

        config.max_price = Decimal(str(max_price_override))
    if require_quote_override is not None:
        config.require_quote = require_quote_override
    if symbol_whitelist_override is not None:
        # Parse comma-separated string to list
        config.symbol_whitelist = (
            [s.strip() for s in symbol_whitelist_override.split(",") if s.strip()]
            if symbol_whitelist_override
            else []
        )
    if symbol_blacklist_override is not None:
        # Parse comma-separated string to list
        config.symbol_blacklist = (
            [s.strip() for s in symbol_blacklist_override.split(",") if s.strip()]
            if symbol_blacklist_override
            else []
        )

    # FAIL-FAST SAFETY GATE: Check live trading requirements before ANY operations
    # This prevents any file I/O, logging, or API calls if safety flags are missing
    # EXCEPTION: Skip safety gates when dry_run is True (no orders will be submitted)
    if (
        not config.dry_run
        and is_live_trading_mode(config)
        and (not config.enable_live_trading or not config.i_understand_live_trading_risk)
    ):
        error_msg = (
            "Live trading disabled. Set ENABLE_LIVE_TRADING=true and "
            "I_UNDERSTAND_LIVE_TRADING_RISK=true to proceed."
        )
        # Raise immediately without setting up logging or state
        raise ValueError(error_msg)

    logger = setup_logging(config.log_level, run_id)

    try:
        logger.info("=" * 60)
        logger.info("AI Trader Starting")
        logger.info("=" * 60)
        logger.info(f"Mode: {config.mode}")
        if config.dry_run:
            # Print banner to console for visibility
            print("\n" + "=" * 70)
            print("DRY RUN — NO ORDERS SUBMITTED")
            print("=" * 70 + "\n")
            logger.warning("=" * 60)
            logger.warning("DRY-RUN MODE ENABLED - NO ORDERS WILL BE SUBMITTED")
            logger.warning("=" * 60)
        logger.info(f"Allowed symbols: {config.allowed_symbols}")
        logger.info(f"Max positions: {config.max_positions}")
        logger.info(f"Max order quantity: {config.max_order_quantity}")
        logger.info(f"Max daily loss: ${config.max_daily_loss}")
        logger.info(f"Max order notional: ${config.max_order_notional}")
        logger.info(f"Max positions notional: ${config.max_positions_notional}")
        logger.info(f"SMA periods: fast={config.sma_fast_period}, slow={config.sma_slow_period}")
        logger.info(f"Use limit orders: {config.use_limit_orders}")
        logger.info(f"Max spread (bps): {config.max_spread_bps}")
        logger.info(f"Min edge (bps): {config.min_edge_bps}")
        logger.info(f"Cost diagnostics: {config.cost_diagnostics}")
        logger.info(f"Min avg volume: {config.min_avg_volume:,}")
        logger.info(f"Min price: ${config.min_price}")
        logger.info(f"Max price: ${config.max_price}")
        logger.info(f"Require quote: {config.require_quote}")
        if config.symbol_whitelist:
            logger.info(f"Symbol whitelist: {','.join(config.symbol_whitelist)}")
        if config.symbol_blacklist:
            logger.info(f"Symbol blacklist: {','.join(config.symbol_blacklist)}")

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

        # Log live trading warning (safety gate already passed)
        if is_live_trading_mode(config):
            logger.warning("=" * 60)
            logger.warning("LIVE TRADING MODE ENABLED - REAL MONEY AT RISK")
            logger.warning("=" * 60)

        # Initialize components based on mode
        # In dry-run mode, always use MockBroker (no credentials needed)
        if config.dry_run:
            logger.info("Dry-run mode: Using Mock broker (no orders will be submitted)")
            broker = MockBroker()
            # Still use real data provider for accurate signals
            if config.mode == "alpaca" and config.alpaca_api_key and config.alpaca_secret_key:
                logger.info("Using Alpaca data provider for market data")
                try:
                    data_provider = AlpacaDataProvider(
                        config.alpaca_api_key, config.alpaca_secret_key, config.alpaca_base_url
                    )
                except NotImplementedError:
                    logger.warning("Alpaca implementation requires alpaca-py library")
                    logger.info("Falling back to Mock data provider")
                    data_provider = MockDataProvider()
            else:
                logger.info("Using Mock data provider")
                data_provider = MockDataProvider()
        elif config.mode == "mock":
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
        from src.app.state import get_daily_realized_pnl

        daily_pnl = get_daily_realized_pnl(state)
        logger.info(f"Today's realized PnL: ${daily_pnl}")
        risk_manager = RiskManager(config, daily_realized_pnl=daily_pnl)
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

        # Print preview header for dry-run mode
        if config.dry_run:
            print("\nPREVIEW:")
            print("  " + "-" * 80)
            print(f"  {'Symbol':<6} {'Act':<4} {'Qty':>3}  {'Price':>9}  {'Reason':<50}")
            print("  " + "-" * 80)

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

                    # Get actual exchange time (not bar timestamp)
                    exchange_time = get_exchange_time()
                    bar_timestamp = latest_bar.timestamp

                    # Log symbol processing start
                    logger.info(f"\n  Processing {symbol}:")
                    logger.info(f"    Bar timestamp: {bar_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                    logger.info(
                        f"    Exchange time: {exchange_time.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                        f"({exchange_time.strftime('%A')})"
                    )
                    logger.info(f"    Bars fetched: {len(bars)}")
                    logger.info(f"    Current price: ${latest_bar.close}")

                    # Check market hours using actual exchange time
                    in_market_hours = is_market_hours(config)
                    market_open = f"{config.market_open_hour:02d}:{config.market_open_minute:02d}"
                    market_close = (
                        f"{config.market_close_hour:02d}:{config.market_close_minute:02d}"
                    )

                    if not in_market_hours:
                        logger.info(
                            f"    Market hours: CLOSED (exchange time: {exchange_time.strftime('%H:%M %Z')}, "
                            f"trading hours: {market_open}-{market_close} on weekdays)"
                        )
                        if not compute_after_hours:
                            logger.info("    Signal: HOLD (market closed)")
                            if config.dry_run:
                                print_dry_run_preview(symbol, "HOLD", reason="Market closed")
                            continue
                        else:
                            logger.info("    Note: Computing signals after-hours for diagnostics")
                    else:
                        logger.info(
                            f"    Market hours: OPEN (exchange time: {exchange_time.strftime('%H:%M %Z')}, "
                            f"trading hours: {market_open}-{market_close})"
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
                        if config.dry_run:
                            print_dry_run_preview(symbol, "HOLD", reason="Insufficient data")
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
                            if config.dry_run:
                                print_dry_run_preview(symbol, "HOLD", reason="Market hours gate")
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
                            data_provider=data_provider,
                            strategy_name="SMA",
                        )

                        # Log final outcome
                        if result.success:
                            if config.dry_run:
                                logger.info(
                                    f"    Final Action: {signal.side.value.upper()} (dry-run)"
                                )
                                # Get limit price from order pipeline for preview
                                # Try to get quote for price display
                                try:
                                    quote = broker.get_quote(symbol)
                                    if config.use_limit_orders:
                                        quarter_spread = quote.spread / Decimal("4")
                                        if signal.side == OrderSide.BUY:
                                            limit_price = min(quote.ask, quote.mid + quarter_spread)
                                        else:
                                            limit_price = max(quote.bid, quote.mid - quarter_spread)
                                    else:
                                        limit_price = quote.mid
                                except Exception:
                                    limit_price = signal.price

                                print_dry_run_preview(
                                    symbol,
                                    signal.side.value.upper(),
                                    qty=quantity,
                                    limit_price=limit_price,
                                    reason=signal.reason,
                                )
                            else:
                                logger.info(
                                    f"    Final Action: {signal.side.value.upper()} (order submitted)"
                                )
                        else:
                            logger.warning(f"    Gate BLOCKED: {result.reason}")
                            logger.info("    Final Action: HOLD (blocked by gate)")
                            if config.dry_run:
                                print_dry_run_preview(symbol, "HOLD", reason=result.reason[:50])

                        if result.success and result.order is not None and not config.dry_run:
                            trades_executed += 1

                            # Update last processed timestamp
                            state.last_processed_timestamp[symbol] = exchange_time.isoformat()

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
                        if config.dry_run:
                            print_dry_run_preview(symbol, "HOLD", reason="No crossover")

            except Exception as e:
                logger.error(f"Error in trading loop iteration: {e}", exc_info=True)

        # Close preview table for dry-run mode
        if config.dry_run:
            print("  " + "-" * 80 + "\n")

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

        # Generate cost diagnostics report (if enabled and trades executed)
        if config.cost_diagnostics and total_trades_in_file > 0:
            cost_report_path = generate_cost_diagnostics(run_id)
            if cost_report_path:
                logger.info(f"\nCost diagnostics report: {cost_report_path}")

    finally:
        # Always close logging handlers to release file locks (critical on Windows)
        close_logging_handlers()


if __name__ == "__main__":
    raise SystemExit(main())
