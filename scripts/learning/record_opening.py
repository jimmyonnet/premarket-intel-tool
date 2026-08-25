"""Persist one idempotent opening forecast/result record per market day."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def record_path(directory: str | Path, market_date: str) -> Path:
    return Path(directory) / f"{market_date}.json"


def record_day(
    *,
    forecast: dict[str, Any],
    result: dict[str, Any],
    directory: str | Path = "data/opening_history",
    feedback: dict[str, Any] | None = None,
) -> Path:
    market_date = str(forecast.get("market_date") or result.get("market_date") or "").strip()
    prediction_id = forecast.get("prediction_id")
    if not market_date or not prediction_id:
        raise ValueError("forecast must contain market_date and prediction_id")
    if result.get("prediction_id") not in (None, prediction_id):
        raise ValueError("forecast/result prediction_id mismatch")

    output = record_path(directory, market_date)
    existing = load(output)
    existing_forecast = existing.get("forecast") if isinstance(existing.get("forecast"), dict) else {}
    existing_result = existing.get("result") if isinstance(existing.get("result"), dict) else {}
    # A verified record is immutable. Retries may enrich a pending/unverified
    # record, but must never replace the successful result later.
    if existing_result.get("status") == "verified" and result.get("status") != "verified":
        result = existing_result
    elif existing_result.get("status") == "verified" and result.get("status") == "verified":
        result = existing_result
    elif existing_forecast and existing_forecast.get("prediction_id") != prediction_id:
        raise ValueError(f"market date already belongs to another prediction: {market_date}")

    payload = {
        "schema_version": "opening-ledger.v1",
        "market_date": market_date,
        "prediction_id": prediction_id,
        "forecast": forecast,
        "result": result,
        "feedback": feedback if isinstance(feedback, dict) else existing.get("feedback"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one opening forecast/result ledger entry")
    parser.add_argument("--forecast", default="data/latest/opening_forecast.json")
    parser.add_argument("--result", default="data/latest/opening_result.json")
    parser.add_argument("--directory", default="data/opening_history")
    args = parser.parse_args(argv)
    forecast = load(args.forecast)
    result = load(args.result)
    try:
        output = record_day(forecast=forecast, result=result, directory=args.directory)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot record opening ledger: {exc}")
        return 1
    print(f"recorded {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
