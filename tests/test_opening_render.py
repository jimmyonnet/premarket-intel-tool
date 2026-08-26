from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "templates"


def _render(**opening):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    context = {
        "generated_at": "2026/08/25 08:30",
        "build_time": "08:30",
        "build_version": "20260825_0830",
        "data_date": "08/25",
        "stale_hours": 0,
        "hours_since_us_close": 3,
        "meta": {"overall_status": "ready"},
        "health": {"overall_status": "ready", "status_label": "可用", "status_badge_class": "is-ready", "summary_reasons": [], "sources": []},
        "indices": {}, "us_indices": {}, "asia_open": {}, "indices_missing": [], "night": {}, "spark": None,
        "disposal": {"one_flag_from_disposal": [], "currently_in_disposal": []},
        "date_check": {}, "date_check_eval": {},
        "pressplay": {"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        "institutional": {"stocks": [], "matched_count": 0, "candidate_count": 0},
        "calendar": {"events": [], "date_groups": []}, "financials": {}, "news": [], "ai_summary": {}, "twse": {},
        "opening_forecast": opening.get("forecast", {}),
        "opening_result": opening.get("result", {}),
        "learning_status": opening.get("learning", {}),
        "twse_holidays_list": [],
    }
    return env.get_template("premarket.html.j2").render(**context)


def test_opening_card_fallback_is_safe_and_at_page_main_end():
    soup = BeautifulSoup(_render(), "html.parser")
    main = soup.find("main", class_="page-main")
    card = soup.find("section", id="opening-forecast")
    summary = soup.find("section", id="summary")
    news_calendar = soup.find("section", id="news-calendar")
    assert main is not None and card is not None and summary is not None and news_calendar is not None
    sections = main.find_all("section", recursive=False)
    assert sections[-1] is card
    assert sections.index(card) > sections.index(summary)
    assert sections.index(card) > sections.index(news_calendar)
    disclosure = card.find("details", class_="opening-forecast-disclosure")
    assert disclosure is not None and disclosure.has_attr("open") is False
    assert disclosure.find("summary", class_="opening-forecast-head") is not None
    assert disclosure.find(class_="opening-forecast-toggle") is not None
    assert "不使用前一天預測冒充今日內容" in card.get_text()


def test_opening_card_renders_single_conclusion_and_traceable_details():
    forecast = {
        "status": "generated", "confidence": "medium", "direction": "up",
        "model_version": "opening-v1", "prediction_id": "2026-08-25T08:30+08:00-opening-v1",
        "market_date": "2026-08-25", "locked_at": "2026-08-25T08:30:00+08:00",
        "previous_close": 45000, "predicted_change_points": 146.4, "predicted_open": 45146.4,
        "confidence_reasons": ["資料可用，但市場訊號包含中性或混合方向"],
        "data_quality": {"missing_factors": [], "conflicts": [], "cache_used": False},
        "evidence": [{"label": "TWSE 官方前收", "value": 45000, "unit": "index_points", "observed_at": "2026-08-24T13:30:00+08:00", "fetched_at": "2026-08-25T08:29:00+08:00", "source_name": "TWSE", "source_url": "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST", "cache_used": False, "supports": "neutral"}],
        "formula": {"threshold_points": 100, "available_weight": 1, "features": [{"key": "night_session_points", "input": 200, "weight": 0.6, "conversion": 1, "contribution": 120}]},
    }
    result = {"status": "pending"}
    learning = {"status": "warmup", "verified_days": 3, "required_days": 20}
    soup = BeautifulSoup(_render(forecast=forecast, result=result, learning=learning), "html.parser")
    card = soup.find("section", id="opening-forecast")
    assert card is not None
    assert "偏開高" in card.get_text()
    assert "預估 +146 點" in card.get_text()
    assert "中可信度" in card.get_text()
    assert "等待驗證" in card.get_text()
    assert "3/20" in card.get_text()
    disclosure = card.find("details", class_="opening-forecast-disclosure")
    assert disclosure is not None and disclosure.has_attr("open") is False
    details = card.find("details", class_="opening-forecast-details")
    assert details is not None and details.has_attr("open") is False
    source = card.find("a", href="https://www.twse.com.tw/indicesReport/MI_5MINS_HIST")
    assert source is not None
    assert "公式" in card.get_text() and "門檻" in card.get_text()


def test_opening_card_hides_stale_forecast_from_another_market_date():
    forecast = {
        "status": "generated", "confidence": "high", "direction": "down",
        "market_date": "2026-08-24", "predicted_change_points": -300,
        "prediction_id": "2026-08-24T08:30+08:00-opening-v1",
    }
    soup = BeautifulSoup(_render(forecast=forecast, result={"status": "verified"}, learning={"status": "warmup", "verified_days": 0, "required_days": 20}), "html.parser")
    card = soup.find("section", id="opening-forecast")
    assert card is not None
    text = card.get_text(" ", strip=True)
    assert "今日尚未產生預測" in text
    assert "偏開低" not in text
    assert "-300" not in text
    assert "目前保存的預測屬於前一交易日；請等待今日 08:30 預測工作完成。" in text
    assert "鎖定窗口已錯過" not in text
