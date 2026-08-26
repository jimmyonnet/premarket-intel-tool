from pathlib import Path

from bs4 import BeautifulSoup


TEMPLATE = Path("scripts/templates/premarket.html.j2").read_text(encoding="utf-8")


def test_theme_shortcut_is_unambiguous_and_announced():
    assert 'id="theme-toggle" type="button" title="切換深淺色主題 (快捷鍵 D)" aria-keyshortcuts="D"' in TEMPLATE
    assert TEMPLATE.count("快捷鍵 D") == 1
    assert 'class="nav-btn btn-snapshot"' not in TEMPLATE

    keyboard_start = TEMPLATE.index("document.addEventListener('keydown'")
    keyboard_end = TEMPLATE.index("\n  });", keyboard_start)
    keyboard_handler = TEMPLATE[keyboard_start:keyboard_end]
    assert "e.key === 'd' || e.key === 'D'" in keyboard_handler
    assert "window.toggleTheme();" in keyboard_handler


def test_debug_only_meta_consistency_warning_is_boot_scoped():
    boot_start = TEMPLATE.index("window.__PM_META__ =")
    boot_end = TEMPLATE.index("var savedTheme", boot_start)
    boot_script = TEMPLATE[boot_start:boot_end]

    assert "localStorage.getItem('pmit_debug') === '1'" in boot_script
    assert "Number(pmMeta.stale_hours) >= 24" in boot_script
    assert "pmMeta.overall_status === 'ready'" in boot_script
    assert "console.warn('[PMIT] stale_hours >= 24 but overall_status=ready', pmMeta);" in boot_script


def test_sortable_headers_use_aria_sort_and_delegated_keyboard_actions():
    soup = BeautifulSoup(TEMPLATE, "html.parser")
    sortable_headers = soup.select(".data-table thead th[data-sort-col]")

    assert len(sortable_headers) == 27
    assert not soup.select("th[onclick]")
    for header in sortable_headers:
        assert header.get("role") == "button"
        assert header.get("tabindex") == "0"
        assert header.get("aria-sort") == "none"

    assert "document.querySelectorAll('.data-table thead').forEach" in TEMPLATE
    assert "thead.addEventListener('click', sortFromEvent);" in TEMPLATE
    assert "thead.addEventListener('keydown'" in TEMPLATE
    assert "event.key !== 'Enter' && event.key !== ' '" in TEMPLATE
    assert "th.setAttribute('aria-sort', isAsc ? 'ascending' : 'descending');" in TEMPLATE
    assert "tbody.querySelectorAll(':scope > tr:not(.candidate-detail-row)')" in TEMPLATE
    assert "tbody.querySelectorAll('tr:not(.candidate-detail-row)')" not in TEMPLATE
