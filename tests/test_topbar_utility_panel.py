from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _nav_block(source: str) -> str:
    start = source.index('<nav class="page-nav"')
    end = source.index("</nav>", start) + len("</nav>")
    return source[start:end]


def test_low_frequency_controls_and_data_status_are_collapsed_in_utility_panel():
    source = TEMPLATE.read_text(encoding="utf-8")
    nav = _nav_block(source)
    opening_tag = nav[nav.index('<details class="nav-utility-panel"'):].split(">", 1)[0]

    assert " open" not in opening_tag
    assert "⚙️ 工具與資料狀態" in nav
    assert '<div class="nav-actions">' in nav
    assert '<details class="today-briefing-details" id="today-briefing-details">' in nav
    for control_id in ("briefing-toggle", "filter-watch-toggle", "manual-update-button"):
        assert f'id="{control_id}"' in nav


def test_open_utility_panel_keeps_its_trigger_in_the_top_right():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert ".nav-utility-panel[open] { flex-basis: 100%; }" not in source
    assert ".nav-utility-content {\n    position: absolute;" in source
    assert "right: 0;" in source
    assert "top: calc(100% + 8px);" in source


def test_deployed_page_keeps_utility_panel_collapsed_and_summary_anchor_ready():
    page = DEPLOYED.read_text(encoding="utf-8")
    nav = _nav_block(page)
    opening_tag = nav[nav.index('<details class="nav-utility-panel"'):].split(">", 1)[0]

    assert " open" not in opening_tag
    assert "⚙️ 工具與資料狀態" in nav
    assert 'id="summary-briefing-anchor"' in page
