"""Test market hours checking."""

from datetime import datetime
from zoneinfo import ZoneInfo
from src.app.market_hours import is_market_hours, get_next_market_open, seconds_until_market_open

now = datetime.now(ZoneInfo("America/New_York"))

print("=" * 80)
print("MARKET HOURS TEST")
print("=" * 80)
print(f"Current time (ET): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"Day of week: {now.strftime('%A')}")
print(f"Market open: {is_market_hours(now)}")
print()

if not is_market_hours(now):
    next_open = get_next_market_open(now)
    seconds_until = seconds_until_market_open(now)
    hours_until = seconds_until / 3600

    print(f"Next market open: {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Time until open: {hours_until:.1f} hours ({seconds_until / 60:.0f} minutes)")
else:
    print("Market is currently OPEN")
    print("Market hours: Monday-Friday, 9:30 AM - 4:00 PM ET")

print("=" * 80)
