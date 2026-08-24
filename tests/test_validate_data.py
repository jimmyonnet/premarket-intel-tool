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
