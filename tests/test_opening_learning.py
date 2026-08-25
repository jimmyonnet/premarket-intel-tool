import json
from pathlib import Path

import pytest

from scripts.learning.build_status import build_status
from scripts.learning.evaluate_opening import evaluate, verified_records
from scripts.learning.record_opening import record_day


def _record(index: int, *, status: str = "verified"):
    date = f"2026-08-{index:02d}"
    return {
        "market_date": date,
        "prediction_id": f"{date}T08:30+08:00-opening-v1",
        "status": status,
        "direction_correct": True if status == "verified" else None,
        "absolute_error_points": 10.0 if status == "verified" else None,
        "confidence": "high",
        "model_version": "opening-v1",
    }


def test_verified_records_excludes_pending_and_unverified():
    records = [_record(1), _record(2, status="pending"), _record(3, status="unverified"), _record(4)]
    assert [row["market_date"] for row in verified_records(records)] == ["2026-08-01", "2026-08-04"]


def test_learning_hides_overall_stats_until_day_twenty():
    warmup = evaluate([_record(index) for index in range(1, 20)], model_version="opening-v1")
    assert warmup["status"] == "warmup"
    assert warmup["verified_days"] == 19
    assert warmup["stats"] is None

    ready = evaluate([_record(index) for index in range(1, 21)], model_version="opening-v1")
    assert ready["status"] == "ready"
    assert ready["verified_days"] == 20
    assert ready["stats"]["direction_accuracy"] == 1.0
    assert ready["stats"]["mean_absolute_error_points"] == 10.0


def test_record_day_is_idempotent_and_verified_result_stays_immutable(tmp_path: Path):
    forecast = {
        "market_date": "2026-08-25",
        "prediction_id": "2026-08-25T08:30+08:00-opening-v1",
        "confidence": "low",
        "model_version": "opening-v1",
    }
    pending = {"prediction_id": forecast["prediction_id"], "market_date": forecast["market_date"], "status": "pending"}
    path = record_day(forecast=forecast, result=pending, directory=tmp_path)
    assert json.loads(path.read_text())["result"]["status"] == "pending"

    verified = {
        **pending,
        "status": "verified",
        "actual_open": 45150,
        "direction_correct": True,
        "absolute_error_points": 3.6,
    }
    record_day(forecast=forecast, result=verified, directory=tmp_path)
    frozen = json.loads(path.read_text())
    assert frozen["result"]["status"] == "verified"
    assert frozen["result"]["actual_open"] == 45150

    later_failure = {**pending, "status": "unverified", "error": "late"}
    record_day(forecast=forecast, result=later_failure, directory=tmp_path)
    still_frozen = json.loads(path.read_text())
    assert still_frozen["result"]["status"] == "verified"
    assert still_frozen["result"]["actual_open"] == 45150


def test_record_day_rejects_prediction_mismatch(tmp_path: Path):
    forecast = {"market_date": "2026-08-25", "prediction_id": "2026-08-25T08:30+08:00-opening-v1"}
    result = {"market_date": "2026-08-25", "prediction_id": "another-prediction", "status": "pending"}
    with pytest.raises(ValueError, match="prediction_id mismatch"):
        record_day(forecast=forecast, result=result, directory=tmp_path)


def test_build_status_reads_only_verified_ledger_entries(tmp_path: Path):
    for index in range(1, 21):
        date = f"2026-08-{index:02d}"
        forecast = {"market_date": date, "prediction_id": f"{date}T08:30+08:00-opening-v1", "confidence": "medium", "model_version": "opening-v1"}
        result = {"market_date": date, "prediction_id": forecast["prediction_id"], "status": "verified", "direction_correct": index % 2 == 0, "absolute_error_points": float(index)}
        record_day(forecast=forecast, result=result, directory=tmp_path)
    unverified_forecast = {"market_date": "2026-08-21", "prediction_id": "2026-08-21T08:30+08:00-opening-v1", "confidence": "low", "model_version": "opening-v1"}
    record_day(forecast=unverified_forecast, result={"market_date": "2026-08-21", "prediction_id": unverified_forecast["prediction_id"], "status": "unverified"}, directory=tmp_path)
    status = build_status(directory=tmp_path, model_version="opening-v1")
    assert status["status"] == "ready"
    assert status["verified_days"] == 20
