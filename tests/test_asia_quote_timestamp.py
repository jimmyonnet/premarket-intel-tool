import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED_PAGE = ROOT / "docs" / "index.html"
INDICES = ROOT / "data" / "latest" / "indices.json"


def test_asia_cards_render_source_quote_time_with_clear_context():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "時間為來源行情時間" in source
    assert "來源行情 {{ q.updated_cst }}" in source
    assert "非頁面建置時間" in source
    assert "行情時間未提供" in source


def test_deployed_asia_cards_show_current_source_quote_times():
    page = DEPLOYED_PAGE.read_text(encoding="utf-8")
    asia_open = json.loads(INDICES.read_text(encoding="utf-8"))["asia_open"]

    for index_key in ("nikkei225", "kospi"):
        assert f"來源行情 {asia_open[index_key]['updated_cst']}" in page
