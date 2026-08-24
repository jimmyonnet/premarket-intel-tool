from pathlib import Path

from scripts.fetch_indices import parse_chart_quote


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"
YAHOO_MARKETS_URL = "https://tw.stock.yahoo.com/markets"
YAHOO_MICRON_URL = "https://tw.stock.yahoo.com/quote/MU"


def _market_card(html: str) -> str:
    start = html.index("美股四大指數與跨海連動標的")
    end = html.index("<!-- 跨海連動 ADR / 關鍵標的", start)
    return html[start:end]


def _cross_sea_block(html: str) -> str:
    start = html.index("<!-- 跨海連動 ADR / 關鍵標的")
    end = html.index("<!-- 台股摘要與夜盤", start)
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


def test_market_indices_card_uses_micron_instead_of_tsmc_spot():
    template = TEMPLATE.read_text(encoding="utf-8")
    deployed = DEPLOYED.read_text(encoding="utf-8")

    template_block = _cross_sea_block(template)
    assert "('MU', '美光 (MU)')" in template_block
    assert "台積電 現貨" not in template_block
    assert "2330.TW" not in template_block

    deployed_block = _cross_sea_block(deployed)
    assert '<span class="tile-name">美光 (MU)</span>' in deployed_block
    assert '<span class="tile-name">台積電 現貨</span>' not in deployed_block
    assert "2330.TW" not in deployed_block


def test_micron_quote_source_url_is_kept_in_fetcher_config():
    source = (ROOT / "scripts" / "fetch_indices.py").read_text(encoding="utf-8")

    assert '"ticker": "MU"' in source
    assert '"name": "美光"' in source
    assert f'"source_url": "{YAHOO_MICRON_URL}"' in source


def test_micron_chart_quote_preserves_the_specified_yahoo_quote_url():
    quote = parse_chart_quote(
        {
            "regularMarketPrice": 100.0,
            "chartPreviousClose": 98.0,
            "regularMarketTime": 1777000000,
        },
        {"ticker": "MU", "name": "美光", "source_url": YAHOO_MICRON_URL},
    )

    assert quote["ticker"] == "MU"
    assert quote["name"] == "美光"
    assert quote["source_url"] == YAHOO_MICRON_URL


def test_market_indices_card_uses_dynamic_market_status_instead_of_fixed_delay_label():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'class="card-tip font-mono market-status-detail"' in source
    assert "us_market_context.label" in source
    assert "us_market_context.detail" in source
    assert "昨日收盤（美東 16:00）" not in source
    assert "資料延遲 <time" not in source
