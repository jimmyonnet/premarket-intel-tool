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
    assert "ai-quality-inline" in template[availability_start:availability_end]
    assert "ai-briefing-card-wrap" not in template
