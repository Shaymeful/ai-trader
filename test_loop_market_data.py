#!/usr/bin/env python3
"""Test market data fetch in loop-like conditions."""

import sys
import os

# Replicate loop environment
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.app.data_providers.hourly_provider import HourlyMarketDataProvider
from src.app.universe_registry import UniverseRegistry

print("=" * 80)
print("TESTING MARKET DATA IN LOOP-LIKE CONDITIONS")
print("=" * 80)
print()

# Load config exactly as loop does
config = load_config_with_yaml()
print(f"Config loaded: alpaca_api_key present = {bool(config.alpaca_api_key)}")
print(f"Config loaded: alpaca_secret_key present = {bool(config.alpaca_secret_key)}")
print()

# Get universe exactly as loop does
registry = UniverseRegistry()
resolution = registry.resolve()
universe = resolution.symbols
print(f"Universe: {len(universe)} symbols")
print(f"Symbols: {', '.join(universe)}")
print()

# Create provider exactly as loop does
print("Creating provider as loop does...")
if config.alpaca_api_key and config.alpaca_secret_key:
    print(f"Using Alpaca hourly data provider (data_url: {config.alpaca_data_base_url})")
    provider = HourlyMarketDataProvider(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        lookback_bars=50,
        ma_period=20,
    )
else:
    print("ERROR: No credentials!")
    sys.exit(1)
print()

# Fetch data exactly as loop does
print("Fetching market data...")
try:
    market_data = provider.get_market_data(universe)
    print(f"SUCCESS: Received data for {len(market_data)} symbols")

    if market_data:
        for symbol, data in list(market_data.items())[:3]:
            print(f"  {symbol}: price={data.get('price')}, bars={data.get('bars_count')}")

    missing = [s for s in universe if s not in market_data]
    if missing:
        print(f"MISSING: {', '.join(missing)}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
