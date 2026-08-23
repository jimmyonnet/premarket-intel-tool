import tempfile
import json
from datetime import date
from pathlib import Path
import pytest

from scripts.trading_calendar import (
    load_twse_holidays,
    is_twse_trading_day,
    get_next_trading_day,
    get_current_trading_day,
)


def test_trading_calendar_statutory_holidays_and_weekends():
    """Verify statutory holidays and weekend market closures."""
    holidays = {
        "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18",
        "2026-02-19", "2026-02-20", "2026-02-27", "2026-04-03",
        "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25",
        "2026-10-09"
    }

    # Weekend (Saturday: 2026-08-22, Sunday: 2026-08-23)
    assert not is_twse_trading_day(date(2026, 8, 22), holidays)
    assert not is_twse_trading_day(date(2026, 8, 23), holidays)

    # Regular trading weekday (Monday: 2026-08-24)
    assert is_twse_trading_day(date(2026, 8, 24), holidays)

    # Statutory holiday (Lunar New Year: 2026-02-16 Monday)
    assert not is_twse_trading_day(date(2026, 2, 16), holidays)

    # Labor Day (2026-05-01 Friday)
    assert not is_twse_trading_day(date(2026, 5, 1), holidays)


def test_trading_calendar_manual_overrides():
    """Verify manual override closures (e.g. typhoon closure)."""
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
        data = {
            "holidays_2026": ["2026-01-01"],
            "manual_overrides": ["2026-07-24"]  # Typhoon day
        }
        tf.write(json.dumps(data))
        tf.flush()
        temp_path = tf.name

    try:
        holidays = load_twse_holidays(temp_path)
        assert "2026-07-24" in holidays
        assert not is_twse_trading_day(date(2026, 7, 24), holidays)
        # Normal day
        assert is_twse_trading_day(date(2026, 7, 23), holidays)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_get_next_and_current_trading_day():
    """Verify next and current trading day calculations crossing weekends and holidays."""
    holidays = {"2026-05-01"}  # 2026-05-01 is Friday (Labor day)

    # Friday 2026-05-01 holiday -> Next trading day is Monday 2026-05-04
    nxt = get_next_trading_day(date(2026, 4, 30), holidays)
    assert nxt == date(2026, 5, 4)

    # From Sunday 2026-08-23 -> Next is Monday 2026-08-24
    assert get_next_trading_day(date(2026, 8, 23), holidays) == date(2026, 8, 24)

    # From Saturday 2026-08-22 -> Current is Friday 2026-08-21
    assert get_current_trading_day(date(2026, 8, 22), holidays) == date(2026, 8, 21)
