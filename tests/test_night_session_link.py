from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "index.html"
TARGET = "https://www.cmoney.tw/forum/futures/TXF1?s=p"


def _night_session_block(html: str) -> str:
    start = html.index("<!-- 台指期夜盤 -->")
    end = html.index('<div id="open-countdown"', start)
    return html[start:end]


def test_night_session_card_links_to_cmoney_in_new_tab():
    block = _night_session_block(PAGE.read_text(encoding="utf-8"))

    assert f'href="{TARGET}"' in block
    assert 'target="_blank"' in block
    assert 'rel="noopener noreferrer"' in block
    assert "台指期夜盤 (05:00) · 來源：Wantgoo / TAIFEX" in block
    assert "45,074" in block
    assert "-64.0 (-0.14%)" in block
    assert "基準：vs 期貨日盤收盤 (45,138)" in block
