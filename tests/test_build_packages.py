import json
from pathlib import Path

from scripts.build_packages import (
    _announcements_package,
    _candidate_package,
    _disposition_package,
    write_packages,
)


def test_disposition_package_sorts_shortest_rule_and_extracts_trigger():
    payload = _disposition_package({
        "date_check": {"page_says_applies_to": "08/24"},
        "one_flag_from_disposal": [{
            "market": "櫃", "code": "⏸3490", "name": "單井", "close": "53.9",
            "condition": "①53.0↑(-1.7%)", "earliest_disposal": "08-25 第2次2分",
            "badges": [
                {"short": "5", "title": "連5", "current": 2, "threshold": 5},
                {"short": "3①", "title": "連3", "current": 2, "threshold": 3},
            ],
        }],
        "currently_in_disposal": [],
    })
    item = payload["items"][0]
    assert item["code"] == "3490"
    assert item["primary_rule"]["id"] == "3①"
    assert item["trigger"]["price"] == 53.0
    assert item["trigger"]["direction"] == "up"


def test_candidate_package_adds_volume_max():
    payload = _candidate_package({
        "not_found_group": {"matched": [{"code": "2330", "name": "台積電", "volume": "1,000", "foreign": "+10"}]},
        "found_group": {"matched": [{"code": "2454", "name": "聯發科", "volume": "2,000", "foreign": "-5"}]},
    }, {})
    assert payload["matched_count"] == 2
    assert {item["volume_max"] for item in payload["items"]} == {2000.0}


def test_announcement_package_keeps_precomputed_delta():
    payload = _announcements_package({"att": [{
        "code": "2330", "name": "台積電", "parsed": {"EPS": 4.2, "上季EPS": 3.1}, "ai_score": 7,
    }]})
    row = payload["blocks"]["att"]["rows"][0]
    assert row["d_eps"] == 1.1
    assert row["ai_score"] == 7.0


def test_write_packages_creates_schema_and_files(tmp_path: Path):
    meta = write_packages(
        tmp_path,
        indices={}, night={}, disposal={}, pressplay={}, chengwaye_daily={},
        calendar={"events": []}, financials={}, news=[], twse={}, meta={"sources": []},
    )
    assert meta["schema_version"] == 1
    assert set(meta["hash"]) == {"disposition", "candidates", "announcements", "macro", "calendar", "news"}
    assert json.loads((tmp_path / "data" / "meta.json").read_text())["schema_version"] == 1
    candidates_raw = (tmp_path / "data" / "candidates.json").read_text(encoding="utf-8")
    assert "\n" not in candidates_raw
    assert ": " not in candidates_raw
