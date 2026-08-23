from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ORIGIN = "https://premarket-gw-pxz3yyqw.manus.space"
WORKFLOW_URL = "https://github.com/jimmyonnet/premarket-intel-tool/actions/workflows/build-premarket-page.yml"


def test_deployed_page_has_in_place_manual_update_button():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'id="manual-update-button"' in page
    assert 'type="button"' in page
    assert "🔄 手動更新資料" in page
    assert WORKFLOW_URL not in page
    assert 'target="_blank"' not in page


def test_template_has_in_place_manual_update_button():
    template = (ROOT / "scripts" / "templates" / "premarket.html.j2").read_text(encoding="utf-8")
    assert 'id="manual-update-button"' in template
    assert 'class="cmdk manual-update-link"' in template
    assert 'aria-label="手動更新資料"' in template
    assert WORKFLOW_URL not in template


def test_manual_update_uses_strict_gateway_bridge_without_client_credentials():
    script = (ROOT / "scripts" / "assets" / "app.js").read_text(encoding="utf-8")
    assert f"MANUAL_UPDATE_GATEWAY_ORIGIN = '{GATEWAY_ORIGIN}'" in script
    assert "window.open(bridgeUrl.toString()" in script
    assert "bridgeUrl.searchParams.set('origin', window.location.origin)" in script
    assert "bridgeUrl.searchParams.set('requestId', requestId)" in script
    assert "if (event.origin !== MANUAL_UPDATE_GATEWAY_ORIGIN) return;" in script
    assert "data.source !== 'premarket-update-gateway'" in script
    assert "data.requestId !== requestId" in script
    assert "GITHUB_TOKEN" not in script
    assert "PRIVATE KEY" not in script
