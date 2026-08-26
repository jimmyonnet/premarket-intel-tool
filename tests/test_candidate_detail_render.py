import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
sys.path.insert(0, str(ROOT / "scripts"))

from build_page import build_institutional_section


def _pressplay(code="2489", name="瑞軒"):
    row = {
        "code": code,
        "name": name,
        "market": "市",
        "close": 35.65,
        "volume": "35,364",
        "foreign": "+1,381",
        "trust": "0",
        "dealer": "+1,019",
    }
    return {
        "source_article": {},
        "_status": "ok",
        "not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []},
        "found_group": {"raw_tokens": [code], "matched": [row], "unmatched": []},
    }


def _daily(code="2489"):
    return {
        "page_date": "2026/08/21",
        "codes": {
            code: {
                "name": "瑞軒",
                "buyers": [{"name": "富邦", "net": 2705868, "buyV": 2816000, "sellV": 110132, "buyP": 35.61, "sellP": 35.16}] * 16,
                "sellers": [{"name": "美商高盛", "net": -915609, "buyV": 1263391, "sellV": 2179000, "buyP": 34.91, "sellP": 35.01}] * 16,
                "daytraders": [{"name": "凱基台北", "total": 1451000, "buyV": 1180000, "sellV": 271000, "buyP": 35.36, "sellP": 34.61}] * 11,
            }
        },
    }


def _history(code="2489"):
    return {
        "codes": {
            code: {
                "code": code,
                "name": "瑞軒",
                "source_url": f"https://chengwaye.com/stock/{code}",
                "summary": {
                    "limit_up_count": "3 次",
                    "latest_limit_up": "2026/08/21",
                    "avg_next_open": "+2.00%",
                    "avg_next_close": "+1.50%",
                },
                "period_note": "統計自 2026/03/17 起",
                "records": [{
                    "date": "2026/08/21",
                    "close": "35.65",
                    "group": "電子零組件",
                    "next_open": "+2.00%",
                    "next_avg": "+1.00%",
                    "next_close": "+1.50%",
                    "next_trend": "續漲",
                }],
            }
        }
    }


def test_institutional_builder_keeps_candidate_detail_limits_and_clean_codes():
    section = build_institutional_section(_pressplay("2489⏸"), _daily(), _history())

    assert section["matched_count"] == 1
    detail = section["stocks"][0]
    assert detail["code"] == "2489"
    assert len(detail["buyers"]) == 15
    assert len(detail["sellers"]) == 15
    assert len(detail["daytraders"]) == 10
    assert detail["limit_up_history"]["summary"]["limit_up_count"] == "3 次"
    assert detail["buyers"][0]["net"] == "+2,706"
    assert detail["sellers"][0]["net"] == "-916"
    assert section["stocks_by_code"]["2489"] == detail


def test_candidate_template_renders_expandable_chengwaye_details():
    env = Environment(loader=FileSystemLoader(str(TEMPLATE.parent)), autoescape=True)
    rendered = env.get_template(TEMPLATE.name).render(
        generated_at="2026/08/24 20:00",
        build_time="20:00",
        data_date="2026-08-24",
        stale_hours=0,
        hours_since_us_close=4.0,
        indices={},
        us_indices={},
        asia_open={},
        indices_missing=[],
        night={},
        spark=None,
        disposal={"date_check": {}, "one_flag_from_disposal": [], "two_flags_from_disposal": [], "currently_in_disposal": []},
        date_check={},
        pressplay=_pressplay(),
        institutional=build_institutional_section(_pressplay(), _daily(), _history()),
        stock_history=_history(),
        calendar={"events": [], "grid": None},
        financials={},
        news=[],
        twse={},
    )

    assert 'id="candidate-detail-2489"' in rendered
    assert 'data-detail-id="candidate-detail-2489"' in rendered
    assert 'class="candidate-detail-row"' in rendered
    assert '<h4 class="candidate-detail-title">2489 瑞軒</h4>' in rendered
    assert "Chengwaye 籌碼明細" not in rendered
    assert "法人買賣 · 買超 Top15" in rendered
    assert "法人買賣 · 賣超 Top15" in rendered
    assert "當沖 Top10" in rendered
    assert rendered.count('class="table-scroll candidate-detail-table-scroll"') == 3
    assert rendered.count("{{ item.sellV }}") == 0
    assert "-916" in rendered
    assert "2,179" in rendered
    assert "個股漲停履歷" in rendered
    assert "漲停次數" in rendered
    assert "+2.00%" in rendered
    assert 'href="https://chengwaye.com/stock/2489"' in rendered
    assert "window.pm.toggleCandidateDetail(row)" in rendered
    assert "window.pm.openCandidateInsight" not in rendered
    assert "candidate-insight-" not in rendered
    assert "candidate-institutional-details" not in rendered
    assert 'href="https://chengwaye.com/daily"' in rendered
    assert ".candidate-detail-table-scroll .candidate-detail-table { min-width: 640px; }" in rendered
    assert ".candidate-detail-table-scroll .candidate-detail-table {\n      display: table;\n      min-width: 640px;" in rendered
    assert ".candidate-detail-table-scroll .candidate-detail-table td::before { display: none; content: none; }" in rendered


def test_candidate_rows_keep_sort_and_open_detail_contracts_without_search_box():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "tr:not(.candidate-detail-row)" in source
    assert source.count('<tr class="candidate-stock-row"') == 2
    assert "#watchlist tr.candidate-stock-row" in source
    assert "candidate-detail-row" in source
    assert "window.pm.toggleCandidateDetail" in source
    assert "window.pm.openCandidateInsight" not in source
    assert 'id="candidate-search"' not in source
    assert "window.pm.filterCandidateTable" not in source
