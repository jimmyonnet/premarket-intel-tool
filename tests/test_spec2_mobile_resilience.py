from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _quick_action_labels(source: str) -> list[str]:
    soup = BeautifulSoup(source, "html.parser")
    label = next(node for node in soup.select(".utility-section-label") if node.get_text(strip=True) == "快速操作")
    return ["".join(control.stripped_strings) for control in label.parent.select(".nav-btn")]


def test_quick_controls_remain_limited_to_three_existing_actions():
    assert _quick_action_labels(TEMPLATE.read_text(encoding="utf-8")) == [
        "🌙 深色",
        "🔄 手動更新資料",
        "🔄 重新整理",
    ]
    assert _quick_action_labels(DEPLOYED.read_text(encoding="utf-8")) == [
        "🌙 深色",
        "🔄 手動更新資料",
        "🔄 重新整理",
    ]


def test_spec2_resilience_contract_is_present_in_template_and_deployed_page():
    for path in (TEMPLATE, DEPLOYED):
        source = path.read_text(encoding="utf-8")
        assert "window.pm.fetchJson" in source
        assert "cache: 'no-store'" in source
        assert "window.pm.showPackageError" in source
        assert "window.pm.exportSettings" in source
        assert "window.pm.importSettings" in source
        assert "data-relative" in source
        assert 'id="holiday-notice"' in source
        assert 'id="source-health-hint"' in source
        assert 'id="pmit-log"' in source
        assert "g + 1~6" in source


def test_snapshot_mode_is_session_only():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "if (window.pm.uiState.snapshotMode) document.body.classList.add('snapshot-mode')" not in source
    assert "Screenshot mode is intentionally session-only" in source
    assert "document.body.classList.remove('snapshot-mode')" in source


def test_holiday_and_service_worker_assets_are_present():
    holiday_path = ROOT / "docs" / "data" / "tw_holidays.json"
    sw_path = ROOT / "docs" / "sw.js"
    assert holiday_path.exists()
    assert '"typhoon"' in holiday_path.read_text(encoding="utf-8")
    assert "./data/tw_holidays.json" in sw_path.read_text(encoding="utf-8")
