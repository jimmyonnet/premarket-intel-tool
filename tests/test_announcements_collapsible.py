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
    assert "資料抓取失敗，無法確認市場未反映公告" in template
    assert "stale_cached" in block
    assert "沿用快取" in template


def test_announcement_table_uses_readable_semantic_cells_and_responsive_layout():
    template = TEMPLATE.read_text(encoding="utf-8")
    macro_start = template.index('{% macro render_announcement_rows')
    macro_end = template.index('{% endmacro %}', macro_start)
    macro = template[macro_start:macro_end]

    assert '<table class="data-table announcement-table">' in macro
    assert 'class="announcement-stock"' in macro
    assert 'class="announcement-code font-mono"' in macro
    assert 'class="announcement-name"' in macro
    assert 'class="announcement-time font-mono"' in macro
    assert 'class="announcement-date">{{ row.get(\'date\') or \'—\' }}</span>' in macro
    assert 'class="announcement-clock">{{ row.get(\'time\') }}</span>' in macro
    assert 'class="announcement-subject"' in macro
    assert 'class="announcement-ai"' in macro
    assert 'class="announcement-eps num font-mono"' in macro
    assert '.announcement-table {\n    width: 100%;\n    table-layout: fixed;' in template
    assert '.announcement-table th:nth-child(1),\n  .announcement-table td:nth-child(1) { width: 12%; }' in template
    assert '.announcement-table th:nth-child(2),\n  .announcement-table td:nth-child(2) { width: 18%; }' in template
    assert '.announcement-table th:nth-child(3),\n  .announcement-table td:nth-child(3) { width: 50%; }' in template
    assert '.announcement-table th:nth-child(4),\n  .announcement-table td:nth-child(4) { width: 8%; }' in template
    assert '.announcement-table th:nth-child(5),\n  .announcement-table td:nth-child(5) { width: 12%; }' in template
    assert '.data-table.announcement-table td {' in template
    assert 'grid-template-columns: 88px minmax(0, 1fr);' in template
    assert '.data-table.announcement-table td {\n      width: 100% !important;\n      box-sizing: border-box;' in template
    assert '.announcement-time {\n    white-space: normal;\n    line-height: 1.45;' in template
    assert '.announcement-date,\n  .announcement-clock {\n    display: block;' in template
    assert '.announcement-clock {\n    margin-top: 2px;' in template
    assert '.announcement-raw-details {\n    display: block;' in template
    assert '.announcement-raw-details > summary {\n    display: inline-block;' in template
    assert '.announcement-raw-details[open] > summary {\n    margin-bottom: 8px;' in template
    assert '.announcement-stock {\n    min-width: 0;' in template
    assert '.announcement-stock {\n    display: flex;' not in template
    assert '.announcement-stock .announcement-code,\n  .announcement-stock .announcement-name {\n    display: block;' in template


def test_realtime_announcement_summary_keeps_count_but_omits_redundant_time_tip():
    template = TEMPLATE.read_text(encoding="utf-8")
    macro_start = template.index('{% macro render_announcements')
    macro_end = template.index('{% endmacro %}', macro_start)
    macro = template[macro_start:macro_end]
    page_section = _announcement_block(template)

    assert '<h3 class="card-title">即時公告明細</h3>' in macro
    assert '<span class="count-badge">{{ unref_count }} 筆</span>' in macro
    assert '<span class="card-tip">昨日 13:30 盤後即時重訊</span>' not in macro
    assert '<span class="section-desc">昨日 13:30 盤後重大財務自結</span>' in page_section
