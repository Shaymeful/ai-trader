"""Fundamentals cache for market cap, price, and liquidity data.

This module provides a lightweight caching layer for ticker fundamentals data
(market cap, average volume, etc.) used by the execution gate for tradability filtering.

Design:
- In-memory cache with disk persistence
- TTL-based expiration (default 24 hours)
- Manual mapping support for symbols without API access
- Stub interface for future API integration (Polygon, IEX, FMP)

Data sources (priority order):
1. Manual mappings (override file)
2. In-memory cache (if not expired)
3. Disk cache (if not expired)
4. API fetch (future integration)
5. Fallback to unknown (no block, just log warning)
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai-trader")


@dataclass
class TickerFundamentals:
    """Fundamental data for a single ticker."""

    symbol: str
    market_cap_usd: float | None = None  # Market capitalization in USD
    avg_dollar_volume_20d: float | None = None  # 20-day average dollar volume
    price: float | None = None  # Recent price (for validation)
    spread_bps: float | None = None  # Bid-ask spread in basis points
    last_updated: str | None = None  # ISO timestamp of last update

    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if data is older than TTL."""
        if not self.last_updated:
            return True
        try:
            updated_dt = datetime.fromisoformat(self.last_updated)
            age = datetime.now(UTC) - updated_dt
            return age > timedelta(hours=ttl_hours)
        except Exception:
            return True


class FundamentalsCache:
    """Cache for ticker fundamentals with in-memory + disk persistence."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        manual_mappings_path: Path | None = None,
        ttl_hours: int = 24,
    ):
        """Initialize fundamentals cache.

        Args:
            cache_dir: Directory for disk cache (default: data/cache)
            manual_mappings_path: Path to manual overrides JSON (default: data/cache/fundamentals_manual.json)
            ttl_hours: Cache TTL in hours (default: 24)
        """
        # Set default paths
        if cache_dir is None:
            repo_root = Path(__file__).resolve().parents[2]
            cache_dir = repo_root / "data" / "cache"

        if manual_mappings_path is None:
            manual_mappings_path = cache_dir / "fundamentals_manual.json"

        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "fundamentals.json"
        self.manual_mappings_path = manual_mappings_path
        self.ttl_hours = ttl_hours

        # In-memory cache
        self._cache: dict[str, TickerFundamentals] = {}
        self._manual_mappings: dict[str, TickerFundamentals] = {}

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load caches
        self._load_manual_mappings()
        self._load_disk_cache()

    def _load_manual_mappings(self) -> None:
        """Load manual fundamentals mappings from JSON file."""
        if not self.manual_mappings_path.exists():
            logger.info(f"No manual mappings file found at {self.manual_mappings_path}")
            return

        try:
            with open(self.manual_mappings_path) as f:
                data = json.load(f)

            for symbol, fund_data in data.items():
                # Skip comment fields
                if symbol.startswith("_"):
                    continue

                # Skip if fund_data is not a dict (e.g., string comments)
                if not isinstance(fund_data, dict):
                    continue

                # Add last_updated if not present
                if "last_updated" not in fund_data:
                    fund_data["last_updated"] = datetime.now(UTC).isoformat()

                self._manual_mappings[symbol] = TickerFundamentals(**fund_data)

            logger.info(f"Loaded {len(self._manual_mappings)} manual fundamental mappings")
        except Exception as e:
            logger.error(f"Failed to load manual mappings: {e}")

    def _load_disk_cache(self) -> None:
        """Load fundamentals from disk cache."""
        if not self.cache_file.exists():
            logger.info(f"No disk cache found at {self.cache_file}")
            return

        try:
            with open(self.cache_file) as f:
                data = json.load(f)

            for symbol, fund_data in data.items():
                fundamentals = TickerFundamentals(**fund_data)
                # Only load if not expired
                if not fundamentals.is_expired(self.ttl_hours):
                    self._cache[symbol] = fundamentals

            logger.info(
                f"Loaded {len(self._cache)} ticker fundamentals from disk cache (expired entries discarded)"
            )
        except Exception as e:
            logger.error(f"Failed to load disk cache: {e}")

    def _save_disk_cache(self) -> None:
        """Save current in-memory cache to disk (atomic write)."""
        try:
            # Prepare data (exclude expired)
            cache_data = {}
            for symbol, fundamentals in self._cache.items():
                if not fundamentals.is_expired(self.ttl_hours):
                    cache_data[symbol] = asdict(fundamentals)

            # Atomic write
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(cache_data, f, indent=2)

            temp_file.replace(self.cache_file)
            logger.debug(f"Saved {len(cache_data)} ticker fundamentals to disk cache")
        except Exception as e:
            logger.error(f"Failed to save disk cache: {e}")

    def get_fundamentals(self, symbol: str) -> TickerFundamentals | None:
        """Get fundamentals for a symbol.

        Lookup order:
        1. Manual mappings (highest priority, never expire)
        2. In-memory cache (if not expired)
        3. Disk cache (reload if needed)
        4. API fetch (future - stub for now)
        5. Return None if not found

        Args:
            symbol: Ticker symbol

        Returns:
            TickerFundamentals if found, None otherwise
        """
        # 1. Check manual mappings (override everything)
        if symbol in self._manual_mappings:
            return self._manual_mappings[symbol]

        # 2. Check in-memory cache
        if symbol in self._cache:
            fundamentals = self._cache[symbol]
            if not fundamentals.is_expired(self.ttl_hours):
                return fundamentals
            else:
                # Expired, remove from cache
                del self._cache[symbol]

        # 3. Disk cache already loaded at init, so skip

        # 4. API fetch (future integration - stub)
        # fundamentals = self._fetch_from_api(symbol)
        # if fundamentals:
        #     self._cache[symbol] = fundamentals
        #     self._save_disk_cache()
        #     return fundamentals

        # 5. Not found
        return None

    def get_market_cap(self, symbol: str) -> float | None:
        """Get market cap for a symbol (convenience method).

        Args:
            symbol: Ticker symbol

        Returns:
            Market cap in USD, or None if not available
        """
        fundamentals = self.get_fundamentals(symbol)
        return fundamentals.market_cap_usd if fundamentals else None

    def get_avg_dollar_volume(self, symbol: str) -> float | None:
        """Get 20-day average dollar volume for a symbol (convenience method).

        Args:
            symbol: Ticker symbol

        Returns:
            Average dollar volume, or None if not available
        """
        fundamentals = self.get_fundamentals(symbol)
        return fundamentals.avg_dollar_volume_20d if fundamentals else None

    def set_fundamentals(self, fundamentals: TickerFundamentals, save_to_disk: bool = True) -> None:
        """Manually set fundamentals for a symbol.

        Args:
            fundamentals: TickerFundamentals object
            save_to_disk: If True, persist to disk cache
        """
        # Update timestamp
        if not fundamentals.last_updated:
            fundamentals.last_updated = datetime.now(UTC).isoformat()

        self._cache[fundamentals.symbol] = fundamentals

        if save_to_disk:
            self._save_disk_cache()

    def bulk_set_fundamentals(self, fundamentals_list: list[TickerFundamentals]) -> None:
        """Set multiple fundamentals at once and save to disk.

        More efficient than calling set_fundamentals repeatedly.

        Args:
            fundamentals_list: List of TickerFundamentals objects
        """
        for fundamentals in fundamentals_list:
            if not fundamentals.last_updated:
                fundamentals.last_updated = datetime.now(UTC).isoformat()
            self._cache[fundamentals.symbol] = fundamentals

        self._save_disk_cache()

    def _fetch_from_api(self, symbol: str) -> TickerFundamentals | None:
        """Stub for future API integration.

        This method can be extended to fetch from:
        - Polygon.io API
        - IEX Cloud API
        - Financial Modeling Prep (FMP) API
        - Alpaca Trading API (limited fundamentals)

        Args:
            symbol: Ticker symbol

        Returns:
            TickerFundamentals if fetched successfully, None otherwise
        """
        # TODO: Implement API integration
        # Example implementation outline:
        #
        # try:
        #     response = requests.get(
        #         f"https://api.polygon.io/v3/reference/tickers/{symbol}",
        #         params={"apiKey": self.api_key}
        #     )
        #     data = response.json()
        #     return TickerFundamentals(
        #         symbol=symbol,
        #         market_cap_usd=data.get("market_cap"),
        #         price=data.get("price"),
        #         last_updated=datetime.now(UTC).isoformat()
        #     )
        # except Exception as e:
        #     logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
        #     return None

        return None

    def clear_cache(self) -> None:
        """Clear in-memory cache (does not affect disk cache or manual mappings)."""
        self._cache.clear()
        logger.info("Cleared in-memory fundamentals cache")

    def reload(self) -> None:
        """Reload both manual mappings and disk cache."""
        self._cache.clear()
        self._manual_mappings.clear()
        self._load_manual_mappings()
        self._load_disk_cache()
        logger.info("Reloaded fundamentals cache from disk")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (counts, hit rates, etc.)
        """
        return {
            "manual_mappings_count": len(self._manual_mappings),
            "cached_symbols_count": len(self._cache),
            "ttl_hours": self.ttl_hours,
            "cache_file": str(self.cache_file),
            "manual_mappings_file": str(self.manual_mappings_path),
        }
