import json

from scripts.validate_data import EXPECTED_TOP_LEVEL, validate_data_dir


def _write_payloads(root, *, missing=None, invalid=None):
    missing = set(missing or [])
    invalid = set(invalid or [])
    for name, expected_types in EXPECTED_TOP_LEVEL.items():
        if name in missing:
            continue
        path = root / f"{name}.json"
        if name in invalid:
            path.write_text("{not valid json", encoding="utf-8")
            continue
        if name == "source_status":
            payload = {"sources": {}}
        elif name == "financials":
            payload = {"att": [], "fin": [], "rev": []}
        elif list(expected_types) == [list]:
            payload = []
        else:
            payload = {}
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_validate_data_dir_accepts_expected_snapshot_contract(tmp_path):
    _write_payloads(tmp_path)

    report = validate_data_dir(tmp_path)

    assert report["ok"] is True
    assert len(report["files"]) == len(EXPECTED_TOP_LEVEL)
    assert report["errors"] == []
    assert any("empty fallback" in warning for warning in report["warnings"])


def test_validate_data_dir_reports_missing_file(tmp_path):
    _write_payloads(tmp_path, missing={"disposal"})

    report = validate_data_dir(tmp_path)

    assert report["ok"] is False
    assert any("missing file" in error and "disposal.json" in error for error in report["errors"])


def test_validate_data_dir_reports_invalid_json(tmp_path):
    _write_payloads(tmp_path, invalid={"indices"})

    report = validate_data_dir(tmp_path)

    assert report["ok"] is False
    assert any("invalid JSON" in error and "indices.json" in error for error in report["errors"])


def test_validate_data_dir_reports_required_object_key(tmp_path):
    _write_payloads(tmp_path)
    (tmp_path / "source_status.json").write_text("{}", encoding="utf-8")

    report = validate_data_dir(tmp_path)

    assert report["ok"] is False
    assert any("missing key 'sources'" in error for error in report["errors"])


def test_validate_data_dir_normalizes_market_rows_before_static_build(tmp_path):
    _write_payloads(tmp_path)
    (tmp_path / "pressplay.json").write_text(json.dumps({
        "found_group": {"matched": [{
            "code": 2489,
            "name": "瑞軒",
            "close": "not-a-number",
            "volume": "1,200",
            "foreign": "+90",
        }]},
        "not_found_group": {"matched": [{"code": "", "name": "bad row", "close": "12"}]},
    }), encoding="utf-8")
    (tmp_path / "disposal.json").write_text(json.dumps({
        "one_flag_from_disposal": [{"code": "⏸3490", "close": "53.9"}],
        "two_flags_from_disposal": [{"code": None, "close": "12"}],
        "currently_in_disposal": [],
    }), encoding="utf-8")

    report = validate_data_dir(tmp_path, normalize=True)
    pressplay = json.loads((tmp_path / "pressplay.json").read_text(encoding="utf-8"))
    disposal = json.loads((tmp_path / "disposal.json").read_text(encoding="utf-8"))

    row = pressplay["found_group"]["matched"][0]
    assert report["ok"] is True
    assert row["code"] == "2489"
    assert row["close"] == "—"
    assert pressplay["not_found_group"]["matched"] == []
    assert disposal["one_flag_from_disposal"][0]["code"] == "⏸3490"
    assert disposal["two_flags_from_disposal"] == []
    assert any("正規化" in warning for warning in report["warnings"])



def _write_calendar_for(root, holidays=None):
    calendar = root.parent / "trading_calendar" / "twse_holidays.json"
    calendar.parent.mkdir(parents=True, exist_ok=True)
    calendar.write_text(json.dumps({"years": {"2026": {"holidays": holidays or []}}, "manual_overrides": []}), encoding="utf-8")


def test_semantic_date_consistency_is_reported_as_warning(tmp_path):
    root = tmp_path / "data" / "latest"
    root.mkdir(parents=True)
    _write_payloads(root)
    _write_calendar_for(root)
    (root / "night_session.json").write_text(json.dumps({"date": "2026-08-25", "latest": {}}), encoding="utf-8")
    (root / "disposal.json").write_text(json.dumps({"date_check": {"today": "2026-08-24", "effective_market_day": "2026-08-24", "page_says_applies_to": "08/23"}}), encoding="utf-8")

    report = validate_data_dir(root)
    assert report["ok"] is True
    assert any("資料日期不一致" in warning for warning in report["warnings"])


def test_semantic_disposal_previous_trading_day_check_uses_authoritative_calendar(tmp_path):
    root = tmp_path / "data" / "latest"
    root.mkdir(parents=True)
    _write_payloads(root)
    _write_calendar_for(root, holidays=["2026-08-24"])
    (root / "disposal.json").write_text(json.dumps({
        "date_check": {
            "today": "2026-08-25", "effective_market_day": "2026-08-25", "page_says_applies_to": "08/20"
        }
    }), encoding="utf-8")

    report = validate_data_dir(root)
    assert any("disposal page_says_applies_to" in warning for warning in report["warnings"])
    assert report["semantic_checks"]["disposal_previous_trading_day"] == "checked"


def test_semantic_index_change_pct_error_is_not_silently_normalized(tmp_path):
    _write_payloads(tmp_path)
    (tmp_path / "indices.json").write_text(json.dumps({"us_indices": {"sp500": {"change_pct": 55}}}), encoding="utf-8")

    report = validate_data_dir(tmp_path)
    assert report["ok"] is False
    assert any("change_pct" in error and "語意上限" in error for error in report["errors"])


def test_semantic_duplicate_codes_news_and_announcements_are_errors(tmp_path):
    _write_payloads(tmp_path)
    (tmp_path / "pressplay.json").write_text(json.dumps({
        "found_group": {"matched": [{"code": "2330"}, {"code": "2330"}]}
    }), encoding="utf-8")
    (tmp_path / "news.json").write_text(json.dumps([
        {"title": "同一標題", "link": "https://example.test/a"},
        {"title": " 同一標題 ", "link": "https://example.test/a"},
    ]), encoding="utf-8")
    (tmp_path / "financials.json").write_text(json.dumps({
        "att": [{"code": "2330", "subject": "公告相同"}, {"code": "2330", "subject": "公告相同"}],
        "fin": [], "rev": [],
    }), encoding="utf-8")

    report = validate_data_dir(tmp_path)
    assert report["ok"] is False
    assert any("股票代號 2330 重複" in error for error in report["errors"])
    assert any("news normalized title 重複" in error for error in report["errors"])
    assert any("news normalized link 重複" in error for error in report["errors"])
    assert any("financials announcement 重複" in error for error in report["errors"])


def test_explicit_schema_catches_nonempty_field_drift(tmp_path):
    _write_payloads(tmp_path)
    (tmp_path / "disposal.json").write_text(json.dumps({"items": []}), encoding="utf-8")

    report = validate_data_dir(tmp_path)
    assert report["ok"] is False
    assert any("schema violation in disposal" in error and "date_check" in error for error in report["errors"])
