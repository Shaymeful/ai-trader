"""Centralized tradability filter for enforcing execution constraints.

This module provides a hard gate that runs BEFORE any order is placed,
regardless of strategy or universe configuration. It enforces:

- Market cap constraints (small/mid/large cap targeting)
- Price constraints (avoid penny stocks or ultra-expensive stocks)
- Liquidity constraints (minimum average dollar volume)
- Spread constraints (bid-ask spread quality)
- Allow/exclude symbol lists (explicit overrides)

Design principles:
- Hard gate: blocks orders that violate constraints
- Strategy-agnostic: applies to all strategies
- Universe-independent: enforces even if universe allows symbol
- Logged rejections: all blocked orders written to ledger with reason codes
- Config-driven: all thresholds configurable via modes or config overrides
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from src.market_data.fundamentals_cache import FundamentalsCache

logger = logging.getLogger("ai-trader")


class BlockReason(Enum):
    """Reason codes for blocked trades."""

    MARKET_CAP_TOO_LOW = "market_cap_below_minimum"
    MARKET_CAP_TOO_HIGH = "market_cap_above_maximum"
    PRICE_TOO_LOW = "price_below_minimum"
    PRICE_TOO_HIGH = "price_above_maximum"
    LIQUIDITY_TOO_LOW = "avg_dollar_volume_below_minimum"
    SPREAD_TOO_WIDE = "bid_ask_spread_above_maximum"
    SYMBOL_EXCLUDED = "symbol_in_exclude_list"
    FUNDAMENTALS_UNAVAILABLE = "fundamentals_data_not_available"


@dataclass
class TradabilityResult:
    """Result of tradability check."""

    allowed: bool
    reason: BlockReason | None = None
    message: str | None = None
    fundamentals_checked: bool = False


@dataclass
class ExecutionGateConfig:
    """Configuration for execution gate constraints."""

    # Market cap constraints (USD)
    min_market_cap_usd: float | None = None
    max_market_cap_usd: float | None = None

    # Price constraints (USD)
    min_price: float | None = None
    max_price: float | None = None

    # Liquidity constraints
    min_avg_dollar_volume_20d: float | None = None

    # Spread constraint (basis points)
    max_spread_bps: float | None = None

    # Symbol lists (explicit overrides)
    exclude_symbols: list[str] | None = None  # Explicit ban list
    allow_symbols: list[str] | None = None  # Bypass all checks

    # Behavior flags
    require_fundamentals: bool = False  # If True, block if fundamentals unavailable
    strict_mode: bool = True  # If False, only warn on violations instead of blocking

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "ExecutionGateConfig":
        """Create config from dictionary."""
        return cls(
            min_market_cap_usd=config.get("min_market_cap_usd"),
            max_market_cap_usd=config.get("max_market_cap_usd"),
            min_price=config.get("min_price"),
            max_price=config.get("max_price"),
            min_avg_dollar_volume_20d=config.get("min_avg_dollar_volume_20d"),
            max_spread_bps=config.get("max_spread_bps"),
            exclude_symbols=config.get("exclude_symbols", []),
            allow_symbols=config.get("allow_symbols", []),
            require_fundamentals=config.get("require_fundamentals", False),
            strict_mode=config.get("strict_mode", True),
        )


class TradabilityGate:
    """Centralized execution gate for ticker tradability filtering.

    This gate enforces hard constraints on which symbols can be traded,
    independent of strategy logic or universe configuration.

    Usage:
        gate = TradabilityGate(config, fundamentals_cache)
        result = gate.check_tradability(symbol, price)
        if not result.allowed:
            log_blocked_order(symbol, result.reason, result.message)
            skip order
    """

    def __init__(self, config: ExecutionGateConfig, fundamentals_cache: FundamentalsCache):
        """Initialize tradability gate.

        Args:
            config: Execution gate configuration
            fundamentals_cache: Cache for fundamentals data
        """
        self.config = config
        self.fundamentals_cache = fundamentals_cache

        # Log active constraints
        self._log_active_constraints()

    def _log_active_constraints(self) -> None:
        """Log active execution gate constraints for transparency."""
        constraints = []

        if self.config.min_market_cap_usd:
            constraints.append(f"min_market_cap: ${self.config.min_market_cap_usd:,.0f}")
        if self.config.max_market_cap_usd:
            constraints.append(f"max_market_cap: ${self.config.max_market_cap_usd:,.0f}")
        if self.config.min_price:
            constraints.append(f"min_price: ${self.config.min_price:.2f}")
        if self.config.max_price:
            constraints.append(f"max_price: ${self.config.max_price:.2f}")
        if self.config.min_avg_dollar_volume_20d:
            constraints.append(f"min_avg_volume: ${self.config.min_avg_dollar_volume_20d:,.0f}")
        if self.config.max_spread_bps:
            constraints.append(f"max_spread: {self.config.max_spread_bps:.0f} bps")
        if self.config.exclude_symbols:
            constraints.append(f"excluded: {len(self.config.exclude_symbols)} symbols")
        if self.config.allow_symbols:
            constraints.append(f"allowed: {len(self.config.allow_symbols)} symbols")

        if constraints:
            mode = "STRICT" if self.config.strict_mode else "ADVISORY"
            logger.info(f"Execution gate active ({mode}): {', '.join(constraints)}")
        else:
            logger.info("Execution gate: No constraints configured (all symbols allowed)")

    def check_tradability(
        self,
        symbol: str,
        price: Decimal | float | None = None,
    ) -> TradabilityResult:
        """Check if a symbol is tradable under current constraints.

        Args:
            symbol: Ticker symbol to check
            price: Current price (optional, will use fundamentals cache if not provided)

        Returns:
            TradabilityResult with allowed flag and reason if blocked
        """
        # 1. Check allow list (bypass all other checks)
        if self.config.allow_symbols and symbol in self.config.allow_symbols:
            logger.debug(f"{symbol}: ALLOWED (in allow_symbols list)")
            return TradabilityResult(allowed=True, message="In allow list")

        # 2. Check exclude list (hard block)
        if self.config.exclude_symbols and symbol in self.config.exclude_symbols:
            logger.info(f"{symbol}: BLOCKED (in exclude_symbols list)")
            return TradabilityResult(
                allowed=False,
                reason=BlockReason.SYMBOL_EXCLUDED,
                message=f"Symbol {symbol} is in exclude list",
            )

        # 3. Get fundamentals (if needed for checks)
        fundamentals = self.fundamentals_cache.get_fundamentals(symbol)

        # Convert price to float for comparisons
        price_float = float(price) if price else None

        # If price not provided, try to get from fundamentals
        if price_float is None and fundamentals and fundamentals.price:
            price_float = fundamentals.price

        # 4. Check if fundamentals are required but unavailable
        if self.config.require_fundamentals and not fundamentals:
            logger.warning(f"{symbol}: BLOCKED (fundamentals unavailable, required mode)")
            return TradabilityResult(
                allowed=False,
                reason=BlockReason.FUNDAMENTALS_UNAVAILABLE,
                message=f"Fundamentals data unavailable for {symbol} (required in strict mode)",
                fundamentals_checked=True,
            )

        # 5. Market cap checks (if available)
        if fundamentals and fundamentals.market_cap_usd:
            market_cap = fundamentals.market_cap_usd

            # Min market cap check
            if self.config.min_market_cap_usd and market_cap < self.config.min_market_cap_usd:
                msg = (
                    f"Market cap ${market_cap:,.0f} below minimum "
                    f"${self.config.min_market_cap_usd:,.0f}"
                )
                logger.info(f"{symbol}: BLOCKED - {msg}")
                return TradabilityResult(
                    allowed=False,
                    reason=BlockReason.MARKET_CAP_TOO_LOW,
                    message=msg,
                    fundamentals_checked=True,
                )

            # Max market cap check
            if self.config.max_market_cap_usd and market_cap > self.config.max_market_cap_usd:
                msg = (
                    f"Market cap ${market_cap:,.0f} above maximum "
                    f"${self.config.max_market_cap_usd:,.0f}"
                )
                logger.info(f"{symbol}: BLOCKED - {msg}")
                return TradabilityResult(
                    allowed=False,
                    reason=BlockReason.MARKET_CAP_TOO_HIGH,
                    message=msg,
                    fundamentals_checked=True,
                )

        # 6. Price checks
        if price_float:
            # Min price check (avoid penny stocks)
            if self.config.min_price and price_float < self.config.min_price:
                msg = f"Price ${price_float:.2f} below minimum ${self.config.min_price:.2f}"
                logger.info(f"{symbol}: BLOCKED - {msg}")
                return TradabilityResult(
                    allowed=False,
                    reason=BlockReason.PRICE_TOO_LOW,
                    message=msg,
                )

            # Max price check
            if self.config.max_price and price_float > self.config.max_price:
                msg = f"Price ${price_float:.2f} above maximum ${self.config.max_price:.2f}"
                logger.info(f"{symbol}: BLOCKED - {msg}")
                return TradabilityResult(
                    allowed=False,
                    reason=BlockReason.PRICE_TOO_HIGH,
                    message=msg,
                )

        # 7. Liquidity check (if available)
        if (
            fundamentals
            and fundamentals.avg_dollar_volume_20d
            and self.config.min_avg_dollar_volume_20d
        ):
            avg_volume = fundamentals.avg_dollar_volume_20d
            if avg_volume < self.config.min_avg_dollar_volume_20d:
                msg = (
                    f"Avg dollar volume ${avg_volume:,.0f} below minimum "
                    f"${self.config.min_avg_dollar_volume_20d:,.0f}"
                )
                logger.info(f"{symbol}: BLOCKED - {msg}")
                return TradabilityResult(
                    allowed=False,
                    reason=BlockReason.LIQUIDITY_TOO_LOW,
                    message=msg,
                    fundamentals_checked=True,
                )

        # 8. Spread check (if available)
        if fundamentals and fundamentals.spread_bps and self.config.max_spread_bps:
            spread = fundamentals.spread_bps
            if spread > self.config.max_spread_bps:
                msg = (
                    f"Bid-ask spread {spread:.1f} bps above maximum "
                    f"{self.config.max_spread_bps:.1f} bps"
                )
                logger.info(f"{symbol}: BLOCKED - {msg}")
                return TradabilityResult(
                    allowed=False,
                    reason=BlockReason.SPREAD_TOO_WIDE,
                    message=msg,
                    fundamentals_checked=True,
                )

        # 9. All checks passed
        fundamentals_checked = fundamentals is not None
        logger.debug(
            f"{symbol}: ALLOWED (all checks passed, fundamentals_checked={fundamentals_checked})"
        )
        return TradabilityResult(
            allowed=True,
            message="Passed all tradability checks",
            fundamentals_checked=fundamentals_checked,
        )

    def get_blocked_symbols(self, symbols: list[str]) -> dict[str, str]:
        """Batch check symbols and return blocked ones with reasons.

        Args:
            symbols: List of symbols to check

        Returns:
            Dictionary mapping symbol -> block reason message (only blocked symbols)
        """
        blocked = {}
        for symbol in symbols:
            result = self.check_tradability(symbol)
            if not result.allowed:
                blocked[symbol] = result.message or "Unknown reason"
        return blocked

    def get_allowed_symbols(self, symbols: list[str]) -> list[str]:
        """Batch check symbols and return only allowed ones.

        Args:
            symbols: List of symbols to check

        Returns:
            List of symbols that pass tradability checks
        """
        allowed = []
        for symbol in symbols:
            result = self.check_tradability(symbol)
            if result.allowed:
                allowed.append(symbol)
        return allowed
