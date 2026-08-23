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
    block = _outer_block(page, '<details class="today-briefing-details"')
    opening_tag = block.split(">", 1)[0]

    assert " open" not in opening_tag
    assert "📊 資料可用性" in block
    assert "⭐ 自選股優先項目" in block
    assert "⏰ 今日高影響事件" in block
    assert any(label in block for label in ("請先確認資料", "資料可能已過期", "不建議依此頁判讀", "資料來源"))


def test_template_data_availability_block_is_collapsed_by_default():
    template = TEMPLATE.read_text(encoding="utf-8")
    block = _outer_block(template, '<details class="today-briefing-details"')
    opening_tag = block.split(">", 1)[0]

    assert " open" not in opening_tag
    assert "📊 資料可用性" in block
    assert "⭐ 自選股優先項目" in block
    assert "⏰ 今日高影響事件" in block
    assert 'class="today-briefing-summary"' in block
