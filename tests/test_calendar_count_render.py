from pathlib import Path


TEMPLATE = Path("scripts/templates/premarket.html.j2").read_text(encoding="utf-8")


def test_calendar_count_is_concise_by_default_and_retains_filter_context():
    assert 'id="cal-count-badge">{{ calendar.events|length }} 筆</span>' in TEMPLATE
    assert "顯示 {{ calendar.events|length }} / {{ calendar.events|length }} 筆" not in TEMPLATE
    assert "else if (totalVisible === totalAll)" in TEMPLATE
    assert "badge.textContent = totalAll + ' 筆';" in TEMPLATE
    assert "badge.textContent = totalVisible + ' / ' + totalAll + ' 筆';" in TEMPLATE
    assert "今日無事件 · 顯示下一個：" in TEMPLATE
