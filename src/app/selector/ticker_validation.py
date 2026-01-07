"""Ticker validation utilities for candidate filtering."""

from __future__ import annotations

import re
from typing import Any

# Stopword blacklist: common false positives from RSS headlines
DEFAULT_STOPWORDS = {
    "CEO",
    "AI",
    "US",
    "USA",
    "IPO",
    "ETF",
    "SEC",
    "FED",
    "CPI",
    "GDP",
    "EPS",
    "Q4",
    "Q3",
    "Q2",
    "Q1",
    "BTC",
    "ETH",
    "API",
    "IT",
    "HR",
    "PR",
    "IR",
    "VP",
    "SVP",
    "EVP",
    "CTO",
    "CFO",
    "COO",
    "CMO",
}

# Ticker pattern: 1-5 uppercase letters (optionally allow . and - later)
TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


class TickerValidator:
    """Validates ticker symbols with deterministic rules."""

    def __init__(
        self,
        stopwords: set[str] | None = None,
        alpaca_client: Any | None = None,
    ):
        """
        Initialize validator.

        Args:
            stopwords: Custom stopword set (defaults to DEFAULT_STOPWORDS)
            alpaca_client: Optional Alpaca client for asset validation
        """
        self.stopwords = stopwords or DEFAULT_STOPWORDS
        self.alpaca_client = alpaca_client
        self._asset_cache: dict[str, bool] = {}

    def is_valid_format(self, ticker: str) -> bool:
        """Check if ticker matches valid format (1-5 uppercase letters)."""
        return bool(TICKER_PATTERN.match(ticker))

    def is_stopword(self, ticker: str) -> bool:
        """Check if ticker is a stopword (common false positive)."""
        return ticker.upper() in self.stopwords

    def is_tradable_asset(self, ticker: str) -> tuple[bool, str | None]:
        """
        Check if ticker is a tradable asset via Alpaca.

        Returns:
            (is_valid, error_message)
        """
        if self.alpaca_client is None:
            return True, None  # Skip check if no client

        # Check cache first
        if ticker in self._asset_cache:
            return self._asset_cache[ticker], None

        try:
            asset = self.alpaca_client.get_asset(ticker)
            is_valid = asset.tradable and asset.status == "active"
            self._asset_cache[ticker] = is_valid

            if not is_valid:
                return False, f"Asset not tradable or inactive: {asset.status}"

            return True, None

        except Exception as e:
            # Asset not found or API error
            error_msg = f"Asset lookup failed: {e}"
            self._asset_cache[ticker] = False
            return False, error_msg

    def validate(self, ticker: str) -> tuple[bool, str | None]:
        """
        Validate ticker with all rules.

        Returns:
            (is_valid, rejection_reason)
        """
        ticker = ticker.upper().strip()

        # Format check
        if not self.is_valid_format(ticker):
            return False, f"Invalid format: {ticker}"

        # Stopword check
        if self.is_stopword(ticker):
            return False, f"Stopword: {ticker}"

        # Alpaca asset check (if available)
        is_tradable, error = self.is_tradable_asset(ticker)
        if not is_tradable:
            return False, error

        return True, None


def create_validator(
    config: dict[str, Any] | None = None,
    alpaca_client: Any | None = None,
) -> TickerValidator:
    """
    Factory function to create validator from config.

    Args:
        config: Config dict with optional 'stopwords' key
        alpaca_client: Optional Alpaca client

    Returns:
        Configured TickerValidator
    """
    stopwords = None
    if config and "stopwords" in config:
        stopwords = set(config["stopwords"])

    return TickerValidator(stopwords=stopwords, alpaca_client=alpaca_client)
