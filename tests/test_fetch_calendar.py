from datetime import date

from scripts.fetch_calendar import (
    generate_tw_market_rule_events,
    get_local_rule_range_end,
    merge_tw_market_rule_events,
)


def _event_by_type(events, semantic_type):
    return next(event for event in events if event.get("semantic_type") == semantic_type)


def test_tw_market_rules_generate_september_revenue_settlement_quarter_end_and_holiday():
    events = generate_tw_market_rule_events(
        date(2026, 9, 1),
        date(2026, 9, 30),
        holidays={"2026-09-25"},
    )

    assert _event_by_type(events, "revenue_deadline")["date"] == "2026-09-10"
    settlement = _event_by_type(events, "futures_settlement")
    assert settlement["date"] == "2026-09-16"
    assert settlement["importance"] == 3
    assert _event_by_type(events, "quarter_end_trading_day")["date"] == "2026-09-30"
    assert _event_by_type(events, "market_holiday")["date"] == "2026-09-25"

    for event in events:
        assert event["source"] == "local-rule"
        assert event["country"] == "TW"
        assert event["flag"] == "🇹🇼"
        assert event["category"] in {"macro", "holiday"}
        assert event["note"]


def test_tw_market_settlement_moves_to_next_trading_day_when_third_wednesday_is_holiday():
    events = generate_tw_market_rule_events(
        date(2026, 2, 1),
        date(2026, 2, 28),
        holidays={"2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20"},
    )

    settlement = _event_by_type(events, "futures_settlement")
    assert settlement["date"] == "2026-02-23"
    assert "順延至 02/23" in settlement["note"]


def test_local_rule_range_extends_through_next_complete_month():
    assert get_local_rule_range_end(date(2026, 8, 24), date(2026, 9, 7)) == date(2026, 9, 30)
    assert get_local_rule_range_end(date(2026, 12, 24), date(2027, 1, 7)) == date(2027, 1, 31)


def test_external_same_day_same_semantic_event_has_priority_over_local_rule():
    local_events = generate_tw_market_rule_events(
        date(2026, 9, 1),
        date(2026, 9, 30),
        holidays={"2026-09-25"},
    )
    external_events = [{
        "id": "external-revenue-20260910",
        "date": "2026-09-10",
        "time": "09:00",
        "title": "台灣 8 月營收公布",
        "summary": "台灣 8 月營收公布",
        "country": "TW",
        "category": "macro",
    }]

    merged = merge_tw_market_rule_events(external_events, local_events)
    sep_10_events = [event for event in merged if event["date"] == "2026-09-10"]

    assert sep_10_events == external_events
    assert [event["date"] for event in merged] == sorted(event["date"] for event in merged)
