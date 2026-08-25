"""Fetch the official TWSE TAIEX previous close for an opening forecast."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone, timedelta
import json
from pathlib import Path
import sys
from typing import Any

import requests

try:
    from ..trading_calendar import TradingCalendarError, get_current_trading_day
except ImportError:  # Allow direct script execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from trading_calendar import TradingCalendarError, get_current_trading_day


TAIPEI = timezone(timedelta(hours=8))
TWSE_HISTORY_URL = "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST"
DEFAULT_CALENDAR = Path(__file__).resolve().parents[2] / "data" / "trading_calendar" / "twse_holidays.json"


def _now() -> datetime:
    return datetime.now(TAIPEI)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _parse_twse_date(value: Any) -> str | None:
    text = str(value or "").strip().replace("／", "/").replace("-", "/")
    pieces = text.split("/")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        return None
    year, month, day = (int(piece) for piece in pieces)
    if year < 1911:
        year += 1911
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _history_url(query_date: str) -> str:
    return f"{TWSE_HISTORY_URL}?response=json&date={query_date.replace('-', '')}"


def _error(market_date: str, message: str, *, previous_trade_date: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "taiex-reference.v1",
        "market_date": market_date,
        "previous_trade_date": previous_trade_date,
        "status": "error",
        "previous_close": None,
        "source": {
            "name": "TWSE TAIEX historical index",
            "url": _history_url(previous_trade_date or market_date),
            "observed_at": None,
            "fetched_at": _now().isoformat(),
            "official": True,
        },
        "error": message,
    }


def fetch_previous_close(
    *,
    market_date: str,
    calendar_path: str | Path = DEFAULT_CALENDAR,
    timeout: float = 10.0,
    session: Any = requests,
) -> dict[str, Any]:
    """Return the last trusted TWSE close before ``market_date``."""
    try:
        target = date.fromisoformat(market_date)
    except ValueError:
        return _error(market_date, f"market date must be ISO date: {market_date}")

    try:
        previous_date = get_current_trading_day(target - timedelta(days=1), config_path=calendar_path)
    except TradingCalendarError as exc:
        return _error(market_date, f"TWSE trading calendar unavailable: {exc.__class__.__name__}")

    query_date = previous_date.isoformat()
    url = _history_url(query_date)
    try:
        response = session.get(url, headers={"User-Agent": "premarket-intel-tool/1.0"}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return _error(market_date, f"TWSE historical endpoint unavailable: {exc.__class__.__name__}", previous_trade_date=query_date)

    fields = payload.get("fields") if isinstance(payload, dict) else None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(fields, list) or not isinstance(rows, list):
        return _error(market_date, "TWSE historical response missing fields/data", previous_trade_date=query_date)

    date_index = next((idx for idx, field in enumerate(fields) if "日期" in str(field)), 0)
    close_index = next((idx for idx, field in enumerate(fields) if "收盤" in str(field)), None)
    if close_index is None:
        return _error(market_date, "TWSE historical response missing closing-index field", previous_trade_date=query_date)

    row = next(
        (
            candidate for candidate in rows
            if isinstance(candidate, list)
            and len(candidate) > max(date_index, close_index)
            and _parse_twse_date(candidate[date_index]) == query_date
        ),
        None,
    )
    if row is None:
        return _error(market_date, f"TWSE historical response has no row for {query_date}", previous_trade_date=query_date)
    previous_close = _number(row[close_index])
    if previous_close is None:
        return _error(market_date, f"TWSE historical close is not numeric for {query_date}", previous_trade_date=query_date)

    fetched_at = _now().isoformat()
    observed_at = f"{query_date}T13:30:00+08:00"
    return {
        "schema_version": "taiex-reference.v1",
        "market_date": market_date,
        "previous_trade_date": query_date,
        "status": "ok",
        "previous_close": round(previous_close, 2),
        "source": {
            "name": "TWSE TAIEX historical index",
            "url": url,
            "observed_at": observed_at,
            "fetched_at": fetched_at,
            "official": True,
        },
        "error": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch official TWSE TAIEX previous close")
    parser.add_argument("--market-date", required=True, help="Taipei market date, YYYY-MM-DD")
    parser.add_argument("--calendar", default=str(DEFAULT_CALENDAR))
    parser.add_argument("--out", default="data/latest/taiex_reference.json")
    args = parser.parse_args(argv)
    payload = fetch_previous_close(market_date=args.market_date, calendar_path=args.calendar)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
