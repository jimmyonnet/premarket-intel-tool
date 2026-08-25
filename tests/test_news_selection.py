from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import scripts.fetch_news as fetch_news

from scripts.fetch_news import (
    MIN_TOTAL_SCORE,
    dedupe_articles,
    get_time_window,
    is_qualified,
    parse_feed,
    select_top_news,
    score_breakdown,
    score_news,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
TAIPEI = timezone(timedelta(hours=8))


def article(title, source="中央社", score=None, timestamp=1_700_000_000):
    scores = score_breakdown(title, source)
    if score is not None:
        scores["score"] = score
    item = {
        "title": title,
        "link": f"https://example.com/{timestamp}",
        "source": source,
        "time": "08/23 07:00",
        "timestamp": timestamp,
        **scores,
    }
    item["qualified"] = is_qualified(item)
    return item


def test_score_news_keeps_integer_compatibility():
    assert isinstance(score_news("聯準會利率決策牽動台股", "中央社"), int)


def test_high_quality_high_impact_article_passes():
    item = article("聯準會利率決策牽動美股與台股，台積電財報展望受關注")

    assert item["quality_score"] >= 4
    assert item["impact_score"] >= 6
    assert item["qualified"] is True
    assert item["score"] >= MIN_TOTAL_SCORE


def test_low_signal_or_unknown_source_does_not_pass_quality_gate():
    low_signal = article("老師推薦這檔明天可能漲停", "不明來源")

    assert low_signal["qualified"] is False


def test_recognized_yahoo_stock_source_can_pass_with_material_market_impact():
    item = article("輝達財報、聯準會論壇與地緣政治牽動美股本週動向", "Yahoo股市")

    assert item["quality_score"] == 3
    assert item["impact_score"] >= 3
    assert item["qualified"] is True


def test_credible_single_topic_market_news_can_pass_relaxed_total_threshold():
    item = article("風向變了！金融三業6月大砍台股757億", "工商時報")

    assert item["score"] == 7
    assert item["qualified"] is True


def test_low_signal_phrase_is_rejected_even_from_a_recognized_source():
    item = article("投資人必看：台積電財報牽動台股與美股", "經濟日報")

    assert item["quality_score"] >= 4
    assert item["low_signal_hits"] == ["投資人必看"]
    assert item["qualified"] is False


def test_dedupe_keeps_stronger_version_of_same_story():
    older = article("聯準會利率決策牽動美股與台股", "中央社", timestamp=1_700_000_000)
    newer = article("聯準會利率決策牽動美股與台股", "路透社", timestamp=1_700_001_000)

    result = dedupe_articles([older, newer])

    assert len(result) == 1
    assert result[0]["source"] == "路透社"


def test_diversity_metadata_is_recorded_for_each_article():
    item = article("輝達財報與 AI 需求牽動美股市場", "路透社")

    assert item["primary_topic"] == "global_market"
    assert "sector_technology" in item["topic_groups"]
    assert "nvidia" in item["named_entities"]


def test_select_top_news_limits_repetitive_entity_when_other_topics_are_available():
    repetitive = [
        article(f"輝達財報前瞻與 AI 需求展望第 {i}", "路透社", score=20, timestamp=1_700_000_000 + i)
        for i in range(8)
    ]
    alternatives = [
        article("聯準會利率決策牽動美元與美股行情", "中央社", score=15, timestamp=1_700_001_000),
        article("原油大漲牽動美股與台股風險偏好", "彭博", score=14, timestamp=1_700_001_001),
        article("日經與 KOSPI 股市大跌拖累亞股情緒", "工商時報", score=13, timestamp=1_700_001_002),
        article("台積電財報展望牽動台股供應鏈", "經濟日報", score=13, timestamp=1_700_001_003),
        article("伊朗制裁升溫引發市場避險與油價大漲", "鉅亨網", score=12, timestamp=1_700_001_004),
        article("蘋果營收展望與消費電子需求受關注", "Yahoo股市", score=12, timestamp=1_700_001_005),
        article("美元匯率與黃金價格大漲牽動市場", "news.cnyes.com", score=11, timestamp=1_700_001_006),
        article("韓國 KOSPI 股市與記憶體類股大跌", "Yahoo新聞", score=10, timestamp=1_700_001_007),
    ]

    result = select_top_news(repetitive + alternatives)

    assert len(result) == 10
    assert sum("nvidia" in item["named_entities"] for item in result) == 3
    assert len({item["primary_topic"] for item in result}) >= 5
    assert all("primary_topic" in item and "named_entities" in item for item in result)


def test_select_top_news_caps_at_ten_without_padding():
    items = [
        article(f"台股大盤與台積電財報重大消息第 {i}", "中央社", timestamp=1_700_000_000 + i)
        for i in range(12)
    ]

    result = select_top_news(items)

    assert len(result) == 10
    assert all(item["qualified"] for item in result)


def test_select_top_news_returns_fewer_than_ten_when_qualified_items_are_insufficient():
    items = [article("美股與聯準會重大政策變化", "中央社", timestamp=1_700_000_000)]

    result = select_top_news(items)

    assert len(result) == 1


def test_after_close_window_starts_at_today_post_market_cutoff():
    now = datetime(2026, 8, 24, 22, 0, tzinfo=TAIPEI)

    start, end = get_time_window(now)

    assert start == datetime(2026, 8, 24, 13, 30, tzinfo=TAIPEI)
    assert end == now


def test_before_close_window_starts_at_previous_trading_day_cutoff():
    now = datetime(2026, 8, 24, 10, 0, tzinfo=TAIPEI)

    start, end = get_time_window(now)

    assert start == datetime(2026, 8, 21, 13, 30, tzinfo=TAIPEI)
    assert end == now


def test_weekend_window_starts_at_previous_trading_day_cutoff():
    now = datetime(2026, 8, 23, 10, 0, tzinfo=TAIPEI)

    start, end = get_time_window(now)

    assert start == datetime(2026, 8, 21, 13, 30, tzinfo=TAIPEI)
    assert end == now


def test_parse_feed_excludes_article_before_post_market_cutoff():
    xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>聯準會政策影響台股與美股財報 13:29</title>
        <link>https://example.com/before</link>
        <pubDate>Mon, 24 Aug 2026 05:29:00 GMT</pubDate>
        <source>中央社</source>
      </item>
      <item>
        <title>聯準會政策影響台股與美股財報 13:30</title>
        <link>https://example.com/at-cutoff</link>
        <pubDate>Mon, 24 Aug 2026 05:30:00 GMT</pubDate>
        <source>中央社</source>
      </item>
    </channel></rss>"""
    start = datetime(2026, 8, 24, 13, 30, tzinfo=TAIPEI)
    end = datetime(2026, 8, 24, 14, 0, tzinfo=TAIPEI)

    parsed = parse_feed(xml.encode("utf-8"), start, end)

    assert [item["link"] for item in parsed] == ["https://example.com/at-cutoff"]


def test_parse_feed_preserves_scoring_metadata_and_filters_time_window():
    pubdate = "Sat, 22 Aug 2026 23:00:00 GMT"
    xml = f"""<?xml version="1.0"?>
    <rss><channel><item>
      <title>聯準會政策影響台股與美股財報</title>
      <link>https://example.com/news</link>
      <pubDate>{pubdate}</pubDate>
      <source>中央社</source>
    </item></channel></rss>"""
    start = datetime(2026, 8, 23, 0, 0, tzinfo=TAIPEI)
    end = datetime(2026, 8, 23, 12, 0, tzinfo=TAIPEI)

    parsed = parse_feed(xml.encode("utf-8"), start, end)

    assert len(parsed) == 1
    assert parsed[0]["quality_score"] >= 4
    assert parsed[0]["impact_score"] >= 3
    assert parsed[0]["qualified"] is True


def test_deployed_news_section_uses_top_ten_cap():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")

    assert "隔夜重大新聞 Top 10" in page
    assert "隔夜重大新聞 Top 5" not in page
    assert "items.slice(0, 10)" in template


def test_all_rss_failures_retain_previous_news_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "latest").mkdir(parents=True)
    news_path = tmp_path / "data" / "latest" / "news.json"
    previous = [{"title": "保留的高品質新聞", "link": "https://example.com/previous"}]
    news_path.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(fetch_news, "fetch_feed", lambda _query: b"")

    fetch_news.main()

    assert json.loads(news_path.read_text(encoding="utf-8")) == previous
