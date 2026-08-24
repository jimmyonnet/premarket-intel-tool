from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_page import build_us_market_context
from scripts.fetch_indices import parse_chart_quote


TAIPEI = timezone(timedelta(hours=8))


def test_parse_chart_quote_keeps_source_update_time_and_change():
    quote = parse_chart_quote(
        {
            "regularMarketPrice": 7655.45,
            "chartPreviousClose": 7674.37,
            "regularMarketTime": 1787582959,
            "marketState": None,
        },
        {"ticker": "^GSPC", "name": "S&P 500指數"},
    )

    assert quote["value"] == 7655.45
    assert quote["change"] == -18.92
    assert quote["change_pct"] == -0.25
    assert quote["updated_taipei"] == "2026-08-24 22:49"
    assert quote["source_label"] == "Yahoo Finance Chart"


def test_us_market_context_marks_regular_session_and_discloses_unknown_delay():
    now = datetime(2026, 8, 24, 22, 49, tzinfo=TAIPEI)
    indices = {"us_indices": {"sp500": {"updated_at": "2026-08-24T22:49:00+08:00"}}}

    context = build_us_market_context(now, indices)

    assert context["session_key"] == "regular"
    assert context["label"] == "美股盤中快照"
    assert context["badge_short"] == "盤中"
    assert context["pill_class"] == "pill-live"
    assert "來源更新 08/24 22:49" in context["detail"]
    assert "延遲分鐘數未提供" in context["detail"]
    assert "美國正常交易時段" in context["detail"]


def test_us_market_context_marks_pre_market_session():
    context = build_us_market_context(
        datetime(2026, 8, 24, 19, 0, tzinfo=TAIPEI),
        {"us_indices": {}},
    )

    assert context["session_key"] == "pre"
    assert context["label"] == "美股盤前"
    assert context["badge_short"] == "盤前"
    assert "尚未進入美股正常交易時段" in context["detail"]


def test_us_market_context_marks_after_hours_session():
    context = build_us_market_context(
        datetime(2026, 8, 25, 4, 0, tzinfo=TAIPEI),
        {"us_indices": {}},
    )

    assert context["session_key"] == "after"
    assert context["label"] == "美股盤後"
    assert context["badge_short"] == "盤後"
    assert "正常交易時段已結束" in context["detail"]


def test_us_market_context_marks_closed_session_without_source_time():
    context = build_us_market_context(
        datetime(2026, 8, 25, 12, 0, tzinfo=TAIPEI),
        {"us_indices": {}},
    )

    assert context["session_key"] == "closed"
    assert context["label"] == "最新收盤快照"
    assert context["badge_short"] == "收盤"
    assert context["updated_label"] == "來源時間未提供"
    assert "延遲分鐘數未提供" in context["detail"]
