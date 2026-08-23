from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _announcement_block(text: str) -> str:
    marker = '<details class="card announcements-collapsible"'
    start = text.index(marker)
    end = text.index('    </section>', start)
    return text[start:end]


def test_source_template_announcement_section_is_collapsed_by_default():
    block = _announcement_block(TEMPLATE.read_text(encoding="utf-8"))

    assert block.startswith('<details class="card announcements-collapsible"')
    assert '<summary class="card-head"' in block
    assert ' open' in block.split(">", 1)[0]


def test_deployed_announcement_card_shows_collapsed_rows_by_default():
    block = _announcement_block(DEPLOYED.read_text(encoding="utf-8"))

    assert block.startswith('<details class="card announcements-collapsible"')
    assert '<summary class="card-head"' in block
    assert ' open' in block.split(">", 1)[0]
    assert block.count('class="unref-accordion"') == 3
    assert 'class="unref-accordion" open' not in block


def test_announcement_template_distinguishes_fetch_failure_and_cached_data_from_zero_rows():
    template = TEMPLATE.read_text(encoding="utf-8")
    block = _announcement_block(template)

    assert "financial_source_status" in template
    assert "資料抓取失敗，無法確認市場未反映筆數" in block
    assert "沿用前次" in block
    assert "沿用快取" in block
