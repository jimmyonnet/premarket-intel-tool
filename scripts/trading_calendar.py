#!/usr/bin/env python3
"""TWSE trading-calendar loader and annual official snapshot updater.

The exchange's annual holiday table is the source of truth.  This module keeps
network access explicit (``update`` command), validates the downloaded payload,
and makes an unknown calendar a hard, visible failure instead of silently
assuming that every weekday is tradable.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_HOLIDAYS_PATH = Path(__file__).parent.parent / "data" / "trading_calendar" / "twse_holidays.json"
OFFICIAL_TWSE_ENDPOINT = "https://www.twse.com.tw/holidaySchedule/holidaySchedule"
CALENDAR_SCHEMA_VERSION = "twse-holiday-calendar.v2"


class TradingCalendarError(RuntimeError):
    """Base error for malformed or unavailable authoritative calendar data."""


class TradingCalendarUnavailable(TradingCalendarError):
    """Raised when a requested year's calendar cannot be trusted."""


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _year_entry(holidays: set[str], observed_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "holidays": sorted(holidays),
        "observed_rows": observed_rows or [],
    }


def _extract_years(payload: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    """Read v2 snapshots and legacy ``holidays_YYYY`` files into one shape."""
    years: dict[int, dict[str, Any]] = {}
    raw_years = payload.get("years")
    if isinstance(raw_years, Mapping):
        for raw_year, raw_entry in raw_years.items():
            try:
                year = int(raw_year)
            except (TypeError, ValueError):
                continue
            if not isinstance(raw_entry, Mapping):
                continue
            holidays = raw_entry.get("holidays", [])
            if not isinstance(holidays, list):
                continue
            years[year] = {
                "holidays": holidays,
                "observed_rows": raw_entry.get("observed_rows", []),
            }

    # Read older repository snapshots so a controlled migration does not make
    # existing tests or a locally pinned snapshot unusable.
    for key, values in payload.items():
        if not key.startswith("holidays_") or not isinstance(values, list):
            continue
        try:
            year = int(key.removeprefix("holidays_"))
        except ValueError:
            continue
        years.setdefault(year, _year_entry(set(str(item) for item in values)))
    return years


def validate_calendar_payload(payload: Any, year: int | None = None) -> dict[int, set[str]]:
    """Validate a normalized or legacy payload and return holidays by year.

    Only ISO dates belonging to their declared year are accepted.  The
    requested year must be present; this is deliberately stricter than a
    generic JSON parser because the result decides whether a build runs.
    """
    if not isinstance(payload, Mapping):
        raise TradingCalendarError("交易日曆必須是 JSON object")
    years = _extract_years(payload)
    if not years:
        raise TradingCalendarError("交易日曆沒有任何年度資料")

    result: dict[int, set[str]] = {}
    for declared_year, entry in years.items():
        raw_holidays = entry.get("holidays") if isinstance(entry, Mapping) else None
        if not isinstance(raw_holidays, list):
            raise TradingCalendarError(f"{declared_year} 年 holidays 必須是陣列")
        normalized: set[str] = set()
        for raw_value in raw_holidays:
            normalized_value = _iso_date(raw_value)
            if not normalized_value:
                raise TradingCalendarError(f"{declared_year} 年含有無效休市日期：{raw_value!r}")
            if int(normalized_value[:4]) != declared_year:
                raise TradingCalendarError(
                    f"{declared_year} 年休市日期跨年度：{normalized_value}"
                )
            normalized.add(normalized_value)
        result[declared_year] = normalized

    if year is not None and year not in result:
        raise TradingCalendarUnavailable(f"缺少 {year} 年 TWSE 官方交易日曆")
    return result


def _load_payload(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise TradingCalendarUnavailable(f"交易日曆檔案不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TradingCalendarUnavailable(f"交易日曆檔案無法解析：{path} ({exc})") from exc
    if not isinstance(payload, Mapping):
        raise TradingCalendarUnavailable(f"交易日曆檔案頂層格式錯誤：{path}")
    return payload


def load_calendar_payload(config_path: Path | str | None = None) -> Mapping[str, Any]:
    """Load the raw calendar snapshot without masking errors."""
    return _load_payload(Path(config_path) if config_path else DEFAULT_HOLIDAYS_PATH)


def load_twse_holidays(config_path: Path | str | None = None) -> set[str]:
    """Return all validated holiday dates in a snapshot.

    This compatibility helper is used by the page builder to expose the
    current snapshot to client-side calendar filters.  Date-specific decisions
    should use :func:`is_twse_trading_day`, which verifies the requested year.
    """
    path = Path(config_path) if config_path else DEFAULT_HOLIDAYS_PATH
    try:
        payload = _load_payload(path)
        years = validate_calendar_payload(payload)
        manual = payload.get("manual_overrides", [])
        if not isinstance(manual, list):
            raise TradingCalendarError("manual_overrides 必須是陣列")
        manual_dates: set[str] = set()
        for raw_value in manual:
            normalized = _iso_date(raw_value)
            if not normalized:
                raise TradingCalendarError(f"手動覆寫含有無效日期：{raw_value!r}")
            manual_dates.add(normalized)
        return set().union(*years.values(), manual_dates)
    except TradingCalendarError as exc:
        print(f"WARNING: 無法載入可信任的 TWSE 交易日曆：{exc}", file=sys.stderr)
        raise


def _holidays_for_year(
    year: int,
    config_path: Path | str | None = None,
) -> set[str]:
    payload = load_calendar_payload(config_path)
    years = validate_calendar_payload(payload, year=year)
    holidays = set(years[year])
    manual = payload.get("manual_overrides", [])
    if not isinstance(manual, list):
        raise TradingCalendarError("manual_overrides 必須是陣列")
    for raw_value in manual:
        normalized = _iso_date(raw_value)
        if normalized and int(normalized[:4]) == year:
            holidays.add(normalized)
    return holidays


def is_twse_trading_day(
    d: date,
    holidays: set[str] | None = None,
    config_path: Path | str | None = None,
) -> bool:
    """Return whether ``d`` is an exchange trading day.

    If ``holidays`` is omitted, the authoritative snapshot for ``d.year`` is
    required.  Missing, malformed, or unavailable data raises
    :class:`TradingCalendarUnavailable` after emitting a warning; it never
    infers a weekday as tradable.
    """
    if d.weekday() >= 5:
        return False
    if holidays is not None:
        active_holidays = holidays
    else:
        try:
            active_holidays = _holidays_for_year(d.year, config_path)
        except TradingCalendarError as exc:
            print(f"WARNING: TWSE 交易日曆不可用，拒絕猜測 {d.isoformat()} 是否交易日：{exc}", file=sys.stderr)
            raise
    return d.isoformat() not in active_holidays


def get_next_trading_day(
    d: date,
    holidays: set[str] | None = None,
    config_path: Path | str | None = None,
) -> date:
    """Calculate the immediately following trusted TWSE trading day."""
    nxt = d + timedelta(days=1)
    while not is_twse_trading_day(nxt, holidays, config_path):
        nxt += timedelta(days=1)
    return nxt


def get_current_trading_day(
    d: date,
    holidays: set[str] | None = None,
    config_path: Path | str | None = None,
) -> date:
    """Calculate the most recent trusted TWSE trading day on or before ``d``."""
    cur = d
    while not is_twse_trading_day(cur, holidays, config_path):
        cur -= timedelta(days=1)
    return cur


def _is_closed_row(name: str, description: str) -> bool:
    text = f"{name} {description}"
    closed_markers = ("無交易", "休市", "放假", "補假", "停止交易")
    open_markers = ("開始交易", "最後交易日")
    if any(marker in text for marker in closed_markers):
        return True
    if any(marker in text for marker in open_markers):
        return False
    raise TradingCalendarError(f"官方資料無法判定市場狀態：{name} / {description}")


def normalize_official_payload(payload: Any, year: int, fetched_at: str | None = None) -> dict[str, Any]:
    """Convert TWSE API JSON into the repository's stable schema."""
    if not isinstance(payload, Mapping) or payload.get("stat") != "ok":
        raise TradingCalendarError("TWSE 官方回應狀態不是 ok")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise TradingCalendarError(f"TWSE 官方回應缺少 {year} 年資料列")

    holidays: set[str] = set()
    observed_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            raise TradingCalendarError(f"TWSE 官方資料列格式錯誤：{row!r}")
        date_value = _iso_date(row[0])
        if not date_value or int(date_value[:4]) != year:
            raise TradingCalendarError(f"TWSE 官方資料列日期錯誤：{row[0]!r}")
        name = str(row[1] or "").strip()
        description = str(row[2] or "").strip()
        closed = _is_closed_row(name, description)
        row_date = date.fromisoformat(date_value)
        observed_rows.append({
            "date": date_value,
            "name": name,
            "description": description,
            "is_trading_day": not closed and row_date.weekday() < 5,
        })
        if closed and row_date.weekday() < 5:
            holidays.add(date_value)

    now = fetched_at or datetime.now(TAIPEI).isoformat()
    return {
        "schema_version": CALENDAR_SCHEMA_VERSION,
        "exchange": "TWSE",
        "source": {
            "name": "TWSE 臺灣證券交易所",
            "url": OFFICIAL_TWSE_ENDPOINT,
            "query": {"yy": str(year)},
        },
        "fetched_at": now,
        "status": "ok",
        "years": {str(year): _year_entry(holidays, observed_rows)},
        "manual_overrides": [],
    }


def fetch_official_calendar(
    year: int,
    endpoint: str = OFFICIAL_TWSE_ENDPOINT,
    timeout: int = 30,
    get_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Fetch and normalize one year from the official TWSE endpoint."""
    getter = get_fn or requests.get
    response = getter(
        endpoint,
        params={"response": "json", "yy": str(year)},
        headers={"User-Agent": "premarket-intel-tool trading-calendar updater"},
        timeout=timeout,
    )
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    try:
        payload = response.json() if hasattr(response, "json") else json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise TradingCalendarError(f"TWSE 官方回應不是有效 JSON：{exc}") from exc
    return normalize_official_payload(payload, year)


def update_calendar(
    year: int,
    output_path: Path | str = DEFAULT_HOLIDAYS_PATH,
    endpoint: str = OFFICIAL_TWSE_ENDPOINT,
    timeout: int = 30,
    get_fn: Callable[..., Any] | None = None,
) -> Path:
    """Fetch one annual table and atomically merge it into the local snapshot."""
    output = Path(output_path)
    fetched = fetch_official_calendar(year, endpoint=endpoint, timeout=timeout, get_fn=get_fn)
    existing: dict[str, Any] = {}
    if output.exists():
        raw = _load_payload(output)
        existing = dict(raw)
    existing_years = _extract_years(existing)
    existing_years[year] = fetched["years"][str(year)]
    manual = existing.get("manual_overrides", [])
    if not isinstance(manual, list):
        manual = []
    normalized = {
        "schema_version": CALENDAR_SCHEMA_VERSION,
        "exchange": "TWSE",
        "source": fetched["source"],
        "fetched_at": fetched["fetched_at"],
        "status": "ok",
        "years": {str(k): existing_years[k] for k in sorted(existing_years)},
        "manual_overrides": manual,
    }
    validate_calendar_payload(normalized, year=year)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="TWSE Trading Day Evaluator")
    parser.add_argument(
        "command",
        choices=["check-today", "is-trading-day", "next-day", "current-day", "update", "validate"],
    )
    parser.add_argument("--date", help="ISO format date (YYYY-MM-DD)", default=None)
    parser.add_argument("--year", type=int, default=None, help="西元年度（update 時必填；預設為台北目前年度）")
    parser.add_argument("--config", help="Path to twse_holidays.json", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    config_path = Path(args.config) if args.config else DEFAULT_HOLIDAYS_PATH

    if args.command == "update":
        year = args.year or datetime.now(TAIPEI).year
        try:
            output = update_calendar(year, output_path=config_path, timeout=args.timeout)
        except (TradingCalendarError, requests.RequestException) as exc:
            print(f"::error::TWSE 交易日曆更新失敗：{exc}", file=sys.stderr)
            raise SystemExit(2)
        print(f"已更新 {year} 年官方 TWSE 交易日曆：{output}")
        return

    if args.command == "validate":
        try:
            payload = load_calendar_payload(config_path)
            years = validate_calendar_payload(payload, year=args.year)
        except TradingCalendarError as exc:
            print(f"::error::TWSE 交易日曆驗證失敗：{exc}", file=sys.stderr)
            raise SystemExit(2)
        print(f"交易日曆有效：{', '.join(str(year) for year in sorted(years))}")
        return

    target_dt = date.fromisoformat(args.date) if args.date else datetime.now(TAIPEI).date()
    try:
        if args.command in ("check-today", "is-trading-day"):
            trading = is_twse_trading_day(target_dt, config_path=config_path)
            print(f"Date: {target_dt.isoformat()}, IsTradingDay: {trading}")
            raise SystemExit(0 if trading else 1)
        if args.command == "next-day":
            print(get_next_trading_day(target_dt, config_path=config_path).isoformat())
        elif args.command == "current-day":
            print(get_current_trading_day(target_dt, config_path=config_path).isoformat())
    except TradingCalendarError as exc:
        print(f"WARNING: TWSE 交易日曆不可用，拒絕猜測交易日：{exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
