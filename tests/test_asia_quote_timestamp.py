import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_page import build_asia_market_context


TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED_PAGE = ROOT / "docs" / "index.html"
INDICES = ROOT / "data" / "latest" / "indices.json"
TAIPEI = timezone(timedelta(hours=8))


def test_asia_cards_render_source_quote_time_with_clear_context():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "Yahoo 股市延遲 20 分鐘" in source
    assert "Yahoo 股市 · {{ q.updated_cst }} · 延遲 20 分鐘" in source
    assert "非頁面建置時間" in source
    assert "Yahoo 股市 · 行情時間未提供" in source
    assert "asia_status.pill_class" in source
    assert "asia_status.badge" in source
    assert "pill-live" in source
    assert "https://tw.stock.yahoo.com/quote/%5EN225" in source
    assert "https://tw.stock.yahoo.com/quote/%5EKS11" in source
    assert 'target="_blank" rel="noopener noreferrer"' in source


def test_deployed_asia_cards_show_current_source_quote_times():
    page = DEPLOYED_PAGE.read_text(encoding="utf-8")
    asia_open = json.loads(INDICES.read_text(encoding="utf-8"))["asia_open"]

    for index_key in ("nikkei225", "kospi"):
        assert f"Yahoo 股市 · {asia_open[index_key]['updated_cst']} · 延遲 20 分鐘" in page

    assert 'href="https://tw.stock.yahoo.com/quote/%5EN225"' in page
    assert 'href="https://tw.stock.yahoo.com/quote/%5EKS11"' in page


def test_asia_market_context_marks_both_indices_in_session_as_blue_live():
    now = datetime(2026, 8, 24, 9, 15, tzinfo=TAIPEI)
    quote = {"price": 100.0}

    nikkei = build_asia_market_context(now, "^N225", quote)
    kospi = build_asia_market_context(now, "^KS11", quote)

    assert nikkei["session_key"] == "regular"
    assert nikkei["badge"] == "盤中"
    assert nikkei["pill_class"] == "pill-live"
    assert kospi["session_key"] == "regular"
    assert kospi["badge"] == "盤中"
    assert kospi["pill_class"] == "pill-live"


def test_asia_market_context_does_not_call_japan_break_or_after_hours_live():
    quote = {"price": 100.0}

    japan_break = build_asia_market_context(datetime(2026, 8, 24, 11, 0, tzinfo=TAIPEI), "^N225", quote)
    after_hours = build_asia_market_context(datetime(2026, 8, 24, 15, 0, tzinfo=TAIPEI), "^KS11", quote)

    assert japan_break["badge"] == "收盤"
    assert japan_break["pill_class"] == "pill-fresh"
    assert after_hours["badge"] == "收盤"
    assert after_hours["pill_class"] == "pill-fresh"
