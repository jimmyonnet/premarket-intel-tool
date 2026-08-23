from pathlib import Path
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
import pytest


@pytest.fixture
def jinja_env():
    template_dir = Path(__file__).parent.parent / "scripts" / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)


def test_template_renders_ready_header_and_briefing_card(jinja_env):
    """Test rendering when status is ready."""
    tmpl = jinja_env.get_template("premarket.html.j2")
    
    health_data = {
        "overall_status": "ready",
        "status_label": "可用",
        "status_badge_class": "is-ready",
        "summary_reasons": ["所有資料來源正常"],
        "sources": [
            {
                "source_id": "indices",
                "name": "指數行情 (美股/亞股/ADR)",
                "is_required": True,
                "status": "ok",
                "fetched_at": "2026-08-24T07:35:00+08:00",
                "data_date": "08/24",
                "age_minutes": 5.0,
                "error_summary": None,
                "fallback_used": False,
                "impact_desc": "無影響"
            }
        ]
    }

    date_check_eval = {
        "status": "aligned_next",
        "label": "已對齊次日",
        "class_name": "is-ok",
        "tooltip": "資料已對齊次日"
    }

    html = tmpl.render(
        generated_at="2026/08/24 07:35",
        build_time="07:35",
        build_version="20260824_0735",
        data_date="08/24",
        stale_hours=0.1,
        hours_since_us_close=3.5,
        meta={"overall_status": "ready"},
        health=health_data,
        indices={},
        us_indices={},
        asia_open={},
        indices_missing=[],
        night={},
        spark=None,
        disposal={"one_flag_from_disposal": [], "currently_in_disposal": []},
        date_check={"page_says_applies_to": "08/24"},
        date_check_eval=date_check_eval,
        pressplay={"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        institutional={"stocks": [], "matched_count": 0, "candidate_count": 0},
        calendar={"events": [], "date_groups": []},
        financials={},
        news=[],
        twse={},
    )

    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Header Status Button
    status_btn = soup.find("button", id="source-status-btn")
    assert status_btn is not None
    assert "is-ready" in status_btn["class"]
    assert "可用" in status_btn.text

    # 2. Date Check Badge
    date_badge = soup.find("span", class_="status-badge")
    assert date_badge is not None
    assert "已對齊次日" in date_badge.text

    # 3. Today's Briefing Card
    briefing_card = soup.find("div", id="today-briefing-block")
    assert briefing_card is not None
    assert "is-ready-card" in briefing_card["class"]
    assert "資料可用性" in briefing_card.text

    # 4. Source Status Modal
    status_modal = soup.find("div", id="source-status-modal")
    assert status_modal is not None
    assert status_modal["role"] == "dialog"
    assert status_modal["aria-modal"] == "true"
    assert "指數行情" in status_modal.text


def test_template_renders_unsafe_header_and_alert_card(jinja_env):
    """Test rendering when status is unsafe."""
    tmpl = jinja_env.get_template("premarket.html.j2")
    
    health_data = {
        "overall_status": "unsafe",
        "status_label": "不建議依此頁判讀",
        "status_badge_class": "is-unsafe",
        "summary_reasons": ["必要來源【指數行情】抓取失敗"],
        "sources": [
            {
                "source_id": "indices",
                "name": "指數行情 (美股/亞股/ADR)",
                "is_required": True,
                "status": "failed",
                "fetched_at": "2026-08-24T07:35:00+08:00",
                "data_date": None,
                "age_minutes": 0.0,
                "error_summary": "連線逾時",
                "fallback_used": True,
                "impact_desc": "無法掌握美股收盤"
            }
        ]
    }

    date_check_eval = {
        "status": "warning",
        "label": "日期異常",
        "class_name": "is-danger",
        "tooltip": "處置資料日期不符"
    }

    html = tmpl.render(
        generated_at="2026/08/24 07:35",
        build_time="07:35",
        build_version="20260824_0735",
        data_date="08/24",
        stale_hours=15.0,
        hours_since_us_close=3.5,
        meta={"overall_status": "unsafe"},
        health=health_data,
        indices={},
        us_indices={},
        asia_open={},
        indices_missing=["^GSPC"],
        night={},
        spark=None,
        disposal={"one_flag_from_disposal": [], "currently_in_disposal": []},
        date_check={"page_says_applies_to": "08/20"},
        date_check_eval=date_check_eval,
        pressplay={"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        institutional={"stocks": [], "matched_count": 0, "candidate_count": 0},
        calendar={"events": [], "date_groups": []},
        financials={},
        news=[],
        twse={},
    )

    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Header Status Button
    status_btn = soup.find("button", id="source-status-btn")
    assert status_btn is not None
    assert "is-unsafe" in status_btn["class"]
    assert "不建議依此頁判讀" in status_btn.text

    # 2. Today's Briefing Card Alert
    briefing_card = soup.find("div", id="today-briefing-block")
    assert briefing_card is not None
    assert "is-unsafe-alert" in briefing_card["class"]
