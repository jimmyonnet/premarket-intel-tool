from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"


def test_manual_candidate_controls_are_rendered_in_watchlist_section():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'id="manual-candidate-panel" hidden' in source
    assert 'id="manual-candidate-input"' in source
    assert 'id="manual-candidate-list"' in source
    assert 'onclick="window.pm.addManualCandidate()"' in source
    assert '＋加入籌碼股' in source


def test_manual_candidate_state_and_keyboard_contract():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "pmit_manual_candidates" in source
    assert "window.pm.addManualCandidate = function()" in source
    assert "window.pm.removeManualCandidate = function(code)" in source
    assert "window.pm.renderManualCandidates();" in source
    assert "e.target.id === 'manual-candidate-input'" in source
    assert "https://chengwaye.com/stock/" in source


def test_manual_candidate_settings_are_backed_up_and_validated():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "'pmit_manual_candidates'" in source
    assert "key === 'pmit_watchlist' || key === 'pmit_manual_candidates'" in source
    assert "股票代號清單格式無效" in source
