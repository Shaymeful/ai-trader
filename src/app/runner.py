"""Strategy runner for shadow mode (no actual order placement) and paper execution."""

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

# CRITICAL: pywin32 is REQUIRED for Windows single-instance guard on Windows
# On non-Windows platforms, these imports will fail but that's okay
try:
    import pywintypes
    import win32api
    import win32event
except ImportError as e:
    if os.name == "nt":
        # Windows requires pywin32 for single-instance guard
        raise ImportError(
            "pywin32 is required on Windows for single-instance protection.\n"
            "Install with: pip install pywin32\n"
            "IMPORTANT: Use the virtual environment Python interpreter:\n"
            f"  Current interpreter: {sys.executable}\n"
            "  Expected: .venv\\Scripts\\python.exe"
        ) from e
    # Non-Windows: silently ignore - platform guards in functions will handle it
    pass

from src.broker import AlpacaBroker, MockBroker

from .allocator import Allocator
from .candidates.store import get_tradeable_candidates, load_candidates
from .config import load_config_with_yaml, validate_alpaca_credentials
from .data_providers import MarketDataProvider
from .data_providers.hourly_provider import HourlyMarketDataProvider, MockMarketDataProvider
from .decision_logger import DecisionLogger, TradingDecision, create_decision_from_intent
from .execution import AlpacaExecutor
from .exit_advisor import ExitAdvisor
from .ledger import CandidateLoadedEvent, Ledger, StrategyIntentCreatedEvent
from .sell_scanner import SellScanner, SellSignal
from .strategies import MeanReversionStrategy, TrendStrategy
from .strategy_registry import StrategyRegistry


def get_market_time_now() -> datetime:
    """
    Get current time in America/New_York (market time).

    Used for log filenames and daily accounting to avoid UTC date rollover issues.
    Market day aligns with US/Eastern trading day, not UTC day.

    Returns:
        datetime object with America/New_York timezone
    """
    return datetime.now(ZoneInfo("America/New_York"))


def _initialize_llm_provider(config):
    """
    Initialize LLM provider for sell scanner.

    Uses same provider infrastructure as Universe Advisor.
    Returns None if initialization fails (sell scanner will use heuristics).

    Args:
        config: Trading configuration

    Returns:
        LLMProvider instance or None
    """
    try:
        from .llm.factory import create_provider

        # Use primary provider from config (openai or anthropic)
        provider_type = getattr(config, "llm_primary", "openai")

        # Get model based on provider type
        if provider_type == "openai":
            model = getattr(config, "llm_openai_model", "gpt-4o-mini")
        else:
            model = getattr(config, "llm_anthropic_model", "claude-3-5-sonnet-20241022")

        timeout = getattr(config, "llm_timeout", 30)

        llm_provider = create_provider(provider_type=provider_type, model=model, timeout=timeout)

        print(f"LLM provider initialized: {provider_type} ({model})")
        return llm_provider

    except Exception as e:
        print(f"WARNING: Failed to initialize LLM provider: {e}")
        print("Sell scanner will use heuristic-based analysis only")
        return None


def _load_recent_news_events(lookback_hours: int = 48) -> list[dict]:
    """
    Load recent RSS events from selector output for sell scanner.

    Args:
        lookback_hours: Hours to look back for news events

    Returns:
        List of recent event dicts
    """
    try:
        events_file = Path("out/selector/events.jsonl")
        if not events_file.exists():
            return []

        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        recent_events = []

        with open(events_file, encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    timestamp_str = event.get("timestamp", "")

                    # Parse timestamp and filter by recency
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        continue

                    if timestamp >= cutoff:
                        recent_events.append(event)

                except json.JSONDecodeError:
                    continue

        print(f"Loaded {len(recent_events)} recent news events (last {lookback_hours}h)")
        return recent_events

    except Exception as e:
        print(f"WARNING: Failed to load news events: {e}")
        return []


def _detect_market_regime(market_data: dict) -> str:
    """
    Simple market regime detection using SPY data.

    Args:
        market_data: Dict of symbol -> market data

    Returns:
        Regime string (bull_low_vol, bull_high_vol, bear_low_vol, bear_high_vol, unknown)
    """
    try:
        spy_data = market_data.get("SPY", {})
        price = spy_data.get("price")
        ma = spy_data.get("ma")

        if price is None or ma is None:
            return "unknown"

        # Determine trend
        trend = "bull" if price >= ma else "bear"

        # Determine volatility (using z-score as proxy)
        zscore = abs(spy_data.get("zscore", 0.0))
        vol = "high_vol" if zscore > 1.5 else "low_vol"

        return f"{trend}_{vol}"

    except Exception as e:
        print(f"WARNING: Market regime detection failed: {e}")
        return "unknown"


def _run_sell_scan(
    sell_scanner: SellScanner,
    broker,
    market_data: dict,
    news_events: list[dict],
    market_regime: str,
    decision_logger: DecisionLogger,
    dry_run: bool = False,
) -> tuple[list[SellSignal], list[dict]]:
    """
    Run sell scanner on current positions and return actionable signals.

    Args:
        sell_scanner: SellScanner instance
        broker: Broker instance for position queries
        market_data: Dict of symbol -> market data
        news_events: Recent news events
        market_regime: Current market regime
        decision_logger: DecisionLogger instance
        dry_run: Whether this is a dry-run (no actual orders)

    Returns:
        Tuple of (sell_signals, sell_orders) where sell_orders are ready to execute
    """
    try:
        # Get current positions from broker
        positions = broker.get_positions()

        if not positions:
            print("No positions to scan for sell signals")
            return [], []

        # Convert to format expected by sell scanner: {symbol: (quantity, avg_price)}
        current_positions = {}
        for symbol, position in positions.items():
            # Handle different position formats: dict, tuple (qty, price), or object
            if isinstance(position, dict):
                qty = position.get("qty", 0)
                avg_price = position.get("avg_entry_price", 0)
            elif isinstance(position, tuple):
                qty, avg_price = position
            else:
                qty = getattr(position, "qty", 0)
                avg_price = getattr(position, "avg_entry_price", 0)

            if qty > 0:  # Only include long positions
                current_positions[symbol] = (int(qty), float(avg_price))

        if not current_positions:
            print("No long positions to scan")
            return [], []

        print(f"\nScanning {len(current_positions)} positions for sell signals...")

        # Run sell scanner
        scan_result = sell_scanner.scan_positions(
            current_positions=current_positions, market_data=market_data, news_events=news_events
        )

        # Save scan result
        sell_scanner.save_scan_result(scan_result)

        # Process signals with confidence >= 0.70 (high confidence sells)
        actionable_signals = [
            signal for signal in scan_result.sell_signals if signal.confidence >= 0.70
        ]

        if not actionable_signals:
            print(
                f"No actionable sell signals (found {len(scan_result.sell_signals)} signals below 0.70 confidence)"
            )
            return scan_result.sell_signals, []

        print(f"Found {len(actionable_signals)} actionable sell signals (confidence >= 0.70)")

        # Convert signals to orders
        sell_orders = []
        for signal in actionable_signals:
            # Get current position quantity
            qty, avg_entry_price = current_positions.get(signal.symbol, (0, 0))

            if qty == 0:
                continue

            # Determine quantity to sell based on action
            if signal.action == "SELL_ALL":
                sell_qty = qty
            elif signal.action == "SELL_HALF":
                sell_qty = qty // 2
            else:
                # TIGHTEN_STOP or other actions: don't create order yet
                continue

            if sell_qty > 0:
                sell_orders.append(
                    {
                        "symbol": signal.symbol,
                        "quantity": -sell_qty,  # Negative for sell
                        "action": signal.action,
                        "reason": signal.primary_reason,
                        "confidence": signal.confidence,
                        "signal": signal,
                    }
                )

                # Log sell decision
                current_price = market_data.get(signal.symbol, {}).get("price", avg_entry_price)

                decision = TradingDecision(
                    decision_id=f"sell_{signal.symbol}_{datetime.now(UTC).isoformat()}",
                    timestamp=datetime.now(UTC).isoformat(),
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=sell_qty,
                    price=current_price,
                    confidence=signal.confidence,
                    expected_value=signal.expected_value,
                    risk_regime=signal.risk_regime,
                    strategy="SellScanner",
                    primary_reason=signal.primary_reason,
                    detailed_reasoning=signal.detailed_reasoning,
                    supporting_data={"headlines": signal.supporting_evidence},
                    invalidation_criteria=signal.invalidation_criteria,
                    position_context={
                        "quantity": qty,
                        "avg_entry_price": avg_entry_price,
                        "current_value": current_price * qty,
                        "unrealized_pnl": (current_price - avg_entry_price) * qty,
                    },
                    execution_result="DRY_RUN" if dry_run else None,
                )

                decision_logger.log_decision(decision)

        print(f"Generated {len(sell_orders)} sell orders from signals")
        return scan_result.sell_signals, sell_orders

    except Exception as e:
        print(f"ERROR: Sell scan failed: {e}")
        traceback.print_exc()
        return [], []


@dataclass
class RunResult:
    """Result of a single run (shadow or paper mode)."""

    mode: str  # "shadow" or "paper"
    dry_run: bool
    orders_placed: int
    orders_skipped: int
    strategy_weights: dict[str, float]  # strategy_name -> weight
    timestamp: str  # ISO format


def run_shadow_mode(provider: MarketDataProvider | None = None, universe_registry=None):
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

    # Initialize ledger for event tracking
    ledger = Ledger()

    # Load candidates from snapshot (if available)
    print("Loading candidates...")
    raw_candidates = load_candidates()
    tradeable_candidates = get_tradeable_candidates(
        raw_candidates,
        now=datetime.now(UTC).replace(tzinfo=None),
        min_dollar_volume=1_000_000.0,
    )

    print(f"  Loaded {len(raw_candidates)} candidates, {len(tradeable_candidates)} tradeable")

    # Emit candidate_loaded event
    if raw_candidates:
        ledger.append(
            CandidateLoadedEvent(
                count_total=len(raw_candidates),
                count_tradeable=len(tradeable_candidates),
                symbols=[c.symbol for c in tradeable_candidates],
                snapshot_path="out/selector/snapshot.json",
            )
        )

    # Build universe from candidates (if available), otherwise use registry/config
    if tradeable_candidates:
        # Use candidate symbols as universe
        universe = [c.symbol for c in tradeable_candidates]
        candidate_map = {c.symbol: c.candidate_id for c in tradeable_candidates}
        print(f"  Universe from candidates: {', '.join(universe)}")
    else:
        # Fallback to universe registry (with operator overrides) or base config
        if universe_registry is not None:
            resolution = universe_registry.resolve()
            universe = resolution.symbols
            print(f"  Universe from registry: {', '.join(universe)} ({resolution.source})")
        else:
            universe = (
                config.universe_symbols if config.universe_symbols else config.allowed_symbols
            )
            print(f"  Universe from config: {', '.join(universe)}")
        candidate_map = {}

    if not universe:
        error_msg = "ERROR: No symbols in universe. Check config/config.yaml, ALLOWED_SYMBOLS env var, or candidate snapshot."
        print(error_msg)
        raise ValueError(error_msg)

    print()

    # Create market data provider if not injected
    if provider is None:
        # Check if credentials are available
        if config.alpaca_api_key and config.alpaca_secret_key:
            print(f"Using Alpaca hourly data provider (data_url: {config.alpaca_data_base_url})")
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
        intents = strategy.generate_intents(universe, market_data, candidate_map)

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

        # Emit strategy_intent_created events and collect results for JSONL logging
        for intent in intents:
            # Emit ledger event for intent creation
            ledger.append(
                StrategyIntentCreatedEvent(
                    strategy_id=strategy.name,
                    version=1,  # TODO: Get from strategy registry when available
                    symbol=intent.symbol,
                    target_quantity=intent.target_quantity,
                    conviction=intent.conviction,
                    reason=intent.reason,
                    candidate_id=intent.candidate_id,
                )
            )

            # Collect for JSONL logging
            all_results.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "strategy": strategy.name,
                    "symbol": intent.symbol,
                    "target_quantity": intent.target_quantity,
                    "conviction": intent.conviction,
                    "reason": intent.reason,
                    "candidate_id": intent.candidate_id,
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
    strategy_states = initialize_strategy_states(strategy_states, [s.name for s in strategies])

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
        calculator.update_strategy_performance(strategy_states, strategy_notionals, symbol_returns)

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

    # Use market time (America/New_York) for log filenames to align with trading day
    # Prevents UTC date rollover causing log files with tomorrow's date
    market_time = get_market_time_now()
    timestamp = market_time.strftime("%Y%m%d_%H%M%S_ET")
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


def run_paper_mode(
    provider: MarketDataProvider | None = None,
    dry_run: bool = False,
    cancel_open_orders: bool = False,
    registry=None,
    universe_registry=None,
):
    """
    Run strategies in paper execution mode (places orders to Alpaca paper).

    Loads config, runs strategies, allocates capital, reconciles positions,
    and executes orders (or dry-run).

    Args:
        provider: Optional market data provider. If None, creates an Alpaca
                  provider using credentials from config/environment.
        dry_run: If True, print orders without placing them
        cancel_open_orders: If True, cancel all open orders before running
    """
    # Load configuration from YAML + env
    config = load_config_with_yaml()

    print("=" * 80)
    if not dry_run:
        print("WARNING: LIVE PAPER TRADING ENABLED")
        print("=" * 80)
    print(f"PAPER MODE: Strategy Runner {'(DRY-RUN)' if dry_run else '(LIVE ORDERS)'}")
    print("=" * 80)
    print(f"Timeframe: {config.timeframe}")
    print(f"Universe: {', '.join(config.universe_symbols or config.allowed_symbols)}")
    print(f"Max Order USD: ${config.max_order_notional}")
    print(f"Max Daily Loss USD: ${config.max_daily_loss}")
    print(f"Max Gross Exposure USD: ${config.max_positions_notional}")
    print(f"Dry-run: {dry_run}")
    print(f"Cancel open orders: {cancel_open_orders}")
    print()
    print("API Endpoint Configuration:")
    print(f"  Trading API: {config.alpaca_trading_base_url} (TradingClient appends /v2)")
    print(f"  Data API: {config.alpaca_data_base_url}")
    print(f"  Credentials: {'Present (masked)' if config.alpaca_api_key else 'Not configured'}")
    print()

    # Validate Alpaca credentials for paper mode
    if not dry_run:
        valid, error_msg = validate_alpaca_credentials("paper", require_credentials=True)
        if not valid:
            print(error_msg)
            raise ValueError(error_msg)

    # Initialize ledger for event tracking
    ledger = Ledger()

    # Initialize decision logger for explainability
    print("Initializing decision logger...")
    decision_logger = DecisionLogger()
    print()

    # Initialize LLM provider for sell scanner
    print("Initializing LLM provider for sell scanner...")
    llm_provider = _initialize_llm_provider(config)
    print()

    # Load candidates from snapshot (if available)
    print("Loading candidates...")
    raw_candidates = load_candidates()
    tradeable_candidates = get_tradeable_candidates(
        raw_candidates,
        now=datetime.now(UTC).replace(tzinfo=None),
        min_dollar_volume=1_000_000.0,
    )

    print(f"  Loaded {len(raw_candidates)} candidates, {len(tradeable_candidates)} tradeable")

    # Emit candidate_loaded event
    if raw_candidates:
        ledger.append(
            CandidateLoadedEvent(
                count_total=len(raw_candidates),
                count_tradeable=len(tradeable_candidates),
                symbols=[c.symbol for c in tradeable_candidates],
                snapshot_path="out/selector/snapshot.json",
            )
        )

    # Build universe from candidates (if available), otherwise use registry/config
    if tradeable_candidates:
        # Use candidate symbols as universe
        universe = [c.symbol for c in tradeable_candidates]
        candidate_map = {c.symbol: c.candidate_id for c in tradeable_candidates}
        print(f"  Universe from candidates: {', '.join(universe)}")
    else:
        # Fallback to universe registry (with operator overrides) or base config
        if universe_registry is not None:
            resolution = universe_registry.resolve()
            universe = resolution.symbols
            print(f"  Universe from registry: {', '.join(universe)} ({resolution.source})")
        else:
            universe = (
                config.universe_symbols if config.universe_symbols else config.allowed_symbols
            )
            print(f"  Universe from config: {', '.join(universe)}")
        candidate_map = {}

    if not universe:
        error_msg = "ERROR: No symbols in universe. Check config/config.yaml, ALLOWED_SYMBOLS env var, or candidate snapshot."
        print(error_msg)
        raise ValueError(error_msg)

    print()

    # Create market data provider if not injected
    if provider is None:
        # Check if credentials are available
        if config.alpaca_api_key and config.alpaca_secret_key:
            print(f"Using Alpaca hourly data provider (data_url: {config.alpaca_data_base_url})")
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
        print(f"Using AlpacaBroker (paper trading at {config.alpaca_trading_base_url})")
        broker = AlpacaBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            trading_base_url=config.alpaca_trading_base_url,
        )
    print()

    # Cancel open orders if requested
    if cancel_open_orders and not dry_run:
        print("Canceling open orders...")
        canceled_count = broker.cancel_all_open_orders()
        print(f"Canceled {canceled_count} open order(s)")
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

    # ============================================================================
    # AI-Driven Sell Scanning (GOAL B)
    # ============================================================================

    # Initialize sell scanner with LLM provider and market data provider
    print("Initializing AI sell scanner...")
    sell_scanner = SellScanner(
        config=config, llm_provider=llm_provider, market_data_provider=provider
    )
    print()

    # Load recent news events for sell scanner
    news_events = _load_recent_news_events(lookback_hours=48)

    # Detect market regime
    market_regime = _detect_market_regime(market_data)
    print(f"Market regime: {market_regime}")
    print()

    # Run sell scan on current positions (before generating buy signals)
    sell_signals, sell_orders = _run_sell_scan(
        sell_scanner=sell_scanner,
        broker=broker,
        market_data=market_data,
        news_events=news_events,
        market_regime=market_regime,
        decision_logger=decision_logger,
        dry_run=dry_run,
    )

    # ============================================================================
    # End AI-Driven Sell Scanning
    # ============================================================================

    # ============================================================================
    # Exit Advisor Integration (SELL Candidate Generation)
    # ============================================================================

    # Initialize Exit Advisor to emit SELL candidates into the candidate pipeline
    print("Initializing Exit Advisor...")
    exit_advisor = ExitAdvisor(
        sell_scanner=sell_scanner, cooldown_hours=4, output_dir=Path("out/exit_advisor")
    )
    print()

    # Get current positions for exit scanning
    try:
        positions = broker.get_positions()

        # Convert positions to format expected by exit advisor: {symbol: (quantity, avg_price)}
        current_positions = {}
        for symbol, position in positions.items():
            # Handle different position formats: dict, tuple (qty, price), or object
            if isinstance(position, dict):
                qty = position.get("qty", 0)
                avg_price = position.get("avg_entry_price", 0)
            elif isinstance(position, tuple):
                qty, avg_price = position
            else:
                qty = getattr(position, "qty", 0)
                avg_price = getattr(position, "avg_entry_price", 0)

            if qty > 0:  # Only include long positions
                current_positions[symbol] = (int(qty), float(avg_price))

        if current_positions:
            print(f"Running Exit Advisor on {len(current_positions)} positions...")

            # Scan and emit SELL candidates
            exit_candidates = exit_advisor.scan_and_emit_candidates(
                current_positions=current_positions,
                market_data=market_data,
                news_events=news_events,
                market_regime=market_regime,
            )

            print(f"Exit Advisor generated {len(exit_candidates)} SELL candidates")

            # Log exit candidates to ledger
            if exit_candidates:
                for candidate in exit_candidates:
                    ledger.append(
                        {
                            "event_type": "exit_candidate_created",
                            "candidate_id": candidate.candidate_id,
                            "symbol": candidate.symbol,
                            "action": candidate.action,
                            "confidence": candidate.confidence,
                            "reason": candidate.reason,
                            "expires_at": candidate.expires_at,
                        }
                    )
            print()
        else:
            print("No positions to scan for exit candidates")
            exit_candidates = []
            print()

    except Exception as e:
        print(f"WARNING: Exit Advisor scan failed: {e}")
        traceback.print_exc()
        exit_candidates = []
        print()

    # ============================================================================
    # End Exit Advisor Integration
    # ============================================================================

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
        intents = strategy.generate_intents(universe, market_data, candidate_map)

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

        # Emit strategy_intent_created events
        for intent in intents:
            ledger.append(
                StrategyIntentCreatedEvent(
                    strategy_id=strategy.name,
                    version=1,  # TODO: Get from strategy registry when available
                    symbol=intent.symbol,
                    target_quantity=intent.target_quantity,
                    conviction=intent.conviction,
                    reason=intent.reason,
                    candidate_id=intent.candidate_id,
                )
            )

            # Log buy decision through decision logger (GOAL C)
            if intent.target_quantity > 0:  # Only log buy intents
                current_price = current_prices.get(intent.symbol, Decimal("0"))

                decision = create_decision_from_intent(
                    intent=intent,
                    price=float(current_price),
                    risk_regime=market_regime,
                    execution_result=None,  # Will be updated after execution
                )

                # Enhance with strategy name
                decision.strategy = strategy.name

                # Log the decision
                decision_logger.log_decision(decision)

    # Allocate capital across strategies
    print("Allocating capital across strategies...")
    allocator = Allocator(config, registry=registry, broker=broker, ledger=ledger)
    allocation_result = allocator.allocate(strategy_intents, current_prices)

    # Display allocation results
    if allocation_result.equity_used is not None:
        print(f"Account equity: ${allocation_result.equity_used:,.2f}")
        print("Allocation mode: EQUITY-BASED (normalized weights)")
    else:
        print("Allocation mode: LEGACY (equal-weight)")

    if allocation_result.weight_summary:
        weight_sum = allocation_result.weight_summary
        print(f"\nStrategy weights (normalized among {len(weight_sum['enabled_ids'])} enabled):")
        for strat_id in weight_sum["enabled_ids"]:
            configured = weight_sum["configured_weights"].get(strat_id, 0)
            normalized = weight_sum["normalized_weights"].get(strat_id, 0)
            print(f"  {strat_id}: configured={configured:.3f}, normalized={normalized:.3f}")

    print("\nStrategy budgets:")
    for name, budget in allocation_result.strategy_budgets.items():
        print(f"  {name}: ${budget:,.2f}")

    print(f"\nTarget positions: {allocation_result.target_positions}")

    if allocation_result.warnings:
        print("\nAllocation warnings:")
        for warning in allocation_result.warnings:
            print(f"  - {warning}")
    print()

    # Merge sell orders into target positions (sell orders take priority)
    merged_target_positions = dict(allocation_result.target_positions)

    if sell_orders:
        print(f"\nMerging {len(sell_orders)} sell orders into target positions...")
        for sell_order in sell_orders:
            symbol = sell_order["symbol"]
            sell_qty = sell_order["quantity"]  # Negative quantity

            # Sell orders override buy intents for the same symbol
            if symbol in merged_target_positions:
                print(f"  {symbol}: Replacing BUY intent with SELL order (quantity: {sell_qty})")

            merged_target_positions[symbol] = sell_qty

        print()

    # Execute orders (both buy and sell)
    print("Executing orders...")
    executor = AlpacaExecutor(broker, config, dry_run=dry_run)
    execution_result = executor.reconcile_and_execute(
        merged_target_positions,
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
        strategy_states = initialize_strategy_states(strategy_states, [s.name for s in strategies])

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

    # Use market time (America/New_York) for log filenames to align with trading day
    # Prevents UTC date rollover causing log files with tomorrow's date
    market_time = get_market_time_now()
    timestamp = market_time.strftime("%Y%m%d_%H%M%S_ET")
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


def run_loop(mode: str, dry_run: bool, sleep_seconds: int, cancel_open_orders: bool = False):
    """
    Run in loop mode: execute strategy runner repeatedly with sleep intervals.

    Catches exceptions and logs errors to logs/loop_errors.log.
    Writes status summaries to logs/loop_status.log.

    Args:
        mode: "shadow" or "paper"
        dry_run: Whether to run paper mode in dry-run
        sleep_seconds: Seconds to sleep between iterations
        cancel_open_orders: Whether to cancel open orders before each run
    """
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    status_log = log_dir / "loop_status.log"
    error_log = log_dir / "loop_errors.log"

    # Initialize runtime state for loop timing tracking
    from .state import load_runtime_state, save_runtime_state

    runtime_state = load_runtime_state()
    # Only set interval from command line if not already set in state
    # This allows UI changes to persist across iterations
    if runtime_state.loop_interval_seconds == 0:
        runtime_state.loop_interval_seconds = sleep_seconds
        save_runtime_state(runtime_state)
    else:
        # Use interval from state file (may have been updated by UI)
        sleep_seconds = runtime_state.loop_interval_seconds
        print(
            f"Using loop interval from state: {sleep_seconds} seconds ({sleep_seconds / 3600:.1f} hours)"
        )
        print()

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

    # Initialize strategy registry for next-tick activation
    print("Initializing strategy registry...")
    try:
        registry = StrategyRegistry()
        print(f"Registry loaded: {len(registry.get_state().strategies)} strategies configured")
        print()
    except FileNotFoundError:
        print("WARNING: Strategy registry not found (config/strategies.yaml missing)")
        print("Continuing without registry - strategies will use hardcoded configuration")
        registry = None
        print()

    # Initialize universe registry for next-tick activation
    print("Initializing universe registry...")
    try:
        from src.app.universe_registry import UniverseRegistry

        universe_registry = UniverseRegistry()
        print(f"Universe registry loaded: {len(universe_registry.sectors)} sectors configured")
        print()
    except FileNotFoundError as e:
        print(f"WARNING: Universe registry initialization failed: {e}")
        print("Continuing with base universe configuration from config.yaml")
        universe_registry = None
        print()
    except Exception as e:
        print(f"ERROR: Failed to load universe registry: {e}")
        universe_registry = None
        print()

    # Load config and ledger for the loop
    config = load_config_with_yaml()
    ledger = Ledger()

    iteration = 0
    while True:
        iteration += 1
        # Use market time for loop timestamps to align with log filenames
        market_time = get_market_time_now()
        run_timestamp = market_time.isoformat()

        # Record loop iteration start time (UTC for state tracking)
        loop_start_utc = datetime.now(UTC)
        runtime_state.last_loop_start = loop_start_utc.isoformat()
        # Preserve loop_interval_seconds from file (may have been changed by UI)
        preserved_state = load_runtime_state()
        runtime_state.loop_interval_seconds = preserved_state.loop_interval_seconds
        save_runtime_state(runtime_state)

        print(f"\n{'=' * 80}")
        print(f"LOOP ITERATION {iteration} - {run_timestamp}")
        print(f"{'=' * 80}\n")

        try:
            # Auto-generate advisor proposals if interval elapsed (best-effort)
            if config.llm_auto_generate_enabled and universe_registry is not None:
                try:
                    from src.app.universe_advisor.storage import load_proposals

                    proposals_file = Path("out/universe_proposals.json")
                    should_generate = True

                    if proposals_file.exists():
                        existing = load_proposals(proposals_file)
                        if existing:
                            generated_at = datetime.fromisoformat(existing.get("generated_at", ""))
                            elapsed_hours = (
                                datetime.now(UTC) - generated_at
                            ).total_seconds() / 3600
                            should_generate = (
                                elapsed_hours >= config.llm_auto_generate_interval_hours
                            )

                    if should_generate:
                        print("Auto-generating advisor proposals...")
                        try:
                            from src.app.data_providers.hourly_provider import (
                                HourlyMarketDataProvider,
                            )
                            from src.app.universe import load_universe_config, load_yaml_config
                            from src.app.universe_advisor.generate import (
                                generate_proposals,
                                load_recent_rss_events,
                            )
                            from src.app.universe_advisor.guardrails import apply_guardrails
                            from src.app.universe_advisor.regime import detect_market_regime
                            from src.app.universe_advisor.storage import save_proposals

                            # Detect regime
                            provider = HourlyMarketDataProvider(config)
                            regime = detect_market_regime(provider)

                            # Load RSS events
                            events_file = Path("out/selector/events.jsonl")
                            events = load_recent_rss_events(
                                events_file,
                                lookback_hours=config.llm_rss_lookback_hours,
                                max_headlines=config.llm_rss_max_headlines,
                            )

                            # Load sectors
                            yaml_config = load_yaml_config()
                            universe_config = load_universe_config(yaml_config)
                            sectors = {
                                name: {"description": sec.description, "symbols": sec.symbols}
                                for name, sec in universe_config.sectors.items()
                            }

                            # Generate proposals
                            llm_config = {
                                "mode": config.llm_mode,
                                "primary": config.llm_primary,
                                "openai_model": config.llm_openai_model,
                                "anthropic_model": config.llm_anthropic_model,
                                "timeout": config.llm_timeout,
                            }

                            proposal_set = generate_proposals(
                                llm_config, regime, events, sectors, config.llm_proposal_ttl_minutes
                            )

                            # Apply guardrails
                            guardrails_config = {
                                "min_confidence": config.llm_min_confidence,
                                "max_sector_toggles_per_day": config.llm_max_sector_toggles_per_day,
                                "cooldown_days": config.llm_cooldown_days,
                            }
                            history_file = Path("out/universe_proposals_history.jsonl")
                            proposal_set, filter_reasons = apply_guardrails(
                                proposal_set, guardrails_config, history_file
                            )

                            # Save
                            save_proposals(proposal_set, proposals_file, filter_reasons)

                            # Log to ledger
                            ledger.append(
                                {
                                    "event_type": "universe_proposals_generated",
                                    "generation_id": proposal_set.generation_id,
                                    "proposal_count": len(proposal_set.proposals),
                                    "disagreement_count": len(proposal_set.disagreements),
                                    "regime": regime.regime.value,
                                    "headline_count": len(events),
                                }
                            )

                            print(
                                f"Generated {len(proposal_set.proposals)} proposals, "
                                f"{len(proposal_set.disagreements)} disagreements"
                            )
                            print()
                        except Exception as e:
                            print(f"WARNING: Proposal generation failed: {e}")
                            print("Continuing with trading...")
                            print()
                except Exception as e:
                    print(f"WARNING: Auto-generation check failed: {e}")
                    print()

            # Check and activate pending strategy configuration changes (next-tick activation)
            if registry is not None:
                activated = registry.check_and_activate_pending()
                if activated:
                    print("Strategy configuration changes activated:")
                    for strategy_id, old_version, new_version in activated:
                        print(f"  {strategy_id}: v{old_version} -> v{new_version}")
                    print()

            # Check and activate pending universe configuration changes
            if universe_registry is not None:
                activated = universe_registry.check_and_activate_pending()
                if activated:
                    print("Universe configuration changes activated:")
                    for sector_name, old_version, new_version in activated:
                        print(f"  {sector_name}: v{old_version} -> v{new_version}")

                        # Mark related proposals as APPLIED
                        try:
                            from src.app.universe_advisor.apply import mark_applied

                            proposals_file = Path("out/universe_proposals.json")
                            history_file = Path("out/universe_proposals_history.jsonl")
                            mark_applied(sector_name, proposals_file, history_file)

                            # Log to ledger
                            ledger.append(
                                {
                                    "event_type": "universe_proposal_applied",
                                    "sector_name": sector_name,
                                    "version": new_version,
                                }
                            )
                        except Exception as e:
                            print(f"WARNING: Failed to mark proposals as applied: {e}")

                    print()

            # Run the appropriate mode
            if mode == "shadow":
                result = run_shadow_mode(universe_registry=universe_registry)
            elif mode == "paper":
                result = run_paper_mode(
                    dry_run=dry_run,
                    cancel_open_orders=cancel_open_orders,
                    registry=registry,
                    universe_registry=universe_registry,
                )
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

            # Record loop iteration end time and calculate next run
            loop_end_utc = datetime.now(UTC)
            runtime_state.last_loop_end = loop_end_utc.isoformat()
            # Calculate next run time (loop_end + sleep_seconds)
            next_run_utc = loop_end_utc + timedelta(seconds=sleep_seconds)
            runtime_state.next_loop_at = next_run_utc.isoformat()
            # Preserve loop_interval_seconds from file (may have been changed by UI)
            preserved_state = load_runtime_state()
            runtime_state.loop_interval_seconds = preserved_state.loop_interval_seconds
            save_runtime_state(runtime_state)

            # Capture equity snapshot (best-effort)
            if not dry_run and config.alpaca_api_key:
                try:
                    from src.app.equity_capture import capture_equity_snapshot
                    from src.broker.base import AlpacaBroker

                    # Get current equity from broker
                    broker = AlpacaBroker(
                        api_key=config.alpaca_api_key,
                        secret_key=config.alpaca_secret_key,
                        trading_base_url=config.alpaca_trading_base_url,
                    )

                    account = broker.client.get_account()
                    equity = float(account.equity)
                    cash = float(account.cash)

                    capture_equity_snapshot(
                        equity=equity,
                        cash=cash,
                        mode=config.mode,
                    )

                except Exception as e:
                    print(f"WARNING: Failed to capture equity snapshot: {e}")

            print(f"\n{'=' * 80}")
            print(f"ITERATION {iteration} COMPLETE")
            print(f"Status logged to: {status_log}")
            print(f"{'=' * 80}\n")

        except Exception as e:
            # Log error to error log
            # Use market time for consistency with log filenames
            error_timestamp = get_market_time_now().isoformat()
            error_msg = (
                f"\n{'=' * 80}\n"
                f"ERROR at {error_timestamp} (iteration {iteration})\n"
                f"{'=' * 80}\n"
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

            # Record loop iteration end time even on error
            loop_end_utc = datetime.now(UTC)
            runtime_state.last_loop_end = loop_end_utc.isoformat()
            # Calculate next run time (loop_end + sleep_seconds)
            next_run_utc = loop_end_utc + timedelta(seconds=sleep_seconds)
            runtime_state.next_loop_at = next_run_utc.isoformat()
            # Preserve loop_interval_seconds from file (may have been changed by UI)
            preserved_state = load_runtime_state()
            runtime_state.loop_interval_seconds = preserved_state.loop_interval_seconds
            save_runtime_state(runtime_state)

            print(f"\n{'=' * 80}")
            print(f"ERROR IN ITERATION {iteration}")
            print(f"Exception: {type(e).__name__}: {str(e)}")
            print(f"Error logged to: {error_log}")
            print("Continuing to next iteration...")
            print(f"{'=' * 80}\n")

        # Hot-reload loop interval from runtime state (allows changing interval without restart)
        try:
            from src.app.state import load_runtime_state

            reloaded_state = load_runtime_state()
            if reloaded_state.loop_interval_seconds != sleep_seconds:
                old_interval = sleep_seconds
                sleep_seconds = reloaded_state.loop_interval_seconds
                runtime_state.loop_interval_seconds = sleep_seconds
                print(
                    f"Loop interval updated: {old_interval}s -> {sleep_seconds}s ({sleep_seconds / 3600:.1f} hours)"
                )
        except Exception as e:
            print(f"WARNING: Failed to reload loop interval: {e}")

        # Sleep before next iteration (with interruptible sleep for early wake-up)
        print(f"Sleeping for {sleep_seconds} seconds ({sleep_seconds / 3600:.1f} hours)...")
        # Calculate next run time in market time
        next_run = get_market_time_now() + timedelta(seconds=sleep_seconds)
        print(f"Next run at: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print()

        try:
            # Use interruptible sleep that checks for trigger flag every 5 seconds
            trigger_flag = Path("state/trigger_loop.flag")
            sleep_remaining = sleep_seconds
            check_interval = 5  # Check every 5 seconds

            while sleep_remaining > 0:
                # Check if early wake-up requested
                if trigger_flag.exists():
                    print("\n*** Early wake-up triggered! Starting next iteration immediately ***")
                    trigger_flag.unlink()  # Remove flag
                    break

                # Sleep for shorter interval or remaining time
                sleep_duration = min(check_interval, sleep_remaining)
                time.sleep(sleep_duration)
                sleep_remaining -= sleep_duration

        except KeyboardInterrupt:
            print("\n\nKeyboard interrupt received. Shutting down loop mode...")
            print(f"Total iterations completed: {iteration}")
            sys.exit(0)


# Global handles to keep mutex and file lock alive for process lifetime
_MUTEX_HANDLE = None
_LOCK_FILE_HANDLE = None


def _check_parent_is_runner() -> tuple[bool, dict]:
    """
    Check if parent process is another python.exe potentially running the same runner.

    This helps detect Windows python->python re-exec scenarios where a parent
    python process spawns a child python process with the same command line.

    Returns:
        Tuple of (is_runner, info_dict) where:
        - is_runner: True if parent is python.exe with runner-like command line
        - info_dict: Parent process info (pid, name, cmdline)
    """
    # This function is Windows-specific
    if sys.platform != "win32":
        return False, {"platform": sys.platform, "note": "Windows-only check"}

    try:
        ppid = os.getppid()

        # Try to open parent process handle for query
        import win32con
        import win32process

        try:
            parent_handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, ppid
            )
        except pywintypes.error:
            # Can't open parent process (might have exited, or permission denied)
            return False, {"pid": ppid, "name": "unknown", "cmdline": "unknown"}

        try:
            # Get parent executable path
            parent_exe = win32process.GetModuleFileNameEx(parent_handle, 0)
            parent_name = os.path.basename(parent_exe).lower()

            # Check if parent is python.exe
            if parent_name == "python.exe":
                # Try to get command line (this is best-effort, may fail)
                try:
                    # Use WMI to get command line (more reliable)
                    import subprocess

                    result = subprocess.run(
                        [
                            "wmic",
                            "process",
                            "where",
                            f"ProcessId={ppid}",
                            "get",
                            "CommandLine",
                            "/format:list",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    cmdline = result.stdout.strip()

                    # Check if command line contains runner.py or src.app.runner
                    if "runner.py" in cmdline or "src.app.runner" in cmdline:
                        return True, {"pid": ppid, "name": parent_name, "cmdline": cmdline}

                    return False, {"pid": ppid, "name": parent_name, "cmdline": cmdline}
                except Exception:
                    # If we can't get cmdline, but parent is python.exe, flag it as suspicious
                    return True, {
                        "pid": ppid,
                        "name": parent_name,
                        "cmdline": "cmdline_unavailable",
                    }

            return False, {"pid": ppid, "name": parent_name, "cmdline": "not_python"}
        finally:
            win32api.CloseHandle(parent_handle)

    except Exception as e:
        # Best effort - if anything fails, return False
        return False, {"error": str(e)}


def _acquire_mutex(mutex_name: str) -> bool:
    """
    Acquire Windows named mutex using pywin32.

    FAIL-CLOSED: If acquisition fails for any reason, returns False.
    No fallback, no "continue anyway" logic.

    Args:
        mutex_name: Mutex name (e.g., "Local\\AI_TRADER__PAPER_DRYRUN_LOOP")

    Returns:
        True if mutex acquired (we are the only instance)
        False if mutex already exists OR acquisition failed
    """
    # This function is Windows-specific
    if sys.platform != "win32":
        return True  # On non-Windows, always return True (no mutex check)

    global _MUTEX_HANDLE

    try:
        # Create or open named mutex
        # If mutex exists, ERROR_ALREADY_EXISTS will be set
        _MUTEX_HANDLE = win32event.CreateMutex(None, True, mutex_name)

        # Check if mutex already existed
        last_error = win32api.GetLastError()
        # ERROR_ALREADY_EXISTS (183) means another instance is running
        # Successfully created new mutex if error != 183
        # Mutex will be held until process exits (auto-released by OS)
        return last_error != 183

    except pywintypes.error as e:
        # Mutex creation/opening failed
        print(f"ERROR: Failed to create mutex '{mutex_name}': {e}", flush=True)
        return False
    except Exception as e:
        # Unexpected error
        print(f"ERROR: Unexpected error creating mutex: {e}", flush=True)
        return False


def _acquire_file_lock(lock_file: Path) -> bool:
    """
    Acquire exclusive OS-level file lock using Windows CreateFileW.

    FAIL-CLOSED: If acquisition fails for any reason, returns False.
    The file handle remains open for the lifetime of the process.

    Args:
        lock_file: Path to lock file (e.g., Path("logs/paper_dryrun.lock"))

    Returns:
        True if lock acquired (we are the only instance)
        False if lock already held OR acquisition failed
    """
    # This function is Windows-specific
    if sys.platform != "win32":
        return True  # On non-Windows, always return True (no file lock check)

    global _LOCK_FILE_HANDLE

    try:
        # Ensure directory exists
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Open file with exclusive access using Windows CreateFileW
        # This is an OS-level exclusive lock - no other process can open this file
        from ctypes import windll

        # Constants
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_ALWAYS = 4
        FILE_ATTRIBUTE_NORMAL = 0x80

        # Create file with exclusive access (dwShareMode = 0 means no sharing)
        handle = windll.kernel32.CreateFileW(
            str(lock_file),
            GENERIC_READ | GENERIC_WRITE,
            0,  # dwShareMode = 0 (NO SHARING - exclusive)
            None,
            OPEN_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )

        if handle == -1:  # INVALID_HANDLE_VALUE
            # Lock is held by another process
            return False

        # Store handle to keep lock alive
        _LOCK_FILE_HANDLE = handle
        return True

    except Exception as e:
        print(f"ERROR: Failed to acquire file lock '{lock_file}': {e}")
        return False


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
    parser.add_argument(
        "--cancel-open-orders",
        action="store_true",
        help="Cancel all open orders before running (paper mode only)",
    )

    args = parser.parse_args()

    if args.mode == "shadow" and args.dry_run:
        print(
            "WARNING: --dry-run flag has no effect in shadow mode (shadow mode never places orders)"
        )
        print()

    # Run in loop or once
    if args.loop:
        run_loop(
            mode=args.mode,
            dry_run=args.dry_run,
            sleep_seconds=args.sleep_seconds,
            cancel_open_orders=args.cancel_open_orders,
        )
    else:
        # Default: run once
        if args.mode == "shadow":
            run_shadow_mode()
        elif args.mode == "paper":
            # Initialize strategy registry for equity-based allocation
            from src.app.strategy_registry import StrategyRegistry

            registry = StrategyRegistry()

            # Initialize universe registry for next-tick activation
            print("Initializing universe registry...")
            try:
                from src.app.universe_registry import UniverseRegistry

                universe_registry = UniverseRegistry()
                print(
                    f"Universe registry loaded: {len(universe_registry.sectors)} sectors configured"
                )
            except FileNotFoundError as e:
                print(f"WARNING: Universe registry initialization failed: {e}")
                print("Continuing with base universe configuration from config.yaml")
                universe_registry = None
            except Exception as e:
                print(f"ERROR: Failed to load universe registry: {e}")
                universe_registry = None

            run_paper_mode(
                dry_run=args.dry_run,
                cancel_open_orders=args.cancel_open_orders,
                registry=registry,
                universe_registry=universe_registry,
            )


# ============================================================================
# SINGLE-INSTANCE GUARD: Executes at module import time (when run as __main__)
# ============================================================================
# This code runs BEFORE main() is called, BEFORE argument parsing, BEFORE any
# code that could cause Python to re-exec itself with -m.
#
# FAIL-CLOSED: If guard fails, process exits immediately. No execution continues.
# ============================================================================

if __name__ == "__main__":
    # ========================================================================
    # Interpreter diagnostics: Log runner startup details
    # Helps diagnose venv mismatch, multiple instances, and spawn issues
    # ========================================================================
    pid = os.getpid()
    ppid = os.getppid() if hasattr(os, "getppid") else "N/A"
    interpreter = sys.executable
    argv_str = " ".join(sys.argv)

    # Check for python->python re-exec (diagnostic only, don't exit early)
    parent_is_runner, parent_info = _check_parent_is_runner()

    print("=" * 80, flush=True)
    print("RUNNER STARTUP DIAGNOSTICS", flush=True)
    print("=" * 80, flush=True)
    print(f"PID:         {pid}", flush=True)
    print(f"Parent PID:  {ppid}", flush=True)
    print(f"Interpreter: {interpreter}", flush=True)
    print(f"Arguments:   {argv_str}", flush=True)
    print(f"Market time: {get_market_time_now().strftime('%Y-%m-%d %H:%M:%S %Z')}", flush=True)

    if parent_is_runner:
        print("", flush=True)
        print("WARNING: Parent process is python.exe running runner", flush=True)
        print(f"  Parent PID: {parent_info.get('pid', 'unknown')}", flush=True)
        print(f"  Parent Cmd: {parent_info.get('cmdline', 'unknown')[:80]}...", flush=True)
        print("  This indicates Windows python->python re-exec", flush=True)
        print("  This may be normal Windows python->python re-exec behavior", flush=True)
        print("  Continuing normally; single-instance guard will block true duplicates", flush=True)

    print("=" * 80, flush=True)
    print("", flush=True)

    # Guard configuration
    mutex_name = "Local\\AI_TRADER__PAPER_DRYRUN_LOOP"
    lock_file = Path("logs") / "paper_dryrun.lock"

    # Guard 1: Acquire Windows Named Mutex
    mutex_acquired = _acquire_mutex(mutex_name)

    # Guard 2: Acquire Exclusive File Lock
    lock_acquired = _acquire_file_lock(lock_file) if mutex_acquired else False

    # FAIL-CLOSED: If EITHER guard failed, exit immediately
    if not mutex_acquired or not lock_acquired:
        print("=" * 80, flush=True)
        print("SINGLE INSTANCE GUARD: Another instance is already running", flush=True)
        print("=" * 80, flush=True)
        print(f"Mutex: {mutex_name}", flush=True)
        print(f"Lock file: {lock_file}", flush=True)
        print("", flush=True)
        print("This instance (blocked):", flush=True)
        print(f"  PID:         {pid}", flush=True)
        print(f"  Interpreter: {interpreter}", flush=True)

        if parent_is_runner:
            print("", flush=True)
            print(
                f"  Re-exec child: Parent PID {parent_info.get('pid')} is python.exe running runner",
                flush=True,
            )
            print("  This is expected Windows python->python re-exec behavior", flush=True)

        print("", flush=True)
        print("Another runner is already active. This instance will exit.", flush=True)
        print("To force-stop all runners, kill the existing process first.", flush=True)
        print("=" * 80, flush=True)
        sys.exit(1)  # Exit code 1 = guard blocked

    # ========================================================================
    # Guard passed - we are the only instance. Proceed to main().
    # ========================================================================
    main()
