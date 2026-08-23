from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _announcement_block(text: str) -> str:
    marker = '<details id="announcements"'
    start = text.index(marker)
    end = text.index("</details>", start) + len("</details>")
    return text[start:end]


def test_source_template_announcement_section_is_collapsed_by_default():
    block = _announcement_block(TEMPLATE.read_text(encoding="utf-8"))

    assert block.startswith('<details id="announcements"')
    assert '<summary class="section-heading compact"' in block
    assert ' open' in block.split(">", 1)[0]
    assert 'id="announcements-panel"' in block
    assert 'data-package="announcements"' in block


def test_deployed_announcement_section_keeps_outer_open_and_inner_rows_collapsed():
    page = DEPLOYED.read_text(encoding="utf-8")
    block = _announcement_block(page)
    app = (ROOT / "scripts" / "assets" / "app.js").read_text(encoding="utf-8")

    assert block.startswith('<details id="announcements"')
    assert '<summary class="section-heading compact"' in block
    assert ' open' in block.split(">", 1)[0]
    assert 'return `<details class="native-details" ${rows.length ? \'\' : \'\'}>' in app
    assert 'native-details" open' not in app
