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
    assert "min-height: 32px;" in mobile_rules
    assert ".cal-search-input" in mobile_rules
    assert "width: 100%;" in mobile_rules
