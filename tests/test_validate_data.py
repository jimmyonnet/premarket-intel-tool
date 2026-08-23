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
