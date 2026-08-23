from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ORIGIN = "https://premarket-gw-pxz3yyqw.manus.space"
WORKFLOW_URL = "https://github.com/jimmyonnet/premarket-intel-tool/actions/workflows/build-premarket-page.yml"


def test_deployed_page_keeps_280_visual_button_class_with_in_place_update():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    button = re.search(r'<button class="nav-btn manual-update-btn" id="manual-update-button"[^>]*>.*?</button>', page)
    assert button
    assert 'class="nav-btn manual-update-btn"' in page
    assert "🔄 手動更新資料" in page
    assert f'href="{WORKFLOW_URL}"' not in page
    assert 'target="_blank"' not in button.group(0)


def test_template_keeps_280_visual_button_class_with_in_place_update():
    template = (ROOT / "scripts" / "templates" / "premarket.html.j2").read_text(encoding="utf-8")
    assert '<button class="nav-btn manual-update-btn" id="manual-update-button" type="button"' in template
    assert 'class="nav-btn manual-update-btn"' in template
    assert f'href="{WORKFLOW_URL}"' not in template


def test_manual_update_uses_strict_gateway_bridge_without_client_credentials():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert f"GATEWAY_ORIGIN = '{GATEWAY_ORIGIN}'" in page
    assert "window.open(bridgeUrl.toString()" in page
    assert "bridgeUrl.searchParams.set('origin', window.location.origin)" in page
    assert "bridgeUrl.searchParams.set('requestId', requestId)" in page
    assert "event.origin !== GATEWAY_ORIGIN || event.source !== popup" in page
    assert "data.source !== 'premarket-update-gateway'" in page
    assert "GITHUB_TOKEN" not in page
    assert "PRIVATE KEY" not in page
