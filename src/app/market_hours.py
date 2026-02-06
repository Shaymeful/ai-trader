"""Market hours checking utilities."""

from datetime import datetime, time
from zoneinfo import ZoneInfo


def is_market_hours(
    current_time: datetime | None = None,
    market_open_hour: int = 9,
    market_open_minute: int = 30,
    market_close_hour: int = 16,
    market_close_minute: int = 0,
) -> bool:
    """
    Check if current time is within market hours (US Eastern).

    Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday

    Args:
        current_time: Time to check (defaults to now in ET)
        market_open_hour: Market open hour (default: 9)
        market_open_minute: Market open minute (default: 30)
        market_close_hour: Market close hour (default: 16)
        market_close_minute: Market close minute (default: 0)

    Returns:
        True if within market hours, False otherwise
    """
    if current_time is None:
        current_time = datetime.now(ZoneInfo("America/New_York"))
    elif current_time.tzinfo is None:
        # Assume naive datetime is in ET
        current_time = current_time.replace(tzinfo=ZoneInfo("America/New_York"))

    # Check if it's a weekday (Monday=0, Sunday=6)
    if current_time.weekday() >= 5:  # Saturday or Sunday
        return False

    # Check if current time is within market hours
    market_open = time(market_open_hour, market_open_minute)
    market_close = time(market_close_hour, market_close_minute)
    current_time_only = current_time.time()

    return market_open <= current_time_only < market_close


def get_next_market_open(
    current_time: datetime | None = None,
    market_open_hour: int = 9,
    market_open_minute: int = 30,
) -> datetime:
    """
    Get the next market open time.

    Args:
        current_time: Time to check from (defaults to now in ET)
        market_open_hour: Market open hour (default: 9)
        market_open_minute: Market open minute (default: 30)

    Returns:
        datetime of next market open
    """
    if current_time is None:
        current_time = datetime.now(ZoneInfo("America/New_York"))
    elif current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=ZoneInfo("America/New_York"))

    # Start with today's market open
    next_open = current_time.replace(
        hour=market_open_hour,
        minute=market_open_minute,
        second=0,
        microsecond=0,
    )

    # If we're past today's open, move to next day
    if current_time >= next_open:
        next_open = next_open.replace(day=next_open.day + 1)

    # Skip weekends
    while next_open.weekday() >= 5:  # Saturday or Sunday
        next_open = next_open.replace(day=next_open.day + 1)

    return next_open


def seconds_until_market_open(
    current_time: datetime | None = None,
    market_open_hour: int = 9,
    market_open_minute: int = 30,
) -> int:
    """
    Get seconds until next market open.

    Args:
        current_time: Time to check from (defaults to now in ET)
        market_open_hour: Market open hour (default: 9)
        market_open_minute: Market open minute (default: 30)

    Returns:
        Seconds until next market open
    """
    if current_time is None:
        current_time = datetime.now(ZoneInfo("America/New_York"))

    next_open = get_next_market_open(current_time, market_open_hour, market_open_minute)
    return int((next_open - current_time).total_seconds())
