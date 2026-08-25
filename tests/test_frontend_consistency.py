from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "scripts/templates/premarket.html.j2").read_text(encoding="utf-8")
PAGE = (ROOT / "docs/index.html").read_text(encoding="utf-8")
SW = (ROOT / "docs/sw.js").read_text(encoding="utf-8")


def test_live_template_uses_delegated_rows_and_has_no_unused_app_bundle_reference():
    # The real page is server-rendered by the Jinja template; app.js was never
    # loaded, so the contract must cover the live source rather than a dead copy.
    assert "document.addEventListener('click'" in TEMPLATE
    assert "row.addEventListener('click'" not in TEMPLATE
    assert "root.querySelectorAll('[data-code]').forEach" not in TEMPLATE
    assert "scripts/assets/app.js" not in TEMPLATE
    assert "assets/app.js" not in PAGE
    assert "<iframe" not in TEMPLATE
    assert "<iframe" not in PAGE
    assert "embed/" not in SW


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


def test_news_package_is_capped_and_links_are_scheme_checked_in_live_template():
    assert "items = items.slice(0, 10);" in TEMPLATE
    assert "/^https?:\\/\\//i.test(candidateUrl)" in TEMPLATE
    assert "link.href = item.link || '#'" not in TEMPLATE
