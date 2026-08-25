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



def _official_payload():
    return {
        "stat": "ok",
        "date": "20260101",
        "title": "115 年市場開休市日期",
        "fields": ["日期", "名稱", "說明"],
        "data": [
            ["2026-01-01", "中華民國開國紀念日", "依規定放假1日。"],
            ["2026-02-11", "農曆春節前最後交易日", "農曆春節前最後交易。"],
            ["2026-02-12", "市場無交易，僅辦理結算交割作業", ""],
            ["2026-02-15", "農曆除夕及春節", "依規定放假5日。"],
            ["2026-02-16", "農曆除夕及春節", "依規定放假5日。"],
        ],
    }


def test_normalize_official_calendar_excludes_weekend_rows_and_marks_provenance():
    from scripts.trading_calendar import normalize_official_payload

    normalized = normalize_official_payload(_official_payload(), 2026, fetched_at="2026-01-01T00:00:00+08:00")
    assert normalized["schema_version"] == "twse-holiday-calendar.v2"
    assert normalized["source"]["url"].endswith("/holidaySchedule/holidaySchedule")
    assert normalized["source"]["query"] == {"yy": "2026"}
    assert normalized["years"]["2026"]["holidays"] == ["2026-01-01", "2026-02-12", "2026-02-16"]
    assert any(row["date"] == "2026-02-15" and not row["is_trading_day"] for row in normalized["years"]["2026"]["observed_rows"])


def test_update_calendar_atomically_merges_year_and_preserves_manual_overrides(tmp_path):
    from scripts.trading_calendar import update_calendar

    output = tmp_path / "twse_holidays.json"
    output.write_text(json.dumps({"holidays_2025": ["2025-01-01"], "manual_overrides": ["2026-07-24"]}), encoding="utf-8")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return _official_payload()

    def fake_get(*args, **kwargs):
        assert kwargs["params"] == {"yy": "2026"}
        return FakeResponse()

    update_calendar(2026, output_path=output, get_fn=fake_get)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["years"]["2025"]["holidays"] == ["2025-01-01"]
    assert "2026-02-16" in payload["years"]["2026"]["holidays"]
    assert payload["manual_overrides"] == ["2026-07-24"]
    assert not output.with_suffix(".json.tmp").exists()


def test_missing_calendar_year_warns_and_raises_instead_of_inferring_weekday(tmp_path, capsys):
    from scripts.trading_calendar import TradingCalendarUnavailable

    path = tmp_path / "twse_holidays.json"
    path.write_text(json.dumps({"years": {"2025": {"holidays": []}}, "manual_overrides": []}), encoding="utf-8")
    with pytest.raises(TradingCalendarUnavailable):
        is_twse_trading_day(date(2026, 8, 24), config_path=path)
    assert "缺少 2026 年" in capsys.readouterr().err


def test_malformed_calendar_date_is_rejected(tmp_path):
    from scripts.trading_calendar import TradingCalendarError, load_twse_holidays

    path = tmp_path / "twse_holidays.json"
    path.write_text(json.dumps({"years": {"2026": {"holidays": ["not-a-date"]}}}), encoding="utf-8")
    with pytest.raises(TradingCalendarError):
        load_twse_holidays(path)
