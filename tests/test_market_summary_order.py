from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _market_context(text: str) -> str:
    start = text.index('<section id="market-context"')
    end = text.index('    </section>', start) + len('    </section>')
    return text[start:end]


def test_market_summary_cards_render_before_asia_opening_section():
    source = TEMPLATE.read_text(encoding="utf-8")
    market = _market_context(source)

    assert '{{ render_market_summary_cards(twse, financials, night, unref_count) }}' in market
    assert market.index('{{ render_market_summary_cards(twse, financials, night, unref_count) }}') < market.index('亞股開盤即時概況')
    assert 'class="summary-grid market-summary-grid"' in source


def test_deployed_market_summary_cards_precede_asia_and_no_longer_show_trading_countdown():
    page = DEPLOYED.read_text(encoding="utf-8")
    market = _market_context(page)

    summary_pos = market.index('class="summary-grid market-summary-grid"')
    asia_titles = [title for title in ('亞股開盤即時概況', '亞股最近收盤概況') if title in market]
    assert asia_titles, '部署頁面必須顯示盤中或最近收盤的亞股標題'
    assert summary_pos < min(market.index(title) for title in asia_titles)
    assert '盤中撮合中' not in page
    assert '收盤倒數' not in page
    assert 'id="open-countdown"' not in page
