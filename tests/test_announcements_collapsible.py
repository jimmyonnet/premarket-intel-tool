from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _announcement_block(text: str) -> str:
    source_marker = '<details id="announcements"'
    deployed_marker = '<details class="card announcements-collapsible"'
    if source_marker in text:
        start = text.index(source_marker)
        end = text.index("</details>", start) + len("</details>")
    else:
        start = text.index(deployed_marker)
        end_marker = '      </details>\n    </section>'
        end = text.index(end_marker, start) + len('      </details>')
    return text[start:end]


def test_source_template_announcement_section_is_collapsed_by_default():
    block = _announcement_block(TEMPLATE.read_text(encoding="utf-8"))

    assert block.startswith('<details id="announcements"')
    assert '<summary class="section-heading compact"' in block
    assert ' open' in block.split(">", 1)[0]


def test_deployed_announcement_card_shows_collapsed_rows_by_default():
    block = _announcement_block(DEPLOYED.read_text(encoding="utf-8"))

    assert block.startswith('<details class="card announcements-collapsible"')
    assert '<summary class="card-head"' in block
    assert ' open' in block.split(">", 1)[0]
    assert block.count('class="unref-accordion"') == 3
    assert 'class="unref-accordion" open' not in block
