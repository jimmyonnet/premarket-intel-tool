from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "scripts" / "templates" / "premarket.html.j2"


def test_template_persists_existing_work_state_without_ui_rebuild():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "pmit_ui_state_v1" in source
    assert "window.pm.saveUiState" in source
    assert "candidateDetails" in source
    assert "calendarGroups" in source
    assert "watchlistExpanded" in source
    assert "watchEditOpen" in source
    assert "document.querySelectorAll('details')" in source
    assert "data-pmit-state-key" in source
    assert "window.pm.uiState.candidateDetails[detailId] = opening" in source
    assert "window.pm.uiState.watchlistExpanded = window.pm.watchlistExpanded" in source
    assert "window.pm.uiState.watchEditOpen = isHidden" in source
