from pathlib import Path


TEMPLATE = Path("scripts/templates/premarket.html.j2").read_text(encoding="utf-8")


def test_next_high_impact_event_tip_uses_existing_card_tip_style():
    assert 'id="cal-next-event-tip"' in TEMPLATE
    assert 'class="card-tip cal-next-event-tip"' in TEMPLATE
    assert 'window.pm.focusNextHighImpactEvent()' in TEMPLATE


def test_next_high_impact_event_prefers_nearby_star3_then_star2_fallback():
    assert "window.pm.findNextHighImpactEvent = function()" in TEMPLATE
    assert "item.importance === 3 && item.diffMs <= 7 * 24 * 3600 * 1000" in TEMPLATE
    assert "importance === 2" in TEMPLATE
    assert "formatCalendarCountdown" in TEMPLATE


def test_no_today_event_briefing_can_be_replaced_without_new_column():
    assert 'id="briefing-no-high-impact"' in TEMPLATE
    assert "window.pm.updateNextHighImpactPresentation" in TEMPLATE
    assert "今日無 ★★★ 重要總經事件" in TEMPLATE


def test_no_event_day_auto_navigation_respects_saved_state_and_user_scroll():
    assert "window.pm.calendarUserScrolled" in TEMPLATE
    assert "hasSavedCalendarGroups" in TEMPLATE
    assert "scrollIntoView({ block: 'nearest'" in TEMPLATE
    assert "window.pm.openCalendarDateSection" in TEMPLATE
