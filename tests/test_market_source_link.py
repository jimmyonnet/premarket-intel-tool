from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"
YAHOO_MARKETS_URL = "https://tw.stock.yahoo.com/markets"


def _market_card(html: str) -> str:
    start = html.index("美股四大指數與跨海連動標的")
    end = html.index("<!-- 跨海連動 ADR / 關鍵標的", start)
    return html[start:end]


def test_market_indices_card_has_yahoo_markets_source_button_in_template():
    card = _market_card(TEMPLATE.read_text(encoding="utf-8"))

    assert f'href="{YAHOO_MARKETS_URL}"' in card
    assert 'class="cal-link-btn"' in card
    assert 'target="_blank"' in card
    assert 'rel="noopener noreferrer"' in card


def test_deployed_market_indices_card_has_yahoo_markets_source_button():
    card = _market_card(DEPLOYED.read_text(encoding="utf-8"))

    assert f'href="{YAHOO_MARKETS_URL}"' in card
    assert 'target="_blank"' in card
