"""Configuration loader for the trading bot."""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Trading bot configuration."""

    # Mode
    mode: str = Field(default="mock", description="Trading mode: mock or alpaca")

    # Alpaca credentials (optional)
    alpaca_api_key: str = Field(default="", description="Alpaca API key")
    alpaca_secret_key: str = Field(default="", description="Alpaca secret key")
    alpaca_trading_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca Trading API base URL (alpaca-py TradingClient will append /v2)",
    )
    alpaca_data_base_url: str = Field(
        default="https://data.alpaca.markets",
        description="Alpaca Market Data API base URL (used by StockHistoricalDataClient)",
    )

    # Risk parameters
    max_positions: int = Field(default=5, description="Max concurrent positions")
    max_order_quantity: int = Field(default=100, description="Max shares per order")
    max_daily_loss: Decimal = Field(
        default=Decimal("500"), description="Max daily loss threshold ($)"
    )
    max_session_loss: Decimal | None = Field(
        default=None, description="Max session loss threshold ($) - disabled if None"
    )
    max_order_notional: Decimal = Field(
        default=Decimal("500"), description="Max order notional value ($)"
    )
    max_positions_notional: Decimal = Field(
        default=Decimal("10000"), description="Max total positions exposure ($)"
    )
    target_utilization_pct: float = Field(
        default=0.97, description="Target capital utilization percentage (0.95-0.99 recommended)"
    )
    use_total_capital_as_equity_cap: bool = Field(
        default=True, description="Use total_capital from account_summary.json as equity cap"
    )
    allowed_symbols: list[str] = Field(
        default=["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"], description="Allowed trading symbols"
    )

    # Trading cost controls
    use_limit_orders: bool = Field(
        default=True, description="Use limit orders instead of market orders"
    )
    max_spread_bps: Decimal = Field(default=Decimal("20"), description="Max allowed spread in bps")
    min_edge_bps: Decimal = Field(
        default=Decimal("0"), description="Minimum edge required in bps (0 = disabled)"
    )
    cost_diagnostics: bool = Field(default=True, description="Enable cost diagnostics reporting")

    # Symbol eligibility and liquidity guardrails
    min_avg_volume: int = Field(
        default=1_000_000, description="Minimum average daily volume threshold"
    )
    min_price: Decimal = Field(
        default=Decimal("2.00"), description="Minimum price to prevent penny stocks"
    )
    max_price: Decimal = Field(default=Decimal("1000.00"), description="Maximum price sanity cap")
    require_quote: bool = Field(default=True, description="Require valid bid/ask quote to trade")
    symbol_whitelist: list[str] = Field(
        default=[], description="Symbol whitelist (empty = allow all)"
    )
    symbol_blacklist: list[str] = Field(default=[], description="Symbol blacklist (always blocks)")

    # Strategy parameters
    sma_fast_period: int = Field(default=10, description="Fast SMA period")
    sma_slow_period: int = Field(default=30, description="Slow SMA period")

    # Market hours (EST)
    market_open_hour: int = Field(default=9, description="Market open hour EST")
    market_open_minute: int = Field(default=30, description="Market open minute")
    market_close_hour: int = Field(default=16, description="Market close hour EST")
    market_close_minute: int = Field(default=0, description="Market close minute")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Live trading safety flags
    enable_live_trading: bool = Field(
        default=False, description="Enable live trading (required for live mode)"
    )
    i_understand_live_trading_risk: bool = Field(
        default=False, description="Acknowledge understanding of live trading risks"
    )

    # Dry-run mode
    dry_run: bool = Field(
        default=False, description="Dry-run mode: simulate trading without submitting orders"
    )

    # Strategy configuration (from YAML)
    timeframe: str = Field(default="1h", description="Strategy timeframe (e.g., 1h, 15m)")
    universe_symbols: list[str] = Field(
        default=[], description="Trading universe symbols from config"
    )

    # Execution settings
    allow_fractional: bool = Field(
        default=False, description="Allow fractional share orders (paper mode only)"
    )
    order_style: str = Field(
        default="limit", description="Order type: 'limit' or 'market'"
    )
    limit_offset_bps_buy: int = Field(
        default=10, description="Buy limit offset in basis points (0.10%)"
    )
    limit_offset_bps_sell: int = Field(
        default=10, description="Sell limit offset in basis points (0.10%)"
    )
    allow_market_in_paper: bool = Field(
        default=True, description="Allow market orders in paper mode for faster fills"
    )

    # Order hygiene settings
    cancel_stale_orders: bool = Field(
        default=True, description="Cancel/replace stale open orders before placing new ones"
    )
    max_open_orders_per_symbol_side: int = Field(
        default=1, description="Maximum open orders allowed per (symbol, side) pair"
    )
    order_price_tolerance_pct: float = Field(
        default=0.001, description="Price tolerance (0.1%) for considering orders equivalent"
    )
    order_qty_tolerance: float = Field(
        default=0.0001, description="Quantity tolerance for fractional shares"
    )

    # Performance tracking (Shadow PnL)
    performance_min_samples: int = Field(
        default=20, description="Minimum samples before strategy weight updates"
    )
    performance_max_samples: int = Field(
        default=200, description="Maximum rolling return samples to keep per strategy"
    )

    # LLM Advisor Configuration
    llm_mode: str = Field(default="primary_fallback", description="LLM provider mode")
    llm_primary: str = Field(default="openai", description="Primary LLM provider")
    llm_openai_model: str = Field(default="gpt-4-turbo-preview", description="OpenAI model to use")
    llm_anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", description="Anthropic model to use"
    )
    llm_timeout: int = Field(default=30, description="LLM API timeout in seconds")
    llm_min_confidence: float = Field(
        default=0.70, description="Minimum confidence threshold for proposals"
    )
    llm_proposal_ttl_minutes: int = Field(
        default=120, description="Proposal time-to-live in minutes"
    )
    llm_max_sector_toggles_per_day: int = Field(
        default=1, description="Maximum sector toggles per day"
    )
    llm_cooldown_days: int = Field(default=3, description="Cooldown period in days per sector")
    llm_rss_lookback_hours: int = Field(
        default=24, description="RSS events lookback period in hours"
    )
    llm_rss_max_headlines: int = Field(default=100, description="Maximum RSS headlines to process")
    llm_auto_generate_enabled: bool = Field(
        default=True, description="Enable automatic proposal generation"
    )
    llm_auto_generate_interval_hours: int = Field(
        default=4, description="Auto-generation interval in hours"
    )
    # Constituent change proposals
    llm_enable_constituent_proposals: bool = Field(
        default=True, description="Enable constituent change proposals"
    )
    llm_allow_constituent_removals: bool = Field(
        default=False, description="Allow REMOVE constituent proposals"
    )
    llm_max_add_per_run: int = Field(default=2, description="Max ADD proposals per generation run")
    llm_max_remove_per_run: int = Field(
        default=1, description="Max REMOVE proposals per generation run"
    )
    llm_min_confidence_add: float = Field(
        default=0.80, description="Min confidence for ADD proposals"
    )
    llm_min_confidence_remove: float = Field(
        default=0.85, description="Min confidence for REMOVE proposals"
    )
    llm_cooldown_days_per_ticker: int = Field(
        default=7, description="Cooldown days for ticker changes"
    )
    llm_ticker_blacklist: list[str] = Field(default_factory=list, description="Blacklisted tickers")
    # Removal rubric
    llm_removal_min_failed_eligibility_checks: int = Field(
        default=5, description="Remove ticker after N failed eligibility checks"
    )
    llm_removal_min_days_no_activity: int = Field(
        default=14, description="Remove ticker after N days of no trades/signals"
    )
    llm_removal_stale_negative_news_confidence: float = Field(
        default=0.80, description="Remove ticker if negative news confidence > N"
    )


def get_alpaca_credentials(mode: str) -> tuple[str, str, str, str]:
    """
    Get Alpaca credentials and endpoints based on trading mode.

    Loads credentials from mode-specific environment variables:
    - Paper mode: ALPACA_PAPER_KEY_ID, ALPACA_PAPER_SECRET_KEY
    - Live mode: ALPACA_LIVE_KEY_ID, ALPACA_LIVE_SECRET_KEY

    Falls back to legacy ALPACA_API_KEY and ALPACA_SECRET_KEY if mode-specific vars not found.

    Base URLs:
    - Trading API: ALPACA_TRADING_BASE_URL (alpaca-py TradingClient will append /v2)
    - Data API: ALPACA_DATA_BASE_URL (used by StockHistoricalDataClient)

    Args:
        mode: Trading mode (mock, paper, live, dry-run, or alpaca)

    Returns:
        Tuple of (api_key, secret_key, trading_base_url, data_base_url)
    """
    # Determine if we're in live mode
    # Check ALPACA_TRADING_BASE_URL instead of legacy ALPACA_BASE_URL
    trading_base_url_check = os.getenv("ALPACA_TRADING_BASE_URL", "")
    is_live = mode == "live" or (
        mode == "alpaca"
        and trading_base_url_check
        and "paper" not in trading_base_url_check.lower()
    )

    if is_live:
        # Live mode: use ALPACA_LIVE_KEY_ID and ALPACA_LIVE_SECRET_KEY
        api_key = os.getenv("ALPACA_LIVE_KEY_ID", "")
        secret_key = os.getenv("ALPACA_LIVE_SECRET_KEY", "")
        trading_base_url = "https://api.alpaca.markets"
        data_base_url = "https://data.alpaca.markets"

        # Fallback to legacy vars if new vars not set
        if not api_key:
            api_key = os.getenv("ALPACA_API_KEY", "")
        if not secret_key:
            secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    else:
        # Paper mode: use ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY
        api_key = os.getenv("ALPACA_PAPER_KEY_ID", "")
        secret_key = os.getenv("ALPACA_PAPER_SECRET_KEY", "")
        trading_base_url = "https://paper-api.alpaca.markets"
        data_base_url = "https://data.alpaca.markets"

        # Fallback to legacy vars if new vars not set
        if not api_key:
            api_key = os.getenv("ALPACA_API_KEY", "")
        if not secret_key:
            secret_key = os.getenv("ALPACA_SECRET_KEY", "")

    # Allow explicit base URL overrides
    trading_base_url = os.getenv("ALPACA_TRADING_BASE_URL", trading_base_url)
    data_base_url = os.getenv("ALPACA_DATA_BASE_URL", data_base_url)

    return api_key, secret_key, trading_base_url, data_base_url


def load_config() -> Config:
    """Load configuration from .env file and environment variables."""
    # Load .env file from repo root (works regardless of CWD)
    # __file__ is src/app/config.py, so we go up 2 levels to reach repo root
    repo_root = Path(__file__).resolve().parents[2]
    dotenv_path = repo_root / ".env"
    # Use override=True to make .env file take precedence over system environment variables
    load_dotenv(dotenv_path=dotenv_path, override=True)

    # Get mode first
    mode = os.getenv("MODE", "mock")

    # Get Alpaca credentials based on mode
    api_key, secret_key, trading_base_url, data_base_url = get_alpaca_credentials(mode)

    # Build config from environment variables
    config_dict = {
        "mode": mode,
        "alpaca_api_key": api_key,
        "alpaca_secret_key": secret_key,
        "alpaca_trading_base_url": trading_base_url,
        "alpaca_data_base_url": data_base_url,
        "max_positions": int(os.getenv("MAX_POSITIONS", "5")),
        "max_order_quantity": int(os.getenv("MAX_ORDER_QUANTITY", "100")),
        "max_daily_loss": Decimal(os.getenv("MAX_DAILY_LOSS", "500")),
        "max_session_loss": Decimal(os.getenv("MAX_SESSION_LOSS"))
        if os.getenv("MAX_SESSION_LOSS")
        else None,
        "max_order_notional": Decimal(os.getenv("MAX_ORDER_NOTIONAL", "500")),
        "max_positions_notional": Decimal(os.getenv("MAX_POSITIONS_NOTIONAL", "10000")),
        "use_limit_orders": os.getenv("USE_LIMIT_ORDERS", "true").lower() == "true",
        "max_spread_bps": Decimal(os.getenv("MAX_SPREAD_BPS", "20")),
        "min_edge_bps": Decimal(os.getenv("MIN_EDGE_BPS", "0")),
        "cost_diagnostics": os.getenv("COST_DIAGNOSTICS", "true").lower() == "true",
        "min_avg_volume": int(os.getenv("MIN_AVG_VOLUME", "1000000")),
        "min_price": Decimal(os.getenv("MIN_PRICE", "2.00")),
        "max_price": Decimal(os.getenv("MAX_PRICE", "1000.00")),
        "require_quote": os.getenv("REQUIRE_QUOTE", "true").lower() == "true",
        "sma_fast_period": int(os.getenv("SMA_FAST_PERIOD", "10")),
        "sma_slow_period": int(os.getenv("SMA_SLOW_PERIOD", "30")),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "enable_live_trading": os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true",
        "i_understand_live_trading_risk": os.getenv(
            "I_UNDERSTAND_LIVE_TRADING_RISK", "false"
        ).lower()
        == "true",
        "dry_run": os.getenv("DRY_RUN", "false").lower() == "true",
    }

    # Parse allowed symbols - support both WATCHLIST and ALLOWED_SYMBOLS
    # WATCHLIST takes precedence if both are set
    symbols_str = os.getenv("WATCHLIST") or os.getenv(
        "ALLOWED_SYMBOLS", "AAPL,MSFT,GOOGL,AMZN,TSLA"
    )
    config_dict["allowed_symbols"] = [s.strip() for s in symbols_str.split(",")]

    # Parse symbol whitelist
    whitelist_str = os.getenv("SYMBOL_WHITELIST", "")
    config_dict["symbol_whitelist"] = (
        [s.strip() for s in whitelist_str.split(",") if s.strip()] if whitelist_str else []
    )

    # Parse symbol blacklist
    blacklist_str = os.getenv("SYMBOL_BLACKLIST", "")
    config_dict["symbol_blacklist"] = (
        [s.strip() for s in blacklist_str.split(",") if s.strip()] if blacklist_str else []
    )

    return Config(**config_dict)


def is_live_trading_mode(config: Config) -> bool:
    """
    Detect if configuration is for live trading (real money).

    Live trading mode is detected when:
    - mode is "alpaca" AND
    - alpaca_trading_base_url is the live API (not paper trading)

    Args:
        config: Configuration object

    Returns:
        True if live trading mode, False otherwise
    """
    return config.mode == "alpaca" and "paper" not in config.alpaca_trading_base_url.lower()


def validate_alpaca_credentials(mode: str, require_credentials: bool = True) -> tuple[bool, str]:
    """
    Validate that required Alpaca credentials are present for the given mode.

    Args:
        mode: Trading mode (paper or live)
        require_credentials: If True, missing credentials is an error

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if mode not in ("paper", "live"):
        # Mock/dry-run modes don't need credentials
        return True, ""

    api_key, secret_key, _, _ = get_alpaca_credentials(mode)

    if not require_credentials:
        # Just checking what's available, not enforcing
        return bool(api_key and secret_key), ""

    if mode == "paper":
        if not api_key or not secret_key:
            msg = (
                "ERROR: Paper mode requires Alpaca paper trading credentials.\n"
                "Please set environment variables:\n"
                "  ALPACA_PAPER_KEY_ID=your_paper_key\n"
                "  ALPACA_PAPER_SECRET_KEY=your_paper_secret\n"
                "\n"
                "Windows PowerShell example:\n"
                '  $env:ALPACA_PAPER_KEY_ID = "PK..."\n'
                '  $env:ALPACA_PAPER_SECRET_KEY = "..."\n'
                "\n"
                "Or add to .env file (do NOT commit this file):\n"
                "  ALPACA_PAPER_KEY_ID=PK...\n"
                "  ALPACA_PAPER_SECRET_KEY=...\n"
            )
            return False, msg
    elif mode == "live" and (not api_key or not secret_key):
        msg = (
            "ERROR: Live mode requires Alpaca live trading credentials.\n"
            "Please set environment variables:\n"
            "  ALPACA_LIVE_KEY_ID=your_live_key\n"
            "  ALPACA_LIVE_SECRET_KEY=your_live_secret\n"
            "\n"
            "Windows PowerShell example:\n"
            '  $env:ALPACA_LIVE_KEY_ID = "AK..."\n'
            '  $env:ALPACA_LIVE_SECRET_KEY = "..."\n'
            "\n"
            "Or add to .env file (do NOT commit this file):\n"
            "  ALPACA_LIVE_KEY_ID=AK...\n"
            "  ALPACA_LIVE_SECRET_KEY=...\n"
            "\n"
            "WARNING: Live mode uses REAL MONEY. Ensure you understand the risks.\n"
        )
        return False, msg

    return True, ""


def load_yaml_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file (defaults to config/config.yaml in repo root)

    Returns:
        Dictionary with configuration values
    """
    if config_path is None:
        repo_root = Path(__file__).resolve().parents[2]
        config_path = repo_root / "config" / "config.yaml"

    if not config_path.exists():
        return {}

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def load_config_with_yaml(yaml_path: Path | None = None) -> Config:
    """
    Load configuration from both .env and YAML files.

    YAML config values are merged with environment variable config.
    Environment variables take precedence over YAML values.

    Args:
        yaml_path: Optional path to YAML config file

    Returns:
        Config object with merged configuration
    """
    # First load the standard env-based config
    config = load_config()

    # Load YAML config if available
    yaml_config = load_yaml_config(yaml_path)

    if yaml_config:
        # Apply timeframe from YAML
        if "timeframe" in yaml_config:
            config.timeframe = yaml_config["timeframe"]

        # Apply universe symbols from YAML
        if "universe" in yaml_config:
            from src.app.universe import resolve_universe

            resolution = resolve_universe(yaml_config)

            # Log warnings
            if resolution.warnings:
                import logging

                logger = logging.getLogger("ai-trader")
                for warning in resolution.warnings:
                    logger.warning(f"Universe resolution: {warning}")

            # Set resolved symbols
            if resolution.symbols:
                config.universe_symbols = resolution.symbols

        # Apply risk parameters from YAML (override existing if present)
        if "risk" in yaml_config:
            risk = yaml_config["risk"]
            if "max_order_usd" in risk:
                config.max_order_notional = Decimal(str(risk["max_order_usd"]))
            if "max_daily_loss_usd" in risk:
                config.max_daily_loss = Decimal(str(risk["max_daily_loss_usd"]))
            if "max_gross_exposure_usd" in risk:
                config.max_positions_notional = Decimal(str(risk["max_gross_exposure_usd"]))
            if "target_utilization_pct" in risk:
                config.target_utilization_pct = float(risk["target_utilization_pct"])
            if "use_total_capital_as_equity_cap" in risk:
                config.use_total_capital_as_equity_cap = bool(risk["use_total_capital_as_equity_cap"])

        # Apply execution parameters from YAML
        if "execution" in yaml_config:
            execution = yaml_config["execution"]
            if "allow_fractional" in execution:
                config.allow_fractional = execution["allow_fractional"]
            if "order_style" in execution:
                config.order_style = str(execution["order_style"])
            if "limit_offset_bps_buy" in execution:
                config.limit_offset_bps_buy = int(execution["limit_offset_bps_buy"])
            if "limit_offset_bps_sell" in execution:
                config.limit_offset_bps_sell = int(execution["limit_offset_bps_sell"])
            if "allow_market_in_paper" in execution:
                config.allow_market_in_paper = bool(execution["allow_market_in_paper"])
            # Order hygiene settings
            if "cancel_stale_orders" in execution:
                config.cancel_stale_orders = bool(execution["cancel_stale_orders"])
            if "max_open_orders_per_symbol_side" in execution:
                config.max_open_orders_per_symbol_side = int(execution["max_open_orders_per_symbol_side"])
            if "order_price_tolerance_pct" in execution:
                config.order_price_tolerance_pct = float(execution["order_price_tolerance_pct"])
            if "order_qty_tolerance" in execution:
                config.order_qty_tolerance = float(execution["order_qty_tolerance"])

        # Apply performance tracking parameters from YAML
        if "performance" in yaml_config:
            performance = yaml_config["performance"]
            if "min_samples" in performance:
                config.performance_min_samples = int(performance["min_samples"])
            if "max_samples" in performance:
                config.performance_max_samples = int(performance["max_samples"])

        # Apply LLM parameters from YAML
        if "llm" in yaml_config:
            llm = yaml_config["llm"]
            if "mode" in llm:
                config.llm_mode = llm["mode"]
            if "primary" in llm:
                config.llm_primary = llm["primary"]
            if "openai_model" in llm:
                config.llm_openai_model = llm["openai_model"]
            if "anthropic_model" in llm:
                config.llm_anthropic_model = llm["anthropic_model"]
            if "timeout_seconds" in llm:
                config.llm_timeout = int(llm["timeout_seconds"])
            if "min_confidence" in llm:
                config.llm_min_confidence = float(llm["min_confidence"])
            if "proposal_ttl_minutes" in llm:
                config.llm_proposal_ttl_minutes = int(llm["proposal_ttl_minutes"])
            if "max_sector_toggles_per_day" in llm:
                config.llm_max_sector_toggles_per_day = int(llm["max_sector_toggles_per_day"])
            if "cooldown_days" in llm:
                config.llm_cooldown_days = int(llm["cooldown_days"])
            if "rss_lookback_hours" in llm:
                config.llm_rss_lookback_hours = int(llm["rss_lookback_hours"])
            if "rss_max_headlines" in llm:
                config.llm_rss_max_headlines = int(llm["rss_max_headlines"])
            if "auto_generate_enabled" in llm:
                config.llm_auto_generate_enabled = bool(llm["auto_generate_enabled"])
            if "auto_generate_interval_hours" in llm:
                config.llm_auto_generate_interval_hours = int(llm["auto_generate_interval_hours"])
            # Constituent change proposals
            if "enable_constituent_proposals" in llm:
                config.llm_enable_constituent_proposals = bool(llm["enable_constituent_proposals"])
            if "allow_constituent_removals" in llm:
                config.llm_allow_constituent_removals = bool(llm["allow_constituent_removals"])
            if "max_add_per_run" in llm:
                config.llm_max_add_per_run = int(llm["max_add_per_run"])
            if "max_remove_per_run" in llm:
                config.llm_max_remove_per_run = int(llm["max_remove_per_run"])
            if "min_confidence_add" in llm:
                config.llm_min_confidence_add = float(llm["min_confidence_add"])
            if "min_confidence_remove" in llm:
                config.llm_min_confidence_remove = float(llm["min_confidence_remove"])
            if "cooldown_days_per_ticker" in llm:
                config.llm_cooldown_days_per_ticker = int(llm["cooldown_days_per_ticker"])
            if "ticker_blacklist" in llm:
                config.llm_ticker_blacklist = list(llm["ticker_blacklist"])
            # Removal rubric
            if "removal_min_failed_eligibility_checks" in llm:
                config.llm_removal_min_failed_eligibility_checks = int(
                    llm["removal_min_failed_eligibility_checks"]
                )
            if "removal_min_days_no_activity" in llm:
                config.llm_removal_min_days_no_activity = int(llm["removal_min_days_no_activity"])
            if "removal_stale_negative_news_confidence" in llm:
                config.llm_removal_stale_negative_news_confidence = float(
                    llm["removal_stale_negative_news_confidence"]
                )

    return config
