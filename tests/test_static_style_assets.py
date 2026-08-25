from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_280_visual_baseline_uses_self_contained_inline_style_system():
    page = (DOCS / "index.html").read_text(encoding="utf-8")
    template = (ROOT / "scripts" / "templates" / "premarket.html.j2").read_text(encoding="utf-8")

    for visual_contract in ("--bg-page", ".page-header", ".page-nav", ".content-section", ".nav-btn"):
        assert visual_contract in page
        assert visual_contract in template
    assert '<link rel="stylesheet" href="assets/tokens.css">' not in page
    assert '<link rel="stylesheet" href="assets/layout.css">' not in page
    assert 'assets/style.css' not in page
    assert '<link href="https://fonts.googleapis.com/css2?' in page
    assert not (DOCS / "assets" / "style.css").exists()


def test_manual_update_button_retains_280_navigation_button_visual_class():
    page = (DOCS / "index.html").read_text(encoding="utf-8")

    assert 'class="nav-btn manual-update-btn"' in page
    assert 'id="manual-update-button"' in page
