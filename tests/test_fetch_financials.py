from datetime import date, datetime, timezone, timedelta

from scripts import fetch_financials
from scripts.fetch_financials import select_unreflected


TAIPEI = timezone(timedelta(hours=8))


def test_is_trading_day_delegates_datetime_to_authoritative_calendar(monkeypatch):
    seen = []

    def fake_calendar(day):
        seen.append(day)
        return False

    monkeypatch.setattr(fetch_financials, "is_twse_trading_day", fake_calendar)
    value = fetch_financials.is_trading_day(datetime(2026, 8, 25, 13, 30, tzinfo=TAIPEI))

    assert value is False
    assert seen == [date(2026, 8, 25)]


def test_att_and_fin_use_roc_timestamp_after_cutoff():
    cutoff = datetime(2026, 8, 21, 13, 30, tzinfo=TAIPEI)
    entries = [
        {"code": "2615", "date": "115/08/21", "time": "15:56:51"},
        {"code": "3008", "date": "115/08/20", "time": "15:37:47"},
    ]

    assert [row["code"] for row in select_unreflected("att", entries, cutoff)] == ["2615"]
    assert [row["code"] for row in select_unreflected("fin", entries, cutoff)] == ["2615"]


def test_revenue_uses_first_seen_after_cutoff_as_source_contract():
    cutoff = datetime(2026, 8, 21, 13, 30, tzinfo=TAIPEI)
    entries = [
        {"code": "1101", "first_seen": "2026-08-21 13:30:00", "is_new": True},
        {"code": "1102", "first_seen": "2026-08-21 13:30:01", "is_new": False, "is_updated": False},
        {"code": "1103", "first_seen": "2026-08-22 09:00:00", "is_new": False, "is_updated": False},
        {"code": "1104", "first_seen": "2026-08-20 18:00:00", "is_updated": True},
    ]

    assert [row["code"] for row in select_unreflected("rev", entries, cutoff)] == ["1102", "1103"]


def test_revenue_legacy_rows_without_first_seen_use_new_or_updated_flags():
    cutoff = datetime(2026, 8, 21, 13, 30, tzinfo=TAIPEI)
    entries = [
        {"code": "1101", "is_new": False, "is_updated": False},
        {"code": "1102", "is_new": True, "is_updated": False},
        {"code": "1103", "is_new": False, "is_updated": True},
    ]

    assert [row["code"] for row in select_unreflected("rev", entries, cutoff)] == ["1102", "1103"]
