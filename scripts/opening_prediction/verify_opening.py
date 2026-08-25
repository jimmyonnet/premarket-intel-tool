"""Verify the first official TAIEX opening value after 09:00.

The TWSE MIS endpoint exposes the day's opening index in ``o``.  Each scheduled
run is idempotent: an already verified result is returned without another
write, while unavailable attempts are appended and can be retried later.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
from typing import Any

import requests

try:
    from .model import direction_for_change, gap_label, load_json, parse_float
except ImportError:  # Allow direct script execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from model import direction_for_change, gap_label, load_json, parse_float


TAIPEI = timezone(timedelta(hours=8))
TWSE_OPEN_ENDPOINT = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0"
TARGET_TIME = "09:00:00+08:00"


def _now() -> datetime:
    return datetime.now(TAIPEI)


def _number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return parse_float(value)


def fetch_official_open(
    *,
    market_date: str,
    timeout: float = 10.0,
    session: Any = requests,
) -> dict[str, Any]:
    """Return the official TAIEX opening index, or a safe unavailability result."""
    try:
        response = session.get(
            TWSE_OPEN_ENDPOINT,
            headers={"User-Agent": "premarket-intel-tool/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"status": "error", "message": f"TWSE official endpoint unavailable: {exc.__class__.__name__}"}

    rows = payload.get("msgArray") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"status": "error", "message": "TWSE response missing msgArray"}
    row = next((item for item in rows if isinstance(item, dict) and item.get("c") == "t00"), None)
    if not row:
        return {"status": "not_available", "message": "TAIEX row is not available"}
    returned_date = str(row.get("d") or "")
    if returned_date != market_date.replace("-", ""):
        return {"status": "not_available", "message": f"TWSE returned date {returned_date or 'unknown'}"}
    opening = _number(row.get("o"))
    if opening is None:
        return {"status": "not_available", "message": "TWSE TAIEX opening field is not available"}
    return {
        "status": "verified",
        "actual_open": opening,
        "observed_at": f"{market_date}T09:00:00+08:00",
        "source": {
            "name": "TWSE MIS TAIEX",
            "url": TWSE_OPEN_ENDPOINT,
            "observed_at": f"{market_date}T09:00:00+08:00",
            "fetched_at": _now().isoformat(),
            "official": True,
        },
    }


def _attempt(previous: dict[str, Any], *, attempted_at: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = list(previous.get("attempt_log") or [])
    attempts.append({
        "attempted_at": attempted_at,
        "status": result.get("status"),
        "observed_open": result.get("actual_open"),
        "message": result.get("message"),
    })
    return attempts


def _base_result(forecast: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "opening-result.v1",
        "prediction_id": forecast.get("prediction_id"),
        "market_date": forecast.get("market_date"),
        "status": "pending",
        "target_time": TARGET_TIME,
        "verified_at": None,
        "attempts": int(previous.get("attempts") or 0),
        "attempt_log": list(previous.get("attempt_log") or []),
        "actual_open": None,
        "actual_change_points": None,
        "actual_direction": "unknown",
        "direction_correct": None,
        "signed_error_points": None,
        "absolute_error_points": None,
        "source": {
            "name": "TWSE MIS TAIEX",
            "url": TWSE_OPEN_ENDPOINT,
            "observed_at": None,
            "fetched_at": None,
            "official": True,
        },
        "error": None,
    }


def reconcile(
    *,
    forecast: dict[str, Any],
    previous: dict[str, Any] | None = None,
    attempted_at: str | None = None,
    final: bool = False,
    fetched: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    if previous.get("status") == "verified":
        return previous
    if forecast.get("status") == "market_closed":
        return {
            **_base_result(forecast, previous),
            "status": "not_applicable",
            "error": "market closed",
        }
    result = _base_result(forecast, previous)
    attempted_at = attempted_at or _now().isoformat()
    if fetched is None:
        fetched = fetch_official_open(market_date=str(forecast.get("market_date")))
    result["attempt_log"] = _attempt(previous, attempted_at=attempted_at, result=fetched)
    result["attempts"] = len(result["attempt_log"])

    if fetched.get("status") != "verified":
        result["status"] = "unverified" if final else "pending"
        result["error"] = fetched.get("message") or "opening value not available"
        return result

    actual_open = _number(fetched.get("actual_open"))
    previous_close = _number(forecast.get("previous_close"))
    predicted_change = _number(forecast.get("predicted_change_points"))
    if actual_open is None or previous_close is None or predicted_change is None:
        result["status"] = "unverified" if final else "pending"
        result["error"] = "forecast or opening value is missing required numeric fields"
        return result

    actual_change = round(actual_open - previous_close, 2)
    actual_direction = direction_for_change(actual_change)
    result.update({
        "status": "verified",
        "verified_at": fetched.get("source", {}).get("fetched_at") or _now().isoformat(),
        "actual_open": round(actual_open, 2),
        "actual_change_points": actual_change,
        "actual_direction": actual_direction,
        "direction_correct": forecast.get("direction") == actual_direction,
        "signed_error_points": round(predicted_change - actual_change, 2),
        "absolute_error_points": round(abs(predicted_change - actual_change), 2),
        "source": fetched.get("source") or result["source"],
        "error": None,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify official TAIEX opening value")
    parser.add_argument("--forecast", default="data/latest/opening_forecast.json")
    parser.add_argument("--out", default="data/latest/opening_result.json")
    parser.add_argument("--attempted-at", default=None)
    parser.add_argument("--initialize", action="store_true", help="Create pending state without fetching the official opening")
    parser.add_argument("--final", action="store_true", help="Mark unavailable result as final unverified")
    args = parser.parse_args(argv)

    forecast = load_json(args.forecast, {}) or {}
    if not isinstance(forecast, dict) or (not forecast.get("prediction_id") and not (args.initialize and forecast.get("status") == "not_generated")):
        print("ERROR: opening forecast is missing", file=sys.stderr)
        return 1
    output = Path(args.out)
    previous = load_json(output, {}) or {}
    if args.initialize:
        result = previous if previous.get("status") == "verified" else _base_result(forecast, previous)
        if forecast.get("status") == "market_closed":
            result["status"] = "not_applicable"
            result["error"] = "market closed"
        elif forecast.get("status") == "not_generated":
            result["status"] = "not_applicable"
            result["error"] = "forecast was not generated within the 08:30 lock window"
    else:
        result = reconcile(forecast=forecast, previous=previous, attempted_at=args.attempted_at, final=args.final)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
