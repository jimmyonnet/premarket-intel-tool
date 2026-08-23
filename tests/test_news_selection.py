from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.fetch_news import (
    MIN_TOTAL_SCORE,
    dedupe_articles,
    is_qualified,
    parse_feed,
    select_top_news,
    score_breakdown,
    score_news,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "scripts" / "assets" / "app.js"
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


def test_dedupe_keeps_stronger_version_of_same_story():
    older = article("聯準會利率決策牽動美股與台股", "中央社", timestamp=1_700_000_000)
    newer = article("聯準會利率決策牽動美股與台股", "路透社", timestamp=1_700_001_000)

    result = dedupe_articles([older, newer])

    assert len(result) == 1
    assert result[0]["source"] == "路透社"


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
    app = APP.read_text(encoding="utf-8")

    assert "隔夜重大新聞 Top 10" in page
    assert "隔夜重大新聞 Top 5" not in page
    assert "items.slice(0, 10)" in app
