from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def test_asia_cards_prioritize_index_name_price_and_change_over_source_details():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert '<div class="tile-card asia-quote-card">' in source
    assert ".asia-quote-card .tile-name { font-size: 14px; font-weight: 800;" in source
    assert ".asia-quote-card .tile-val { order: 1;" in source
    assert "font-size: 25px;" in source
    assert ".asia-quote-card .tile-chg { order: 2;" in source
    assert "font-size: 13px;" in source
    assert ".asia-quote-card .tile-source-row {" in source
    assert "order: 3;" in source


def test_deployed_asia_cards_keep_the_core_quote_class():
    page = DEPLOYED.read_text(encoding="utf-8")

    assert page.count('class="tile-card asia-quote-card"') == 2
