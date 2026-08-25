from datetime import date
import json
from pathlib import Path

from scripts.opening_prediction.generate_forecast import generate
from scripts.opening_prediction.model import build_forecast, direction_for_change, gap_label, load_model_config


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / "data" / "trading_calendar" / "twse_holidays.json"
CONFIG = ROOT / "config" / "opening_model_v1.json"


def _inputs(tmp_path: Path):
    indices = {
        "us_indices": {
            "nasdaq": {"change_pct": 1.0, "updated_at": "2026-08-25T05:00:00+08:00", "source_url": "https://example.test/nasdaq"},
            "sp500": {"change_pct": 0.5, "updated_at": "2026-08-25T05:00:00+08:00", "source_url": "https://example.test/sp500"},
            "dow": {"change_pct": 0.2, "updated_at": "2026-08-25T05:00:00+08:00", "source_url": "https://example.test/dow"},
        }
    }
    night = {"latest": {"change": 200, "collected_at": "2026-08-25T05:00:00+08:00"}}
    twse = {"twii": {"price": 45000}}
    reference = {
        "status": "ok",
        "previous_close": 45000,
        "source": {
            "name": "TWSE fixture",
            "url": "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=json&date=20260824",
            "observed_at": "2026-08-24T13:30:00+08:00",
            "fetched_at": "2026-08-25T08:29:00+08:00",
            "official": True,
        },
    }
    paths = {}
    for name, payload in (("indices", indices), ("night", night), ("twse", twse), ("reference", reference)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    return paths, indices, night, twse, reference


def test_direction_and_gap_boundary_is_inclusive():
    assert direction_for_change(100) == "flat"
    assert direction_for_change(-100) == "flat"
    assert gap_label(100) == "flat"
    assert gap_label(-100) == "flat"
    assert direction_for_change(100.01) == "up"
    assert direction_for_change(-100.01) == "down"


def test_build_forecast_uses_official_previous_close_and_exposes_formula():
    _, indices, night, twse, reference = _inputs(Path("/tmp"))
    forecast = build_forecast(
        market_date="2026-08-25",
        locked_at="2026-08-25T08:30:00+08:00",
        indices=indices,
        night=night,
        twse=twse,
        taiex_reference=reference,
        config=load_model_config(CONFIG),
    )
    assert forecast["status"] == "generated"
    assert forecast["previous_close"] == 45000
    assert forecast["predicted_change_points"] == 146.4
    assert forecast["direction"] == "up"
    assert forecast["gap_label"] == "gap_up"
    assert forecast["confidence"] == "high"
    assert forecast["formula"]["available_weight"] == 1.0
    assert forecast["evidence"][0]["source_name"] == "TWSE fixture"
    assert forecast["evidence"][0]["observed_at"] == "2026-08-24T13:30:00+08:00"


def test_missing_factor_still_generates_low_confidence_forecast():
    _, indices, night, twse, reference = _inputs(Path("/tmp"))
    del indices["us_indices"]["dow"]
    forecast = build_forecast(
        market_date="2026-08-25",
        locked_at="2026-08-25T08:30:00+08:00",
        indices=indices,
        night=night,
        twse=twse,
        taiex_reference=reference,
        config=load_model_config(CONFIG),
    )
    assert forecast["status"] == "generated"
    assert forecast["confidence"] == "low"
    assert "dow_pct" in forecast["data_quality"]["missing_factors"]
    assert forecast["predicted_change_points"] is not None


def test_conflicting_signals_are_disclosed_and_lower_confidence():
    _, indices, night, twse, reference = _inputs(Path("/tmp"))
    night["latest"]["change"] = -200
    forecast = build_forecast(
        market_date="2026-08-25",
        locked_at="2026-08-25T08:30:00+08:00",
        indices=indices,
        night=night,
        twse=twse,
        taiex_reference=reference,
        config=load_model_config(CONFIG),
    )
    assert forecast["confidence"] == "low"
    assert forecast["data_quality"]["conflicts"] == ["market-signal:up_vs_down"]
    assert any("矛盾" in reason for reason in forecast["confidence_reasons"])


def test_legacy_previous_close_is_explicit_compatibility_fallback():
    _, indices, night, twse, _ = _inputs(Path("/tmp"))
    forecast = build_forecast(
        market_date="2026-08-25",
        locked_at="2026-08-25T08:30:00+08:00",
        indices=indices,
        night=night,
        twse=twse,
        taiex_reference={"status": "error"},
        config=load_model_config(CONFIG),
    )
    assert forecast["previous_close"] == 45000
    assert forecast["confidence"] == "low"
    assert "official_previous_close" in forecast["data_quality"]["missing_factors"]
    assert "compatibility fallback" in forecast["evidence"][0]["source_name"]


def test_generator_rejects_late_lock_without_using_intraday_data(tmp_path: Path):
    paths, *_ = _inputs(tmp_path)
    forecast = generate(
        market_date="2026-08-25",
        locked_at="2026-08-25T08:45:00+08:00",
        indices_path=paths["indices"],
        night_path=paths["night"],
        twse_path=paths["twse"],
        taiex_reference_path=paths["reference"],
        calendar_path=CALENDAR,
        config_path=CONFIG,
    )
    assert forecast["status"] == "not_generated"
    assert forecast["prediction_id"] is None
    assert "錯過" in forecast["confidence_reasons"][0]


def test_generator_returns_market_closed_without_reading_inputs(tmp_path: Path):
    forecast = generate(
        market_date="2026-08-29",
        locked_at="2026-08-29T08:30:00+08:00",
        indices_path=tmp_path / "missing-indices.json",
        night_path=tmp_path / "missing-night.json",
        twse_path=tmp_path / "missing-twse.json",
        taiex_reference_path=tmp_path / "missing-reference.json",
        calendar_path=CALENDAR,
        config_path=CONFIG,
    )
    assert forecast["status"] == "market_closed"
    assert forecast["prediction_id"].startswith("2026-08-29-market-closed-")


class _ReferenceResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _ReferenceSession:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return _ReferenceResponse(self.payload)


def test_official_taiex_reference_reads_previous_trading_day_close():
    from scripts.opening_prediction.fetch_taiex_reference import fetch_previous_close

    session = _ReferenceSession({
        "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
        "data": [["115/08/24", "45,100.00", "45,300.00", "45,000.00", "45,123.45"]],
    })
    payload = fetch_previous_close(market_date="2026-08-25", calendar_path=CALENDAR, session=session)
    assert payload["status"] == "ok"
    assert payload["previous_trade_date"] == "2026-08-24"
    assert payload["previous_close"] == 45123.45
    assert payload["source"]["official"] is True
    assert "date=20260824" in session.urls[0]


def test_official_taiex_reference_rejects_missing_or_wrong_date_row(tmp_path: Path):
    from scripts.opening_prediction.fetch_taiex_reference import fetch_previous_close

    session = _ReferenceSession({
        "fields": ["日期", "收盤指數"],
        "data": [["115/08/25", "45,123.45"]],
    })
    payload = fetch_previous_close(market_date="2026-08-25", calendar_path=CALENDAR, session=session)
    assert payload["status"] == "error"
    assert payload["previous_close"] is None
    assert "2026-08-24" in payload["error"]

    missing_calendar = fetch_previous_close(
        market_date="2026-08-25",
        calendar_path=tmp_path / "missing-calendar.json",
        session=session,
    )
    assert missing_calendar["status"] == "error"
    assert "calendar unavailable" in missing_calendar["error"]
