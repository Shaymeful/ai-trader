"""Configuration loader for the trading bot."""

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Trading bot configuration."""

    # Mode
    mode: str = Field(default="mock", description="Trading mode: mock or alpaca")

    # Alpaca credentials (optional)
    alpaca_api_key: str = Field(default="", description="Alpaca API key")
    alpaca_secret_key: str = Field(default="", description="Alpaca secret key")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets", description="Alpaca base URL"
    )

    # Risk parameters
    max_positions: int = Field(default=5, description="Max concurrent positions")
    max_order_quantity: int = Field(default=100, description="Max shares per order")
    max_daily_loss: Decimal = Field(
        default=Decimal("500"), description="Max daily loss threshold ($)"
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


def load_config() -> Config:
    """Load configuration from .env file and environment variables."""
    # Load .env file from repo root (works regardless of CWD)
    # __file__ is src/app/config.py, so we go up 2 levels to reach repo root
    repo_root = Path(__file__).resolve().parents[2]
    dotenv_path = repo_root / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)

    # Build config from environment variables
    config_dict = {
        "mode": os.getenv("MODE", "mock"),
        "alpaca_api_key": os.getenv("ALPACA_API_KEY", ""),
        "alpaca_secret_key": os.getenv("ALPACA_SECRET_KEY", ""),
        "alpaca_base_url": os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        "max_positions": int(os.getenv("MAX_POSITIONS", "5")),
        "max_order_quantity": int(os.getenv("MAX_ORDER_QUANTITY", "100")),
        "max_daily_loss": Decimal(os.getenv("MAX_DAILY_LOSS", "500")),
        "max_order_notional": Decimal(os.getenv("MAX_ORDER_NOTIONAL", "500")),
        "max_positions_notional": Decimal(os.getenv("MAX_POSITIONS_NOTIONAL", "10000")),
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

    return Config(**config_dict)


def is_live_trading_mode(config: Config) -> bool:
    """
    Detect if configuration is for live trading (real money).

    Live trading mode is detected when:
    - mode is "alpaca" AND
    - alpaca_base_url is the live API (not paper trading)

    Args:
        config: Configuration object

    Returns:
        True if live trading mode, False otherwise
    """
    return config.mode == "alpaca" and "paper" not in config.alpaca_base_url.lower()
