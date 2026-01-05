"""Test script to verify Alpaca data API credentials."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv
import os

# Load environment (.env overrides system variables)
load_dotenv(override=True)

# Get credentials
api_key = os.getenv("ALPACA_PAPER_KEY_ID")
secret_key = os.getenv("ALPACA_PAPER_SECRET_KEY")

print("=" * 80)
print("ALPACA DATA API CREDENTIAL TEST")
print("=" * 80)
print(f"API Key: {api_key[:10]}... (masked)")
print(f"Secret Key: {'*' * 10} (masked)")
print()

# Initialize client
print("Initializing StockHistoricalDataClient...")
try:
    client = StockHistoricalDataClient(api_key, secret_key)
    print("[OK] Client initialized")
except Exception as e:
    print(f"[ERROR] Failed to initialize client: {e}")
    exit(1)

# Test 1: Fetch recent bars with IEX feed
print()
print("Test 1: Fetching 1 hour bar for SPY with IEX feed...")
try:
    eastern = ZoneInfo("America/New_York")
    end = datetime.now(eastern)
    start = end - timedelta(days=2)

    request = StockBarsRequest(
        symbol_or_symbols=["SPY"],
        timeframe=TimeFrame.Hour,
        start=start,
        end=end,
        feed="iex",
    )

    response = client.get_stock_bars(request)
    if response and "SPY" in response.data:
        bars = response.data["SPY"]
        print(f"[OK] Fetched {len(bars)} bars for SPY")
        if bars:
            latest = bars[-1]
            print(f"     Latest bar: close=${latest.close}, time={latest.timestamp}")
    else:
        print("[WARNING] No data returned for SPY")
except Exception as e:
    print(f"[ERROR] Test 1 failed: {e}")
    print()
    print("This likely means:")
    print("  - Free paper tier doesn't have IEX feed access")
    print("  - Data subscription not enabled on paper account")
    print("  - Credentials don't have data API permissions")

# Test 2: Try without specifying feed
print()
print("Test 2: Fetching 1 hour bar for SPY without specifying feed...")
try:
    eastern = ZoneInfo("America/New_York")
    end = datetime.now(eastern)
    start = end - timedelta(days=2)

    request = StockBarsRequest(
        symbol_or_symbols=["SPY"],
        timeframe=TimeFrame.Hour,
        start=start,
        end=end,
    )

    response = client.get_stock_bars(request)
    if response and "SPY" in response.data:
        bars = response.data["SPY"]
        print(f"[OK] Fetched {len(bars)} bars for SPY")
        if bars:
            latest = bars[-1]
            print(f"     Latest bar: close=${latest.close}, time={latest.timestamp}")
    else:
        print("[WARNING] No data returned for SPY")
except Exception as e:
    print(f"[ERROR] Test 2 failed: {e}")

print()
print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
