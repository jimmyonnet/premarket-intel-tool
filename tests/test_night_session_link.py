from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "index.html"
APP = ROOT / "scripts" / "assets" / "app.js"
TARGET = "https://www.cmoney.tw/forum/futures/TXF1?s=p"


def _night_session_block(html: str) -> str:
    start = html.index("<!-- 台指期夜盤 -->")
    end = html.index("<!-- 亞股開盤走勢 -->", start)
    return html[start:end]


def test_night_session_card_links_to_cmoney_in_new_tab():
    block = _night_session_block(PAGE.read_text(encoding="utf-8"))

    assert f'href="{TARGET}"' in block
    assert 'target="_blank"' in block
    assert 'rel="noopener noreferrer"' in block
    assert "台指期夜盤 (05:00) · 來源：Wantgoo / TAIFEX" in block
    assert 'class="summary-card"' in block
    assert 'class="card-val font-mono' in block
    assert "基準：vs 期貨日盤收盤" in block


def test_modern_market_renderer_links_night_session_to_cmoney():
    app = APP.read_text(encoding="utf-8")

    assert f'href="{TARGET}"' in app
    assert 'target="_blank" rel="noopener noreferrer"' in app
    assert 'class="market-item"' in app
    assert "夜盤" in app


def test_market_context_stays_first_in_summary_after_utility_panel():
    template = (ROOT / "scripts" / "templates" / "premarket.html.j2").read_text(encoding="utf-8")

    assert "var availability = document.getElementById('summary-briefing-anchor');" in template
    assert "var marketContext = document.getElementById('market-context');" in template
    assert "availability.insertAdjacentElement('afterend', marketContext)" in template
