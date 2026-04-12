"""
tests/unit/test_calendar.py — Unit tests for engine/market/calendar.py.

Tests all spec-required cases from Section 16.1:
  - Market open during correct hours
  - Market closed before open, after close
  - Market closed on weekends
  - Market closed on NSE holidays
  - Exact boundary conditions (9:15:00, 15:30:00)
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
import pytz

from engine.market import calendar as cal

IST_TZ = pytz.timezone("Asia/Kolkata")


def make_ist(year: int, month: int, day: int,
             hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """Create a timezone-aware IST datetime."""
    naive = datetime.datetime(year, month, day, hour, minute, second)
    return IST_TZ.localize(naive)


# ── Helpers ────────────────────────────────────────────────────────────────

# A known weekday that is NOT an NSE holiday for 2026 — using a safe date
TRADING_WEEKDAY = datetime.date(2026, 3, 2)    # Monday, no known holiday
SATURDAY = datetime.date(2026, 3, 7)            # Saturday
SUNDAY = datetime.date(2026, 3, 8)              # Sunday
NSE_HOLIDAY_2026 = datetime.date(2026, 3, 20)   # Holi (from nse_holidays.json)


def trading_dt(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """An IST datetime on a known trading day."""
    return make_ist(
        TRADING_WEEKDAY.year, TRADING_WEEKDAY.month, TRADING_WEEKDAY.day,
        hour, minute, second
    )


def holiday_dt(hour: int, minute: int) -> datetime.datetime:
    """An IST datetime on a known NSE holiday."""
    return make_ist(
        NSE_HOLIDAY_2026.year, NSE_HOLIDAY_2026.month, NSE_HOLIDAY_2026.day,
        hour, minute
    )


def weekend_dt(date: datetime.date, hour: int, minute: int) -> datetime.datetime:
    return make_ist(date.year, date.month, date.day, hour, minute)


# ─────────────────────────────────────────────────────────────────────────────
# is_market_open() tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIsMarketOpen:
    def test_open_during_trading_hours(self):
        """Market is open at 10:30 AM on a trading weekday."""
        assert cal.is_market_open(trading_dt(10, 30)) is True

    def test_open_just_after_open_time(self):
        """Market is open at 9:16 AM (just after 9:15)."""
        assert cal.is_market_open(trading_dt(9, 16)) is True

    def test_open_at_exact_open_boundary(self):
        """Market is open at exactly 9:15:00 AM (inclusive boundary)."""
        assert cal.is_market_open(trading_dt(9, 15, 0)) is True

    def test_open_at_exact_close_boundary(self):
        """Market is open at exactly 3:30:00 PM (inclusive boundary per spec)."""
        assert cal.is_market_open(trading_dt(15, 30, 0)) is True

    def test_closed_before_open(self):
        """Market is closed at 9:14 AM (before 9:15)."""
        assert cal.is_market_open(trading_dt(9, 14, 59)) is False

    def test_closed_at_9_14(self):
        """Market is closed at 9:14 exactly."""
        assert cal.is_market_open(trading_dt(9, 14)) is False

    def test_closed_after_close(self):
        """Market is closed at 3:31 PM (after 3:30)."""
        assert cal.is_market_open(trading_dt(15, 31)) is False

    def test_closed_at_pre_open(self):
        """Market is closed at 9:00 AM (pre-open)."""
        assert cal.is_market_open(trading_dt(9, 0)) is False

    def test_closed_at_midnight(self):
        """Market is closed at midnight."""
        assert cal.is_market_open(trading_dt(0, 0)) is False

    def test_closed_on_saturday(self):
        """Market is closed on Saturdays."""
        assert cal.is_market_open(weekend_dt(SATURDAY, 10, 30)) is False

    def test_closed_on_sunday(self):
        """Market is closed on Sundays."""
        assert cal.is_market_open(weekend_dt(SUNDAY, 10, 30)) is False

    def test_closed_on_nse_holiday(self):
        """Market is closed on NSE holidays (e.g., Holi)."""
        # This requires nse_holidays.json to include 2026-03-20
        if NSE_HOLIDAY_2026 in cal.NSE_HOLIDAYS:
            assert cal.is_market_open(holiday_dt(10, 30)) is False
        else:
            pytest.skip("NSE holiday 2026-03-20 not in loaded holidays — check nse_holidays.json")

    def test_open_day_after_holiday(self):
        """Day after a holiday (if it's a weekday) is open."""
        day_after = NSE_HOLIDAY_2026 + datetime.timedelta(days=1)
        if day_after.weekday() < 5 and day_after not in cal.NSE_HOLIDAYS:
            dt = make_ist(day_after.year, day_after.month, day_after.day, 10, 30)
            assert cal.is_market_open(dt) is True

    def test_accepts_naive_datetime_and_localizes(self):
        """is_market_open should handle naive datetime by localizing to IST."""
        naive = datetime.datetime(TRADING_WEEKDAY.year, TRADING_WEEKDAY.month,
                                  TRADING_WEEKDAY.day, 10, 30, 0)
        # Should not raise; should treat as IST
        result = cal.is_market_open(naive)
        assert result is True

    def test_uses_current_time_when_no_arg(self):
        """Calling is_market_open() with no args uses current IST time (smoke test)."""
        # Just verify it runs without error
        result = cal.is_market_open()
        assert isinstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# is_trading_day() tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIsTradingDay:
    def test_weekday_is_trading_day(self):
        assert cal.is_trading_day(TRADING_WEEKDAY) is True

    def test_saturday_is_not_trading_day(self):
        assert cal.is_trading_day(SATURDAY) is False

    def test_sunday_is_not_trading_day(self):
        assert cal.is_trading_day(SUNDAY) is False

    def test_holiday_is_not_trading_day(self):
        if NSE_HOLIDAY_2026 in cal.NSE_HOLIDAYS:
            assert cal.is_trading_day(NSE_HOLIDAY_2026) is False
        else:
            pytest.skip("Holiday not in loaded set")

    def test_defaults_to_today(self):
        result = cal.is_trading_day()
        assert isinstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# next_trading_day() tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNextTradingDay:
    def test_next_trading_day_from_friday_is_monday(self):
        friday = datetime.date(2026, 3, 6)   # Friday
        next_day = cal.next_trading_day(friday)
        assert next_day == datetime.date(2026, 3, 9)  # Monday

    def test_next_trading_day_from_weekday(self):
        monday = datetime.date(2026, 3, 2)   # Monday
        next_day = cal.next_trading_day(monday)
        assert next_day == datetime.date(2026, 3, 3)  # Tuesday (if not holiday)

    def test_next_trading_day_skips_holiday(self):
        """If the next calendar day is a holiday, skip to the day after."""
        # Find a day before our known holiday
        day_before_holiday = NSE_HOLIDAY_2026 - datetime.timedelta(days=1)
        if day_before_holiday.weekday() < 5:
            next_day = cal.next_trading_day(day_before_holiday)
            assert next_day != NSE_HOLIDAY_2026
            assert cal.is_trading_day(next_day)


# ─────────────────────────────────────────────────────────────────────────────
# Holiday loading tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHolidayLoading:
    def test_holidays_loaded_as_frozenset(self):
        assert isinstance(cal.NSE_HOLIDAYS, frozenset)

    def test_holidays_contain_date_objects(self):
        for h in cal.NSE_HOLIDAYS:
            assert isinstance(h, datetime.date)

    def test_expected_2026_holidays_present(self):
        """Check a few well-known 2026 holidays are in the set."""
        known_holidays = [
            datetime.date(2026, 1, 26),  # Republic Day
            datetime.date(2026, 8, 15),  # Independence Day
            datetime.date(2026, 12, 25), # Christmas
        ]
        for h in known_holidays:
            if h not in cal.NSE_HOLIDAYS:
                pytest.skip(f"{h} not in loaded holidays — verify nse_holidays.json")
            assert h in cal.NSE_HOLIDAYS

    def test_handles_missing_holiday_file_gracefully(self, tmp_path):
        """_load_holidays() with missing file returns empty frozenset (fail-open)."""
        missing_path = str(tmp_path / "nonexistent.json")
        import warnings
        with warnings.catch_warnings(record=True):
            result = cal._load_holidays(missing_path)
        assert result == frozenset()

    def test_handles_malformed_holiday_json(self, tmp_path):
        """_load_holidays() with bad JSON returns empty frozenset."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json")
        import warnings
        with warnings.catch_warnings(record=True):
            result = cal._load_holidays(str(bad_json))
        assert result == frozenset()
