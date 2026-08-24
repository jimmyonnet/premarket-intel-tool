from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_URL = "https://github.com/jimmyonnet/premarket-intel-tool/actions/workflows/build-premarket-page.yml"


def _read_template():
    return (ROOT / "scripts" / "templates" / "premarket.html.j2").read_text(encoding="utf-8")


def _read_page():
    return (ROOT / "docs" / "index.html").read_text(encoding="utf-8")


def _assert_direct_workflow_link(source):
    link = re.search(
        r'<a class="nav-btn manual-update-btn" id="manual-update-button"[^>]*>.*?</a>',
        source,
    )
    assert link, "手動更新控制必須是可直接開啟 workflow 的連結"
    markup = link.group(0)
    assert f'href="{WORKFLOW_URL}"' in markup
    assert 'target="_blank"' in markup
    assert 'rel="noopener noreferrer"' in markup
    assert 'title="開啟 GitHub Actions 手動執行頁面"' in markup
    assert 'aria-label="開啟 GitHub Actions 手動執行頁面"' in markup
    assert "🔄 手動更新資料" in markup


def test_deployed_page_links_manual_update_to_workflow():
    page = _read_page()
    _assert_direct_workflow_link(page)
    assert "manual-update-bridge.mjs" not in page
    assert "premarket-gw-pxz3yyqw.manus.space" not in page


def test_template_links_manual_update_to_workflow():
    template = _read_template()
    _assert_direct_workflow_link(template)
    assert "manual-update-bridge.mjs" not in template
    assert "premarket-gw-pxz3yyqw.manus.space" not in template


def test_manual_update_keeps_visual_button_class_and_id():
    for source in (_read_template(), _read_page()):
        assert 'class="nav-btn manual-update-btn"' in source
        assert 'id="manual-update-button"' in source


def test_manual_update_link_has_no_client_credentials_or_old_gateway_reference():
    source_files = [
        ROOT / "scripts" / "templates" / "premarket.html.j2",
        ROOT / "templates" / "premarket.html.j2",
        ROOT / "docs" / "index.html",
        ROOT / "scripts" / "assets" / "app.js",
        ROOT / "docs" / "assets" / "app.js",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    assert "GITHUB_TOKEN" not in combined
    assert "PRIVATE KEY" not in combined
    assert "premarket-gw-pxz3yyqw.manus.space" not in combined
    assert "workflow_dispatch_locks" not in combined


def test_manual_update_direct_link_is_not_a_form_submission():
    for source in (_read_template(), _read_page()):
        link = re.search(
            r'<a class="nav-btn manual-update-btn" id="manual-update-button"[^>]*>.*?</a>',
            source,
        )
        assert link
        assert "onclick=" not in link.group(0)
        assert "type=\"button\"" not in link.group(0)
