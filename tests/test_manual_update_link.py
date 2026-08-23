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
    deployed_bridge = (ROOT / "docs" / "assets" / "manual-update-bridge.mjs").read_text(encoding="utf-8")
    source_bridge = (ROOT / "scripts" / "assets" / "manual-update-bridge.mjs").read_text(encoding="utf-8")
    assert re.search(rf'GATEWAY_ORIGIN\s*=\s*"{re.escape(GATEWAY_ORIGIN)}"', deployed_bridge)
    assert f'GATEWAY_ORIGIN = "{GATEWAY_ORIGIN}"' in source_bridge
    assert "manual-update-bridge.mjs" in page
    assert "windowRef.open(bridgeUrl.toString()" in source_bridge
    assert 'bridgeUrl.searchParams.set("origin", windowRef.location.origin)' in source_bridge
    assert 'bridgeUrl.searchParams.set("requestId", requestId)' in source_bridge
    assert "event.origin !== gatewayOrigin || event.source !== popup" in source_bridge
    assert 'data.source !== "premarket-update-gateway"' in source_bridge
    assert "GITHUB_TOKEN" not in page + source_bridge + deployed_bridge
    assert "PRIVATE KEY" not in page + source_bridge + deployed_bridge


def test_manual_update_keeps_popup_open_until_terminal_status():
    for path in (ROOT / "docs" / "index.html", ROOT / "scripts" / "templates" / "premarket.html.j2"):
        page = path.read_text(encoding="utf-8")
        assert "manual-update-bridge.mjs" in page
    bridge = (ROOT / "scripts" / "assets" / "manual-update-bridge.mjs").read_text(encoding="utf-8")
    assert 'data.state === "queued"' in bridge
    assert 'data.state === "completed"' in bridge
    assert 'data.state === "failed"' not in bridge  # failure remains the guarded final else branch
    queued_handler = re.search(r'if \(data\.state === "queued"\) \{(.*?)\} else if', bridge, re.DOTALL)
    assert queued_handler
    assert "popup.close" not in queued_handler.group(1)
    assert "try { popup.close(); }" in bridge
