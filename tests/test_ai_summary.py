from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from scripts import generate_ai_summary as ai




def sample_inputs():
    indices = {
        "us_indices": {
            "nasdaq": {"name": "那斯達克", "ticker": "^IXIC", "value": 100, "change_pct": -1.2, "updated_at": "2026-08-25T04:00:00+08:00"},
        },
        "adrs": {
            "nvda": {"name": "輝達 (NVDA)", "ticker": "NVDA", "value": 100, "change_pct": -2.0, "updated_at": "2026-08-25T04:00:00+08:00"},
        },
        "asia_open": {
            "^N225": {"name": "日經 225", "ticker": "^N225", "value": 100, "change_pct": 0.5, "updated_at": "2026-08-25T08:00:00+08:00"},
        },
    }
    night = {
        "date": "2026-08-25",
        "latest": {"price": 45000, "change": -100, "change_pct": -0.2, "collected_at": "2026-08-25T05:00:00+08:00"},
    }
    news = [
        {"title": "輝達財報牽動美股", "source": "中央社", "time": "08/25 07:00", "primary_topic": "company_earnings", "named_entities": ["nvidia"]},
        {"title": "台股盤前震盪", "source": "經濟日報", "time": "08/25 07:01", "primary_topic": "taiwan_market", "named_entities": ["taiwan_market"]},
        {"title": "美債殖利率回落", "source": "路透社", "time": "08/25 07:02", "primary_topic": "currency_commodities", "named_entities": []},
    ]
    source_status = {"sources": [{"name": "行情", "status": "ok"}, {"name": "PressPlay", "status": "warning", "fallback_used": True}]}
    return indices, night, news, source_status


def test_generate_summary_uses_deterministic_fallback_without_key():
    result = ai.generate_summary(*sample_inputs(), api_key="")

    assert result["status"] == "fallback"
    assert result["provider"] == "確定性降級整理"
    assert result["news_stats"] == {"count": 3, "unique_topics": 3, "unique_sources": 3, "nvidia_count": 1}
    assert result["data_quality"]["status"] == "attention"
    assert any("PressPlay" in issue["message"] for issue in result["data_quality"]["issues"])
    assert len(result["news_summary"]["key_points"]) == 3
    assert result["market_summary"]["observations"]
    assert result["market_summary"]["drivers"]
    assert all("資料時間" not in item for item in result["market_summary"]["observations"])


def test_generate_summary_normalizes_gemini_response(monkeypatch):
    monkeypatch.setattr(
        ai,
        "call_gemini",
        lambda _key, _model, _payload: {
            "news_summary": {
                "headline": "新聞涵蓋台股、海外市場與債券題材。",
                "topic_summary": [{"topic": "taiwan_market", "count": 1, "summary": "台股盤前震盪。"}],
                "key_points": ["台股盤前震盪。"],
            },
            "market_summary": {
                "headline": "隔夜行情偏弱。",
                "observations": ["科技股相對承壓。"],
                "drivers": ["市場關注財報。"],
                "risks": ["行情時間需留意。"],
            },
            "quality_note": "PressPlay 使用備援資料。",
        },
    )

    result = ai.generate_summary(*sample_inputs(), api_key="test-key", model="gemini-test")

    assert result["status"] == "ok"
    assert result["provider"] == "Gemini API"
    assert result["model"] == "gemini-test"
    assert result["news_summary"]["headline"] == "新聞涵蓋台股、海外市場與債券題材。"
    assert result["quality_note"] == "PressPlay 使用備援資料。"
    assert result["market_summary"]["observations"] == ["科技股相對承壓。"]
    assert result["market_summary"]["drivers"] == ["市場關注財報。"]


def test_closed_asia_quotes_are_explicitly_historical_in_fallback_and_ai_text():
    session = ai.asia_session_context(datetime(2026, 8, 25, 16, 0, tzinfo=ai.TAIPEI))
    assert session["key"] == "closed"
    quotes = [
        {"group": "美股指數", "name": "NASDAQ", "change_pct": 0.8},
        {"group": "亞股", "name": "日經225", "change_pct": -0.5},
        {"group": "台指期夜盤", "name": "台指期夜盤", "change_pct": 0.2},
    ]
    fallback = ai.fallback_market_summary(quotes, [], session)
    assert "前一交易時段收盤結果" in fallback["observations"][-1]
    assert all("亞股" not in item or "非當下盤中" in item for item in fallback["observations"])

    raw = {
        "news_summary": {"headline": "", "topic_summary": [], "key_points": []},
        "market_summary": {
            "headline": "美股主要指數普遍上漲，亞股則呈現下跌。",
            "observations": ["亞股呈現下跌。"],
            "drivers": [],
            "risks": [],
        },
    }
    normalized = ai.normalize_ai_response(raw, {"headline": "", "topic_summary": [], "key_points": []}, fallback, {"topic_counts": {}}, session)
    assert "亞股已收盤" in normalized["market_summary"]["headline"]
    assert "前一交易時段" in normalized["market_summary"]["observations"][0]


def test_template_renders_closed_asia_context_and_renames_quote_card():
    template_dir = Path(__file__).parent.parent / "scripts" / "templates"
    tmpl = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True).get_template("premarket.html.j2")
    html = tmpl.render(
        generated_at="2026/08/25 16:00",
        build_time="16:00",
        build_version="20260825_1600",
        data_date="08/25",
        stale_hours=0.1,
        hours_since_us_close=12.0,
        meta={"overall_status": "ready"},
        health={"overall_status": "ready", "status_label": "可用", "status_badge_class": "is-ready", "summary_reasons": [], "sources": []},
        indices={"asia_open": {"^N225": {"value": 100, "change": -0.5, "change_pct": -0.5, "updated_cst": "08/25 14:45"}, "^KS11": {"value": 100, "change": -0.6, "change_pct": -0.6, "updated_cst": "08/25 17:05"}}},
        us_indices={},
        asia_open={"^N225": {"value": 100, "price": 100, "change": -0.5, "change_pct": -0.5, "updated_cst": "08/25 14:45"}, "^KS11": {"value": 100, "price": 100, "change": -0.6, "change_pct": -0.6, "updated_cst": "08/25 17:05"}},
        indices_missing=[],
        night={},
        spark=None,
        disposal={"one_flag_from_disposal": [], "currently_in_disposal": []},
        date_check={"page_says_applies_to": "08/25"},
        date_check_eval={"status": "ok", "label": "正常", "class_name": "is-ok", "tooltip": "正常"},
        pressplay={"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        institutional={"stocks": [], "matched_count": 0, "candidate_count": 0},
        calendar={"events": [], "date_groups": []},
        financials={}, news=[], twse={}, ai_summary={"market_summary": {"headline": "亞股呈現下跌。", "observations": [], "drivers": [], "risks": []}},
        asia_market_context={"^N225": {"session_key": "closed", "badge": "收盤", "pill_class": "pill-fresh"}, "^KS11": {"session_key": "closed", "badge": "收盤", "pill_class": "pill-fresh"}},
        opening_forecast={}, opening_result={}, learning_status={}, twse_holidays_list=[],
    )
    soup = BeautifulSoup(html, "html.parser")
    market = soup.find(id="market-context")
    assert market is not None
    assert "美股／ADR 行情與亞股最近交易時段收盤概況" in market.text
    assert "亞股目前非盤中" in market.text
    assert "亞股最近收盤概況" in market.text
    assert "亞股開盤即時概況" not in market.text


def test_ai_panels_are_embedded_in_requested_parent_sections():
    template = open("scripts/templates/premarket.html.j2", encoding="utf-8").read()

    market_start = template.index("美股四大指數與跨海連動標的")
    market_end = template.index("<!-- 台股摘要與夜盤 -->")
    news_start = template.index("隔夜重大新聞 Top 10")
    news_end = template.index("<!-- 財經行事曆 (時間軸儀表板) -->")
    availability_start = template.index("id=\"today-briefing-block\"")
    availability_end = template.index("</details>", availability_start)

    assert "ai-market-inline-panel" in template[market_start:market_end]
    assert "ai-news-inline-panel" in template[news_start:news_end]
    assert "📰 新聞要" in template[news_start:news_end]
    assert "ai-quality-inline" in template[availability_start:availability_end]
    assert "ai-briefing-card-wrap" not in template
