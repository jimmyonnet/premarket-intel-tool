"""Generate and lock a deterministic Taiwan opening forecast."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone, timedelta
import json
from pathlib import Path
import sys
from typing import Any

try:
    from .model import build_forecast, load_json, load_model_config
except ImportError:  # Allow `python scripts/opening_prediction/generate_forecast.py`.
    from model import build_forecast, load_json, load_model_config

try:
    from trading_calendar import TradingCalendarError, is_twse_trading_day
except ImportError:  # Direct script execution starts sys.path in this subdirectory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from trading_calendar import TradingCalendarError, is_twse_trading_day


TAIPEI = timezone(timedelta(hours=8))
DEFAULT_CALENDAR = Path(__file__).resolve().parents[2] / "data" / "trading_calendar" / "twse_holidays.json"


def _now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def _not_generated(market_date: str, model_version: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "opening-forecast.v1",
        "prediction_id": None,
        "market_date": market_date,
        "status": "not_generated",
        "locked_at": None,
        "model_version": model_version,
        "previous_close": None,
        "predicted_change_points": None,
        "predicted_open": None,
        "direction": "unknown",
        "gap_label": "unknown",
        "confidence": "unknown",
        "confidence_reasons": [reason],
        "evidence": [],
        "data_quality": {"missing_factors": [], "conflicts": [], "conflict_directions": [], "cache_used": False},
        "formula": {"threshold_points": 100.0, "available_weight": 0.0, "features": []},
    }


def _closed_forecast(market_date: str, model_version: str) -> dict[str, Any]:
    return {
        "schema_version": "opening-forecast.v1",
        "prediction_id": f"{market_date}-market-closed-{model_version}",
        "market_date": market_date,
        "status": "market_closed",
        "locked_at": None,
        "model_version": model_version,
        "previous_close": None,
        "predicted_change_points": None,
        "predicted_open": None,
        "direction": "unknown",
        "gap_label": "unknown",
        "confidence": "unknown",
        "confidence_reasons": ["今日台股休市，沒有正式開盤判斷"],
        "evidence": [],
        "data_quality": {"missing_factors": [], "conflicts": [], "conflict_directions": [], "cache_used": False},
        "formula": {"threshold_points": 100.0, "available_weight": 0.0, "features": []},
    }


def generate(
    *,
    market_date: str,
    locked_at: str,
    indices_path: str | Path,
    night_path: str | Path,
    twse_path: str | Path,
    taiex_reference_path: str | Path | None = None,
    calendar_path: str | Path = DEFAULT_CALENDAR,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    try:
        target = date.fromisoformat(market_date)
    except ValueError as exc:
        raise ValueError(f"market date must be ISO date: {market_date}") from exc

    config = load_model_config(config_path)
    model_version = str(config.get("model_version") or "opening-v1")
    try:
        trading_day = is_twse_trading_day(target, config_path=calendar_path)
    except TradingCalendarError as exc:
        raise RuntimeError(f"TWSE trading calendar unavailable for {market_date}: {exc}") from exc
    if not trading_day:
        return _closed_forecast(market_date, model_version)

    try:
        lock_dt = datetime.fromisoformat(locked_at)
    except ValueError as exc:
        raise ValueError(f"locked-at must be ISO date-time: {locked_at}") from exc
    if lock_dt.tzinfo is None:
        lock_dt = lock_dt.replace(tzinfo=TAIPEI)
    lock_dt = lock_dt.astimezone(TAIPEI)
    if lock_dt.date() != target:
        raise ValueError(f"locked-at date {lock_dt.date().isoformat()} does not match market date {market_date}")
    # GitHub scheduled jobs can start a few minutes late.  Never silently use
    # a later intraday snapshot as an 08:30 forecast; beyond this grace window
    # publish an explicit safe fallback instead.
    lock_minutes = lock_dt.hour * 60 + lock_dt.minute
    if lock_minutes > 8 * 60 + 40:
        return _not_generated(market_date, model_version, "08:30 預測鎖定窗口已錯過，拒絕使用盤中資料回填")
    if lock_minutes < 8 * 60 + 25:
        return _not_generated(market_date, model_version, "尚未到達 08:30 預測鎖定窗口，拒絕使用過早資料回填")

    indices = load_json(indices_path, {}) or {}
    night = load_json(night_path, {}) or {}
    twse = load_json(twse_path, {}) or {}
    taiex_reference = load_json(taiex_reference_path, {}) or {} if taiex_reference_path else {}
    if not isinstance(indices, dict) or not isinstance(night, dict) or not isinstance(twse, dict) or not isinstance(taiex_reference, dict):
        raise ValueError("indices, night-session, twse-summary, and taiex-reference must be JSON objects")
    return build_forecast(
        market_date=market_date,
        locked_at=locked_at,
        indices=indices,
        night=night,
        twse=twse,
        taiex_reference=taiex_reference,
        config=config,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a locked Taiwan opening forecast")
    parser.add_argument("--market-date", default=None, help="Taipei market date, YYYY-MM-DD")
    parser.add_argument("--locked-at", default=None, help="Explicit lock timestamp, ISO date-time")
    parser.add_argument("--indices", default="data/latest/indices.json")
    parser.add_argument("--night-session", default="data/latest/night_session.json")
    parser.add_argument("--twse-summary", default="data/latest/twse_summary.json")
    parser.add_argument("--taiex-reference", default="data/latest/taiex_reference.json")
    parser.add_argument("--calendar", default=str(DEFAULT_CALENDAR))
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[2] / "config" / "opening_model_v1.json"))
    parser.add_argument("--out", default="data/latest/opening_forecast.json")
    args = parser.parse_args(argv)

    now = _now_taipei()
    market_date = args.market_date or now.date().isoformat()
    locked_at = args.locked_at or now.isoformat()
    try:
        payload = generate(
            market_date=market_date,
            locked_at=locked_at,
            indices_path=args.indices,
            night_path=args.night_session,
            twse_path=args.twse_summary,
            taiex_reference_path=args.taiex_reference,
            calendar_path=args.calendar,
            config_path=args.config,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: opening forecast not generated: {exc}", file=sys.stderr)
        return 1

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
