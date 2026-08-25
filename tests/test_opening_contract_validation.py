from pathlib import Path
import json

from scripts.validate_data import validate_opening_artifacts


def _write(root: Path, name: str, payload: dict):
    (root / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _valid_payloads():
    forecast = {
        "schema_version": "opening-forecast.v1",
        "prediction_id": "2026-08-25T08:30+08:00-opening-v1",
        "market_date": "2026-08-25",
        "status": "generated",
        "direction": "up",
        "confidence": "low",
        "evidence": [],
    }
    result = {
        "schema_version": "opening-result.v1",
        "prediction_id": forecast["prediction_id"],
        "market_date": forecast["market_date"],
        "status": "pending",
        "actual_direction": "unknown",
        "direction_correct": None,
        "absolute_error_points": None,
    }
    learning = {
        "schema_version": "learning-status.v1",
        "status": "warmup",
        "verified_days": 0,
        "required_days": 20,
        "stats": None,
    }
    return forecast, result, learning


def test_opening_artifacts_are_optional_when_absent(tmp_path: Path):
    files, payloads, errors, warnings = {}, {}, [], []
    validate_opening_artifacts(tmp_path, payloads, files, errors, warnings)
    assert errors == []
    assert files == {}


def test_present_opening_artifacts_pass_contract(tmp_path: Path):
    forecast, result, learning = _valid_payloads()
    _write(tmp_path, "opening_forecast", forecast)
    _write(tmp_path, "opening_result", result)
    _write(tmp_path, "learning_status", learning)
    files, payloads, errors, warnings = {}, {}, [], []
    validate_opening_artifacts(tmp_path, payloads, files, errors, warnings)
    assert errors == []
    assert set(files) == {"opening_forecast", "opening_result", "learning_status"}


def test_mismatched_result_and_unverified_metrics_fail_contract(tmp_path: Path):
    forecast, result, learning = _valid_payloads()
    result["market_date"] = "2026-08-26"
    result["status"] = "unverified"
    result["direction_correct"] = False
    result["absolute_error_points"] = 3.0
    _write(tmp_path, "opening_forecast", forecast)
    _write(tmp_path, "opening_result", result)
    _write(tmp_path, "learning_status", learning)
    files, payloads, errors, warnings = {}, {}, [], []
    validate_opening_artifacts(tmp_path, payloads, files, errors, warnings)
    assert any("non-verified" in error for error in errors)
    assert any("market_date mismatch" in error for error in errors)
