import pytest
import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from scripts.tx_night_session import (
    fetch_snapshot_with_fallback,
    fetch_fixture_snapshot,
)


def test_night_session_fixture_fallback():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    snapshot = fetch_fixture_snapshot(now)
    assert snapshot is not None
    assert snapshot["provider"] == "fixture"
    assert snapshot["is_fallback"] is True
    assert snapshot["price"] is not None


def test_night_session_template_provider_rendering():
    template_dir = Path(__file__).parent.parent / "scripts" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    tmpl = env.get_template("premarket.html.j2")

    # Case 1: Live provider (e.g. Yahoo / Wantgoo)
    night_live = {
        "date": "2026-08-22",
        "provider": "wantgoo",
        "provider_name": "Wantgoo / TAIFEX",
        "latest": {
            "provider": "wantgoo",
            "provider_name": "Wantgoo / TAIFEX",
            "price": 45074.0,
            "change": -64.0,
            "change_pct": -0.14,
            "is_fallback": False,
        }
    }

    html_live = tmpl.render(
        generated_at="2026/08/22 08:00",
        indices={},
        us_indices={},
        asia_open={},
        indices_missing=[],
        night=night_live,
        spark=None,
        disposal={},
        date_check={},
        pressplay={"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        institutional={"stocks": [], "matched_count": 0, "candidate_count": 0},
        calendar={"events": [], "grid": None},
        financials={},
        news=[],
        twse={},
    )
    assert "台指期夜盤 (05:00)" in html_live
    assert "來源：Wantgoo / TAIFEX" not in html_live
    assert "⚠️ 抓取失敗" not in html_live

    # Case 2: All 4 failed, fallback fixture
    night_fallback = {
        "date": "2026-08-22",
        "provider": "fixture",
        "provider_name": "fixtures/fallback",
        "latest": {
            "provider": "fixture",
            "provider_name": "fixtures/fallback",
            "price": 45203.0,
            "change": 65.0,
            "change_pct": 0.14,
            "is_fallback": True,
        }
    }

    html_fallback = tmpl.render(
        generated_at="2026/08/22 08:00",
        indices={},
        us_indices={},
        asia_open={},
        indices_missing=[],
        night=night_fallback,
        spark=None,
        disposal={},
        date_check={},
        pressplay={"not_found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "found_group": {"raw_tokens": [], "matched": [], "unmatched": []}, "source_article": {}},
        institutional={"stocks": [], "matched_count": 0, "candidate_count": 0},
        calendar={"events": [], "grid": None},
        financials={},
        news=[],
        twse={},
    )
    assert "⚠️ 抓取失敗，使用最近一次 fixtures/2026-08-22" in html_fallback
