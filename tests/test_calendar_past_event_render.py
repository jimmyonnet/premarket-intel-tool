from pathlib import Path


TEMPLATE = Path("scripts/templates/premarket.html.j2").read_text(encoding="utf-8")


def test_past_event_styles_follow_the_requested_muted_treatment():
    assert ".cal-event-card.is-past {" in TEMPLATE
    assert "opacity: 0.55;" in TEMPLATE
    assert ".cal-event-card.is-past .cal-card-title" in TEMPLATE
    assert "color: var(--text-muted);" in TEMPLATE
    assert ".cal-event-card.is-past .cal-countdown-badge" in TEMPLATE
    assert "display: none;" in TEMPLATE


def test_past_events_use_two_hour_threshold_and_collapse_once_per_group():
    assert "window.pm.markPastEvents = function(nowMs)" in TEMPLATE
    assert "nowMs - evTime > 2 * 3600 * 1000" in TEMPLATE
    assert "cdBadge.textContent = '已公布';" in TEMPLATE
    assert "data-past-auto-collapsed" in TEMPLATE
    assert "allPast" in TEMPLATE


def test_today_filter_falls_back_to_next_matching_future_date_group():
    assert "window.pm.calendarCardMatchesFilters" in TEMPLATE
    assert "quickVal === 'today' && totalVisible === 0" in TEMPLATE
    assert "findNextCalendarFallbackSection" in TEMPLATE
    assert "今日無事件 · 顯示下一個：" in TEMPLATE
