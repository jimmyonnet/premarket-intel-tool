import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_chengwaye_stock_history import collect_codes, parse_stock_page


FIXTURE = ROOT / "tests" / "fixtures" / "chengwaye_stock_5314.html"


def test_parse_chengwaye_stock_history_fixture():
    payload = parse_stock_page(FIXTURE.read_text(encoding="utf-8"), "5314")

    assert payload["code"] == "5314"
    assert payload["name"] == "世紀*"
    assert payload["summary"] == {
        "limit_up_count": "11 次",
        "latest_limit_up": "2026/08/24",
        "avg_next_open": "+6.08%",
        "avg_next_close": "+6.39%",
    }
    assert payload["record_count"] == 11
    assert payload["records"][0] == {
        "date": "2026/08/24",
        "close": "28.6",
        "group": "光碟片",
        "next_open": "—",
        "next_avg": "—",
        "next_close": "—",
        "next_trend": "—",
    }
    assert payload["records"][1]["next_trend"] == "續漲停"


def test_collect_codes_deduplicates_and_removes_pause_marker():
    pressplay = {
        "not_found_group": {"matched": [{"code": "5314⏸"}, {"code": "2330"}]},
        "found_group": {"matched": [{"code": "5314"}, {"code": "2454"}]},
    }
    assert collect_codes(pressplay) == ["5314", "2330", "2454"]


def test_live_snapshot_is_valid_json():
    snapshot = ROOT / "data" / "latest" / "stock_history.json"
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["_status"] == "ok"
    assert isinstance(payload.get("codes"), dict)
    assert payload["codes"]
    for code, item in payload["codes"].items():
        assert code.isdigit()
        assert item["record_count"] == len(item.get("records") or [])
