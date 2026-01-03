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

    # Performance tracking (Shadow PnL)
    performance_min_samples: int = Field(
        default=20, description="Minimum samples before strategy weight updates"
    )
    performance_max_samples: int = Field(
        default=200, description="Maximum rolling return samples to keep per strategy"
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
        mode == "alpaca" and trading_base_url_check and "paper" not in trading_base_url_check.lower()
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
    load_dotenv(dotenv_path=dotenv_path, override=False)

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
        if "universe" in yaml_config and "core" in yaml_config["universe"]:
            core_symbols = yaml_config["universe"]["core"].get("symbols", [])
            if core_symbols:
                config.universe_symbols = core_symbols

        # Apply risk parameters from YAML (override existing if present)
        if "risk" in yaml_config:
            risk = yaml_config["risk"]
            if "max_order_usd" in risk:
                config.max_order_notional = Decimal(str(risk["max_order_usd"]))
            if "max_daily_loss_usd" in risk:
                config.max_daily_loss = Decimal(str(risk["max_daily_loss_usd"]))
            if "max_gross_exposure_usd" in risk:
                config.max_positions_notional = Decimal(str(risk["max_gross_exposure_usd"]))

        # Apply execution parameters from YAML
        if "execution" in yaml_config:
            execution = yaml_config["execution"]
            if "allow_fractional" in execution:
                config.allow_fractional = execution["allow_fractional"]

        # Apply performance tracking parameters from YAML
        if "performance" in yaml_config:
            performance = yaml_config["performance"]
            if "min_samples" in performance:
                config.performance_min_samples = int(performance["min_samples"])
            if "max_samples" in performance:
                config.performance_max_samples = int(performance["max_samples"])

    return config
