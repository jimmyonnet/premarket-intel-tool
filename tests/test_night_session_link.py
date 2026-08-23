from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "scripts" / "assets" / "app.js"
TARGET = "https://www.cmoney.tw/forum/futures/TXF1?s=p"


def test_market_renderer_links_night_session_to_cmoney_in_new_tab():
    app = APP.read_text(encoding="utf-8")

    assert f'href="{TARGET}"' in app
    assert 'target="_blank" rel="noopener noreferrer"' in app
    assert 'class="market-item"' in app
    assert "夜盤" in app
