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
    assert '<div class="tiles-grid asia-quotes-grid">' in source
    assert "#market-context .asia-quotes-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in source
    assert "#market-context .asia-quotes-grid { grid-template-columns: 1fr; }" in source


def test_candidate_groups_are_collapsed_and_show_names_in_summary():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.count('<details class="card candidate-group-disclosure">') == 2
    assert source.count('<summary class="card-head candidate-group-summary">') == 2
    assert '<details class="card candidate-group-disclosure" open>' not in source
    assert "pressplay.found_group.matched|map(attribute='name')|join('、')" in source
    assert "pressplay.not_found_group.matched|map(attribute='name')|join('、')" in source
    assert 'class="candidate-group-symbols"' in source
    assert ".candidate-group-summary::after" in source
    assert ".candidate-group-disclosure[open] > .candidate-group-summary::after" in source
    assert "var openAllDetails = opening && window.innerWidth >= 769;" in source
    assert "panel.open = openAllDetails;" in source


def test_deployed_asia_cards_keep_the_core_quote_class():
    page = DEPLOYED.read_text(encoding="utf-8")

    assert page.count('class="tile-card asia-quote-card"') == 2
