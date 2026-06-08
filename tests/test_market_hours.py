"""Tests for NYSE holiday/half-day-aware market hours (active runner path)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.app import market_hours
from src.app.market_hours import (
    get_next_market_open,
    is_market_hours,
    seconds_until_market_open,
)

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


# --- normal weekday -------------------------------------------------------


def test_normal_weekday_open():
    # Wednesday 2024-06-12, 11:00 ET -> open.
    assert is_market_hours(_et(2024, 6, 12, 11, 0)) is True


def test_normal_weekday_before_open_and_after_close():
    assert is_market_hours(_et(2024, 6, 12, 9, 0)) is False  # before 9:30
    assert is_market_hours(_et(2024, 6, 12, 16, 0)) is False  # at close (exclusive)
    assert is_market_hours(_et(2024, 6, 12, 16, 30)) is False  # after close


# --- weekend --------------------------------------------------------------


def test_weekend_closed():
    # Saturday 2024-06-15 and Sunday 2024-06-16, midday -> closed.
    assert is_market_hours(_et(2024, 6, 15, 11, 0)) is False
    assert is_market_hours(_et(2024, 6, 16, 11, 0)) is False


# --- holiday --------------------------------------------------------------


def test_nyse_holiday_closed():
    # Independence Day 2024-07-04 (Thursday) -> closed all day.
    assert is_market_hours(_et(2024, 7, 4, 11, 0)) is False
    # Christmas 2024-12-25 -> closed.
    assert is_market_hours(_et(2024, 12, 25, 11, 0)) is False


# --- half-day early close -------------------------------------------------


def test_half_day_early_close():
    # 2024-11-29 (day after Thanksgiving) closes early at 13:00 ET.
    assert is_market_hours(_et(2024, 11, 29, 12, 0)) is True  # before early close
    assert is_market_hours(_et(2024, 11, 29, 13, 0)) is False  # at early close
    assert is_market_hours(_et(2024, 11, 29, 13, 30)) is False  # after early close
    assert is_market_hours(_et(2024, 11, 29, 15, 30)) is False  # before regular 16:00


# --- next open / seconds-until -------------------------------------------


def test_next_open_skips_weekend():
    # From Saturday 2024-06-15 -> next open is Monday 2024-06-17 09:30 ET.
    nxt = get_next_market_open(_et(2024, 6, 15, 12, 0))
    assert (nxt.year, nxt.month, nxt.day) == (2024, 6, 17)
    assert (nxt.hour, nxt.minute) == (9, 30)


def test_next_open_skips_holiday():
    # From the July 4 2024 holiday -> next open is Friday 2024-07-05 09:30 ET.
    nxt = get_next_market_open(_et(2024, 7, 4, 11, 0))
    assert (nxt.year, nxt.month, nxt.day) == (2024, 7, 5)
    assert (nxt.hour, nxt.minute) == (9, 30)


def test_seconds_until_open_nonnegative_and_consistent():
    base = _et(2024, 6, 15, 12, 0)  # Saturday
    secs = seconds_until_market_open(base)
    nxt = get_next_market_open(base)
    assert secs == int((nxt - base).total_seconds())
    assert secs > 0


# --- fail-closed vs dry-run fallback on calendar error --------------------


def _force_calendar_error(monkeypatch):
    def _boom():
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(market_hours, "_get_calendar", _boom)


def test_calendar_error_fails_closed_for_real_orders(monkeypatch):
    _force_calendar_error(monkeypatch)
    # Even on a normal open weekday, a calendar error must read as CLOSED for real orders.
    assert is_market_hours(_et(2024, 6, 12, 11, 0), real_orders_possible=True) is False


def test_calendar_error_dry_run_falls_back_to_weekday_heuristic(monkeypatch):
    _force_calendar_error(monkeypatch)
    # Dry-run/shadow tolerate the weekday/regular-hours fallback.
    assert is_market_hours(_et(2024, 6, 12, 11, 0), real_orders_possible=False) is True
    assert is_market_hours(_et(2024, 6, 15, 11, 0), real_orders_possible=False) is False  # Sat


def test_calendar_error_next_open_fail_closed_repolls_soon(monkeypatch):
    _force_calendar_error(monkeypatch)
    base = _et(2024, 6, 12, 11, 0)
    secs = seconds_until_market_open(base, real_orders_possible=True)
    # Conservative short re-poll rather than a blind multi-hour sleep.
    assert 0 < secs <= market_hours._FAIL_CLOSED_RETRY_SECONDS
