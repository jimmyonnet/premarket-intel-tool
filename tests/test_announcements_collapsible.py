from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _announcement_block(text: str) -> str:
    marker = '<section id="announcements" class="content-section">'
    start = text.index(marker)
    end = text.index('    </section>', start) + len('    </section>')
    return text[start:end]


def test_source_template_places_announcements_after_watchlist_before_market_context():
    template = TEMPLATE.read_text(encoding="utf-8")
    block = _announcement_block(template)

    assert block.startswith('<section id="announcements" class="content-section">')
    assert '{{ render_announcements(financials, unref_count, build_version, generated_at) }}' in block
    assert template.index('<section id="watchlist"') < template.index('<section id="announcements"')
    assert template.index('<section id="announcements"') < template.index('<section id="market-context"')


def test_deployed_announcement_card_follows_watchlist_and_keeps_collapsed_rows():
    page = DEPLOYED.read_text(encoding="utf-8")
    block = _announcement_block(page)

    assert page.index('<section id="watchlist"') < page.index('<section id="announcements"') < page.index('<section id="market-context"')
    assert '<details class="card announcements-collapsible" open>' in block
    assert '<summary class="card-head"' in block
    assert block.count('class="unref-accordion"') == 3
    assert 'class="unref-accordion" open' not in block


def test_announcement_template_distinguishes_fetch_failure_and_cached_data_from_zero_rows():
    template = TEMPLATE.read_text(encoding="utf-8")
    macro_start = template.index('{% macro render_announcements')
    macro_end = template.index('{% endmacro %}', macro_start)
    block = template[macro_start:macro_end]

    assert "financial_source_status" in block
    assert "資料抓取失敗，無法確認市場未反映筆數" in block
    assert "沿用前次" in block
    assert "沿用快取" in block
