import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from scripts.fetch_disposal import parse_active, parse_one_away, DisposalEntry, expected_market_day


def test_disposal_entry_dataclass():
    """Test DisposalEntry retains countdown and source exit markers."""
    entry_none = DisposalEntry(code="1101", name="台泥", trading_days_left=None)
    assert entry_none.trading_days_left is None

    entry_zero = DisposalEntry(code="3293", name="鈊象", trading_days_left=0)
    assert entry_zero.trading_days_left == 0
    assert isinstance(entry_zero.trading_days_left, int)

    entry_three = DisposalEntry(code="2455", name="全新", trading_days_left=3)
    assert entry_three.trading_days_left == 3
    assert isinstance(entry_three.trading_days_left, int)

    entry_exit = DisposalEntry(code="3163", name="波若威", trading_days_left="出關")
    assert entry_exit.trading_days_left == "出關"


def test_fetch_disposal_parser_three_scenarios():
    """
    Test parsing from HTML fixture covering 3 scenarios:
    (a) 空白欄位: trading_days_left is None
    (b) 倒數今日: trading_days_left == 0
    (c) 倒數 N 日: trading_days_left == 3 (> 0)
    """
    fixture_path = Path(__file__).parent.parent / "fixtures" / "chengwaye_disposal.html"
    soup = BeautifulSoup(fixture_path.read_text(encoding="utf-8"), "html.parser")
    
    active_rows = parse_active(soup)
    assert len(active_rows) == 3

    # (a) 已出關 (empty cell -> None)
    stock_a = next(r for r in active_rows if r["code"] == "1101")
    assert stock_a["trading_days_left"] is None

    # (b) 倒數今日 (0 -> 0)
    stock_b = next(r for r in active_rows if r["code"] == "3293")
    assert stock_b["trading_days_left"] == 0

    # (c) 倒數 N 日 (3天 -> 3)
    stock_c = next(r for r in active_rows if r["code"] == "2455")
    assert stock_c["trading_days_left"] == 3


def test_non_trading_day_uses_next_twse_session_for_source_context():
    from datetime import date

    assert expected_market_day(date(2026, 8, 23)).isoformat() == "2026-08-24"


def test_template_rendering_filters_and_hidden_comment():
    """
    Test Jinja2 template rendering:
    - Stocks with trading_days_left=None are filtered
    - Outputs <!-- 隱藏 X 筆（資料缺欄位，請回報） -->
    - Stocks with countdown 0 or 3 days are handled properly
    """
    template_dir = Path(__file__).parent.parent / "scripts" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    tmpl = env.get_template("premarket.html.j2")

    disposal_data = {
        "date_check": {"page_says_applies_to": "08/22", "today": "2026-08-22", "applies_to_matches_today": True},
        "one_flag_from_disposal": [
            {"market": "市", "code": "2330", "name": "台積電", "close": "1080", "condition": "1000↑", "earliest_disposal": "08-26", "badges": [], "condition_segments": []}
        ],
        "two_flags_from_disposal": [],
        "currently_in_disposal": [
            # (a) trading_days_left = None
            {"market": "市", "code": "1101", "name": "台泥", "matching": "5分", "start_date": "08-01", "end_date": "08-15", "exit_date": "08-18", "trading_days_left": None, "reason": "第1次"},
            # (b) trading_days_left = 0
            {"market": "櫃", "code": "3293", "name": "鈊象", "matching": "20分", "start_date": "08-08", "end_date": "08-21", "exit_date": "08-22", "trading_days_left": 0, "reason": "第2次"},
            # (c) trading_days_left = 3
            {"market": "市", "code": "2455", "name": "全新", "matching": "2分", "start_date": "08-24", "end_date": "08-28", "exit_date": "08-31", "trading_days_left": 3, "reason": "第2次"},
        ]
    }

    rendered_html = tmpl.render(
        generated_at="2026/08/22 08:00",
        build_time="08:00",
        data_date="2026-08-22",
        stale_hours=0,
        hours_since_us_close=4.0,
        indices={},
        us_indices={},
        asia_open={},
        indices_missing=[],
        night={},
        spark=None,
        disposal=disposal_data,
        date_check=disposal_data["date_check"],
        pressplay={"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        institutional={"stocks": [], "matched_count": 0, "candidate_count": 0},
        calendar={"events": [], "grid": None},
        financials={
            "att": [],
            "fin": [],
            "rev": [],
            "source_status": {"rev": {"state": "fetch_failed"}},
        },
        news=[],
        twse={},
    )

    # Verify hidden count comment is present
    assert "<!-- 隱藏 1 筆（資料缺欄位，請回報） -->" in rendered_html
    # Verify stock (b) 3293 is rendered under exiting
    assert "3293" in rendered_html
    assert "即時營收（資料抓取失敗，無法確認市場未反映筆數）" in rendered_html
    assert "抓取失敗" in rendered_html
