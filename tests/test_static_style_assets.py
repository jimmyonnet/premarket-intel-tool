from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_pages_referenced_style_assets_exist_and_are_substantive():
    page = (DOCS / "index.html").read_text(encoding="utf-8")
    expected = {
        "tokens.css": ("--n1", 1_000),
        "layout.css": (".topbar", 10_000),
    }

    for filename, (required_rule, minimum_size) in expected.items():
        asset = DOCS / "assets" / filename
        content = asset.read_text(encoding="utf-8")
        assert f'href="assets/{filename}"' in page
        assert asset.stat().st_size >= minimum_size
        assert required_rule in content


def test_manual_update_button_retains_existing_command_button_visual_class():
    page = (DOCS / "index.html").read_text(encoding="utf-8")

    assert 'class="cmdk manual-update-link"' in page
    assert 'id="manual-update-button"' in page
