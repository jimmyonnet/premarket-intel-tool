from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_URL = "https://github.com/jimmyonnet/premarket-intel-tool/actions/workflows/build-premarket-page.yml"


def test_deployed_page_has_manual_update_link():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert WORKFLOW_URL in page
    assert 'class="nav-btn manual-update-btn"' in page
    assert 'target="_blank"' in page
    assert 'rel="noopener noreferrer"' in page
    assert "🔄 手動更新資料" in page


def test_template_has_manual_update_link():
    template = (ROOT / "scripts" / "templates" / "premarket.html.j2").read_text(encoding="utf-8")
    assert WORKFLOW_URL in template
    assert 'class="cmdk manual-update-link"' in template
    assert 'target="_blank"' in template
    assert 'rel="noopener noreferrer"' in template
    assert "🔄 手動更新資料" in template
