#!/usr/bin/env python3
"""Diagnose market data fetch issue."""

import logging
from src.app.config import load_config_with_yaml
from src.app.data_providers.hourly_provider import HourlyMarketDataProvider
from src.app.universe_registry import UniverseRegistry

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-trader")

# Load config
config = load_config_with_yaml()

# Get universe
print("Loading universe...")
registry = UniverseRegistry()
resolution = registry.resolve()
universe = resolution.symbols

print(f"Universe: {len(universe)} symbols")
print(f"Symbols: {', '.join(universe)}")
print()

# Create provider
print("Creating Hourly Market Data Provider...")
provider = HourlyMarketDataProvider(
    api_key=config.alpaca_api_key,
    secret_key=config.alpaca_secret_key,
    lookback_bars=50,
    ma_period=20,
)
print()

# Fetch data
print("Fetching market data...")
market_data = provider.get_market_data(universe)
print()

# Report results
print(f"Market data returned for {len(market_data)} symbols")
if market_data:
    for symbol, data in market_data.items():
        print(f"  {symbol}: price={data.get('price', 'N/A')}, bars={data.get('bars_count', 'N/A')}")
else:
    print("  No data returned!")

missing = [s for s in universe if s not in market_data]
if missing:
    print(f"\nMissing data for {len(missing)} symbols: {', '.join(missing)}")
