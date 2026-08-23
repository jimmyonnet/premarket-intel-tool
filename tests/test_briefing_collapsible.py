from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOYED = ROOT / "docs" / "index.html"
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"


def _outer_block(text, marker, end_marker="</details>"):
    start = text.index(marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def test_deployed_data_availability_block_is_collapsed_by_default():
    page = DEPLOYED.read_text(encoding="utf-8")
    block = _outer_block(page, '<details class="briefing-details"')
    opening_tag = block.split(">", 1)[0]

    assert " open" not in opening_tag
    assert "📊 資料可用性" in block
    assert "資料可用性 · 首屏契約" in block
    assert 'id="today-briefing-block"' in block


def test_template_data_availability_block_is_collapsed_by_default():
    template = TEMPLATE.read_text(encoding="utf-8")
    block = _outer_block(template, '<details class="briefing-details"')
    opening_tag = block.split(">", 1)[0]

    assert " open" not in opening_tag
    assert "📊 資料可用性" in block
    assert "資料可用性 · 首屏契約" in block
    assert 'aria-label="展開資料可用性"' in block
