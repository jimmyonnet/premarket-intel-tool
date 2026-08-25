from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "scripts/assets/app.js").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "scripts/templates/premarket.html.j2").read_text(encoding="utf-8")
SW = (ROOT / "docs/sw.js").read_text(encoding="utf-8")


def test_app_uses_delegated_rows_and_cross_match_deduplication():
    assert "bindDelegatedEvents" in APP
    assert "document.addEventListener('click'" in APP
    assert "state.crossMatchSignature" in APP
    assert "const seenSignals = new Set()" in APP
    assert "row.addEventListener('click'" not in APP
    assert "root.querySelectorAll('[data-code]').forEach" not in APP


def test_live_template_uses_stable_watch_container_actions_without_duplicate_sw_listener():
    assert "summaryChip.onclick" not in TEMPLATE
    assert 'class="wc-del" onclick=' not in TEMPLATE
    assert "data-focus-watch" in TEMPLATE
    assert "data-delete-watch" in TEMPLATE
    assert "data-watch-filter" in TEMPLATE
    assert TEMPLATE.count("navigator.serviceWorker.addEventListener('message'") == 1
    assert "var savedTheme =" in TEMPLATE
    assert "var activeTheme =" not in TEMPLATE


def test_service_worker_revalidates_json_and_has_revision_contract():
    assert "const DATA_REVISION = '" in SW
    assert "pmit-202" in SW or "pmit-build-data-revision" in SW
    assert "cache: 'no-store'" in SW
    assert "isDataRequest" in SW
    assert "networkFirst(event.request, event.request, true)" in SW
    assert "dataRevision: DATA_REVISION" in SW
