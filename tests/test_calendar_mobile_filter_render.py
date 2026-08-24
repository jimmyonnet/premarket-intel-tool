from pathlib import Path


TEMPLATE = Path("scripts/templates/premarket.html.j2").read_text(encoding="utf-8")


def test_mobile_calendar_filter_toolbar_uses_authorized_scroll_and_wrap_rules():
    mobile_rule_start = TEMPLATE.index("@media (max-width: 768px) {", TEMPLATE.index("/* MOBILE NAV & BADGE */"))
    mobile_rule_end = TEMPLATE.index("\n  }", mobile_rule_start)
    mobile_rules = TEMPLATE[mobile_rule_start:mobile_rule_end]

    assert ".cal-filter-toolbar" in mobile_rules
    assert "overflow-x: auto;" in mobile_rules
    assert "-webkit-overflow-scrolling: touch;" in mobile_rules
    assert ".cal-filter-row" in mobile_rules
    assert "flex-wrap: nowrap;" in mobile_rules
    assert "min-width: max-content;" in mobile_rules
    assert ".cal-filter-row.secondary" in mobile_rules
    assert "flex-wrap: wrap;" in mobile_rules
    assert "min-width: 0;" in mobile_rules
    assert ".cal-chip" in mobile_rules
    assert "flex: 0 0 auto;" in mobile_rules
    assert "min-height: 36px;" in mobile_rules
    assert "padding: 6px 12px;" in mobile_rules
    assert ".cal-search-input" in mobile_rules
    assert "width: 100%;" in mobile_rules
    assert "font-size: 16px;" in mobile_rules


def test_mobile_primary_navigation_scrolls_in_one_touch_sized_row():
    nav_rule_start = TEMPLATE.index("@media (max-width: 768px) {", TEMPLATE.index("/* NAV"))
    nav_rule_end = TEMPLATE.index("\n  }", nav_rule_start)
    nav_rules = TEMPLATE[nav_rule_start:nav_rule_end]

    assert ".nav-sections" in nav_rules
    assert "justify-content: flex-start;" in nav_rules
    assert "flex-wrap: nowrap;" in nav_rules
    assert "overflow-x: auto;" in nav_rules
    assert "-webkit-overflow-scrolling: touch;" in nav_rules
    assert ".nav-link" in nav_rules
    assert "flex: 0 0 auto;" in nav_rules
    assert "height: 40px;" in nav_rules
    assert "padding: 0 12px;" in nav_rules
    assert ".nav-utility-panel" in nav_rules
    assert "justify-content: flex-end;" in nav_rules


def test_mobile_optimization_contracts_cover_safe_area_inputs_tables_and_feedback():
    assert 'content="width=device-width, initial-scale=1, viewport-fit=cover"' in TEMPLATE
    for token in ("--safe-top", "--safe-bottom", "--safe-left", "--safe-right"):
        assert token in TEMPLATE
    assert ".page-main { padding-bottom: calc(60px + var(--safe-bottom)); }" in TEMPLATE
    assert ".back-to-top" in TEMPLATE and "right: calc(24px + var(--safe-right));" in TEMPLATE
    assert ".watch-input-modern," in TEMPLATE
    assert ".cal-search-input," in TEMPLATE
    assert ".nav-utility-content input { font-size: 16px; }" in TEMPLATE
    assert ".table-scroll.is-overflowing::before" in TEMPLATE
    assert "min-width: 640px;" in TEMPLATE
    assert ".disposal-table th:nth-child(2)" in TEMPLATE
    assert ".disposal-table td:nth-child(2)" in TEMPLATE
    assert ".content-section {" in TEMPLATE
    assert "content-visibility: auto;" in TEMPLATE
    assert ".nav-btn:active" in TEMPLATE
