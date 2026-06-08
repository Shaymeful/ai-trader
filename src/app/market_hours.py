"""NYSE market-hours checks (holiday- and half-day-aware).

The active runner path (``src/app/runner.py``) uses these helpers to decide when
to trade. Regular sessions are 9:30-16:00 ET; the NYSE calendar
(``pandas_market_calendars``) supplies holidays (closed) and early-close days
(e.g. 13:00 ET on the day after Thanksgiving and several half-days), so we never
rely on a naive weekday/time window for real orders.

Fail-closed policy: if the exchange-calendar lookup errors while real orders could
be placed, ``is_market_hours`` returns ``False`` (treat as closed → do not trade).
Only in non-real-order contexts (dry-run / shadow) do we tolerate a fallback to the
simple weekday/time heuristic so development and backtest-style runs keep working.
"""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("ai-trader")

_ET = ZoneInfo("America/New_York")

# Regular session bounds — used only by the dry-run fallback heuristic. Real-order
# decisions use the exchange calendar, which also encodes early-close times.
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)

# How far ahead to scan when finding the next session open.
_LOOKAHEAD_DAYS = 14
# Conservative re-poll interval (seconds) when the calendar errors on the
# real-order path: stay closed (fail closed) but re-check soon.
_FAIL_CLOSED_RETRY_SECONDS = 300

_calendar = None


def _get_calendar():
    """Lazily build and cache the NYSE exchange calendar."""
    global _calendar
    if _calendar is None:
        import pandas_market_calendars as mcal

        _calendar = mcal.get_calendar("NYSE")
    return _calendar


def _to_et(current_time: datetime | None) -> datetime:
    """Normalize an input datetime to a tz-aware America/New_York datetime."""
    if current_time is None:
        return datetime.now(_ET)
    if current_time.tzinfo is None:
        # Assume a naive datetime is already expressed in ET.
        return current_time.replace(tzinfo=_ET)
    return current_time.astimezone(_ET)


def _session_bounds(dt_et: datetime) -> tuple[datetime, datetime] | None:
    """Return (open, close) ET datetimes for the date of ``dt_et``.

    Returns ``None`` if that date is not a trading day (weekend or holiday).
    May raise if the calendar lookup fails — callers decide fail-open vs closed.
    """
    cal = _get_calendar()
    date_str = dt_et.strftime("%Y-%m-%d")
    sched = cal.schedule(start_date=date_str, end_date=date_str)
    if sched.empty:
        return None
    open_et = sched.iloc[0]["market_open"].tz_convert(_ET).to_pydatetime()
    close_et = sched.iloc[0]["market_close"].tz_convert(_ET).to_pydatetime()
    return open_et, close_et


def _next_session_open(dt_et: datetime) -> datetime:
    """Return the next session open (ET) strictly after ``dt_et``.

    May raise if the calendar lookup fails.
    """
    cal = _get_calendar()
    start = dt_et.strftime("%Y-%m-%d")
    end = (dt_et + timedelta(days=_LOOKAHEAD_DAYS)).strftime("%Y-%m-%d")
    sched = cal.schedule(start_date=start, end_date=end)
    for ts in sched["market_open"]:
        open_et = ts.tz_convert(_ET).to_pydatetime()
        if open_et > dt_et:
            return open_et
    # Should not happen within the lookahead window; signal to caller.
    raise RuntimeError(f"No NYSE session open found within {_LOOKAHEAD_DAYS} days of {dt_et}")


# ---------------------------------------------------------------------------
# Dry-run / shadow fallback heuristic (weekday + regular hours, no holidays)
# ---------------------------------------------------------------------------


def _fallback_is_open(dt_et: datetime) -> bool:
    if dt_et.weekday() >= 5:  # Saturday/Sunday
        return False
    return _REGULAR_OPEN <= dt_et.time() < _REGULAR_CLOSE


def _fallback_next_open(dt_et: datetime) -> datetime:
    next_open = dt_et.replace(
        hour=_REGULAR_OPEN.hour, minute=_REGULAR_OPEN.minute, second=0, microsecond=0
    )
    if dt_et >= next_open:
        next_open += timedelta(days=1)
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)
    return next_open


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_market_hours(
    current_time: datetime | None = None,
    *,
    real_orders_possible: bool = False,
) -> bool:
    """Return True if the NYSE is open for regular trading at ``current_time``.

    Holiday- and half-day-aware via the exchange calendar. On a calendar error,
    fails closed (returns False) when ``real_orders_possible`` is True; otherwise
    falls back to a weekday/regular-hours heuristic for dry-run/shadow use.
    """
    now = _to_et(current_time)
    try:
        bounds = _session_bounds(now)
    except Exception as e:
        logger.error(f"NYSE calendar lookup failed: {e}")
        if real_orders_possible:
            logger.error("Failing closed: treating market as CLOSED (no orders).")
            return False
        logger.warning("Dry-run fallback: using weekday/regular-hours heuristic.")
        return _fallback_is_open(now)

    if bounds is None:
        return False  # weekend or holiday
    market_open, market_close = bounds
    return market_open <= now < market_close


def get_next_market_open(
    current_time: datetime | None = None,
    *,
    real_orders_possible: bool = False,
) -> datetime:
    """Return the next NYSE session open (ET) strictly after ``current_time``."""
    now = _to_et(current_time)
    try:
        return _next_session_open(now)
    except Exception as e:
        logger.error(f"NYSE calendar lookup failed while finding next open: {e}")
        if real_orders_possible:
            # Fail closed: re-poll soon rather than sleeping blindly for hours.
            return now + timedelta(seconds=_FAIL_CLOSED_RETRY_SECONDS)
        logger.warning("Dry-run fallback: using weekday/regular-hours heuristic.")
        return _fallback_next_open(now)


def seconds_until_market_open(
    current_time: datetime | None = None,
    *,
    real_orders_possible: bool = False,
) -> int:
    """Return seconds until the next NYSE session open (never negative)."""
    now = _to_et(current_time)
    next_open = get_next_market_open(now, real_orders_possible=real_orders_possible)
    return max(0, int((next_open - now).total_seconds()))
