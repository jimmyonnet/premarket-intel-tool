from pathlib import Path

import scripts.opening_prediction.verify_opening as verifier
from scripts.opening_prediction.verify_opening import fetch_official_open, reconcile


FORECAST = {
    "schema_version": "opening-forecast.v1",
    "prediction_id": "2026-08-25T08:30+08:00-opening-v1",
    "market_date": "2026-08-25",
    "status": "generated",
    "previous_close": 45000,
    "predicted_change_points": 146.4,
    "direction": "up",
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def _fetched_open(value=45150):
    return {
        "status": "verified",
        "actual_open": value,
        "source": {
            "name": "TWSE MIS TAIEX",
            "url": verifier.TWSE_OPEN_ENDPOINT,
            "observed_at": "2026-08-25T09:00:00+08:00",
            "fetched_at": "2026-08-25T09:05:00+08:00",
            "official": True,
        },
    }


def test_fetch_official_open_uses_taiex_o_field_and_rejects_wrong_date():
    session = FakeSession({"msgArray": [{"c": "t00", "d": "20260825", "o": "45,150.00", "z": "45,200"}]})
    payload = fetch_official_open(market_date="2026-08-25", session=session)
    assert payload["status"] == "verified"
    assert payload["actual_open"] == 45150.0
    assert payload["source"]["official"] is True
    assert session.calls[0][0] == verifier.TWSE_OPEN_ENDPOINT

    wrong_date = FakeSession({"msgArray": [{"c": "t00", "d": "20260824", "o": "45,150.00"}]})
    rejected = fetch_official_open(market_date="2026-08-25", session=wrong_date)
    assert rejected["status"] == "not_available"
    assert "20260824" in rejected["message"]


def test_reconcile_pending_then_verified_and_computes_metrics():
    pending = reconcile(
        forecast=FORECAST,
        attempted_at="2026-08-25T09:05:00+08:00",
        fetched={"status": "not_available", "message": "opening not published"},
    )
    assert pending["status"] == "pending"
    assert pending["attempts"] == 1
    verified = reconcile(
        forecast=FORECAST,
        previous=pending,
        attempted_at="2026-08-25T09:10:00+08:00",
        fetched=_fetched_open(),
    )
    assert verified["status"] == "verified"
    assert verified["attempts"] == 2
    assert verified["actual_change_points"] == 150.0
    assert verified["actual_direction"] == "up"
    assert verified["direction_correct"] is True
    assert verified["absolute_error_points"] == 3.6


def test_final_unavailable_is_unverified_and_not_learning_eligible():
    pending = reconcile(
        forecast=FORECAST,
        attempted_at="2026-08-25T09:05:00+08:00",
        fetched={"status": "not_available", "message": "not ready"},
    )
    final = reconcile(
        forecast=FORECAST,
        previous=pending,
        attempted_at="2026-08-25T09:15:00+08:00",
        final=True,
        fetched={"status": "error", "message": "endpoint timeout"},
    )
    assert final["status"] == "unverified"
    assert final["attempts"] == 2
    assert final["direction_correct"] is None
    assert final["absolute_error_points"] is None


def test_verified_result_is_immutable_on_later_retry():
    verified = reconcile(
        forecast=FORECAST,
        attempted_at="2026-08-25T09:05:00+08:00",
        fetched=_fetched_open(45150),
    )
    later = reconcile(
        forecast=FORECAST,
        previous=verified,
        attempted_at="2026-08-25T09:15:00+08:00",
        final=True,
        fetched={"status": "error", "message": "late failure"},
    )
    assert later == verified


def test_empty_fetched_injection_does_not_call_network(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("network must not be called for injected empty result")

    monkeypatch.setattr(verifier, "fetch_official_open", fail)
    result = reconcile(
        forecast=FORECAST,
        attempted_at="2026-08-25T09:05:00+08:00",
        fetched={},
    )
    assert result["status"] == "pending"


def test_market_closed_is_not_applicable():
    closed = {**FORECAST, "status": "market_closed", "prediction_id": "closed"}
    result = reconcile(forecast=closed)
    assert result["status"] == "not_applicable"
    assert result["actual_open"] is None


def test_initialize_creates_pending_without_network_for_generated_forecast(tmp_path, monkeypatch):
    forecast_path = tmp_path / "forecast.json"
    result_path = tmp_path / "result.json"
    forecast_path.write_text(__import__("json").dumps(FORECAST), encoding="utf-8")

    def fail(**kwargs):
        raise AssertionError("initialize must not fetch MIS")

    monkeypatch.setattr(verifier, "fetch_official_open", fail)
    assert verifier.main(["--forecast", str(forecast_path), "--out", str(result_path), "--initialize"]) == 0
    payload = __import__("json").loads(result_path.read_text())
    assert payload["status"] == "pending"
    assert payload["attempts"] == 0
    assert payload["attempt_log"] == []


def test_initialize_creates_not_applicable_for_not_generated_forecast(tmp_path):
    import json

    forecast_path = tmp_path / "forecast.json"
    result_path = tmp_path / "result.json"
    forecast = {"status": "not_generated", "prediction_id": None, "market_date": "2026-08-25"}
    forecast_path.write_text(json.dumps(forecast), encoding="utf-8")
    assert verifier.main(["--forecast", str(forecast_path), "--out", str(result_path), "--initialize"]) == 0
    assert json.loads(result_path.read_text())["status"] == "not_applicable"
