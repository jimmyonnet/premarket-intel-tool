#!/usr/bin/env python3
"""
TWSE Trading Calendar helper module.
Determines if a given date is a Taiwan Stock Exchange trading day,
taking weekends, statutory holidays, and manual overrides into account.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_HOLIDAYS_PATH = Path(__file__).parent.parent / "data" / "trading_calendar" / "twse_holidays.json"


def load_twse_holidays(config_path: Path | str | None = None) -> set[str]:
    """
    Loads TWSE statutory holidays and manual closure overrides from JSON.
    Returns a set of ISO formatted date strings (YYYY-MM-DD).
    """
    path = Path(config_path) if config_path else DEFAULT_HOLIDAYS_PATH
    if not path.exists():
        # Fallback default statutory holidays if file is missing
        return {
            "2026-01-01", "2026-02-13", "2026-02-16", "2026-02-17", "2026-02-18",
            "2026-02-19", "2026-02-20", "2026-02-27", "2026-04-03", "2026-04-06",
            "2026-05-01", "2026-06-19", "2026-09-25", "2026-10-09", "2026-10-26"
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        holidays: set[str] = set()
        for key, val in data.items():
            if (key.startswith("holidays_") or key == "manual_overrides") and isinstance(val, list):
                holidays.update(val)
        return holidays
    except Exception as exc:
        print(f"Warning: Failed to load {path}: {exc}, using fallback", file=sys.stderr)
        return set()


def is_twse_trading_day(d: date, holidays: set[str] | None = None) -> bool:
    """
    Checks if a given date is a TWSE trading day (Mon-Fri and not a holiday).
    """
    if d.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False
    active_holidays = holidays if holidays is not None else load_twse_holidays()
    return d.isoformat() not in active_holidays


def get_next_trading_day(d: date, holidays: set[str] | None = None) -> date:
    """
    Calculates the immediately following TWSE trading day strictly after d.
    """
    active_holidays = holidays if holidays is not None else load_twse_holidays()
    nxt = d + timedelta(days=1)
    while not is_twse_trading_day(nxt, active_holidays):
        nxt += timedelta(days=1)
    return nxt


def get_current_trading_day(d: date, holidays: set[str] | None = None) -> date:
    """
    Calculates the active or most recent TWSE trading day on or before d.
    """
    active_holidays = holidays if holidays is not None else load_twse_holidays()
    cur = d
    while not is_twse_trading_day(cur, active_holidays):
        cur -= timedelta(days=1)
    return cur


def main() -> None:
    parser = argparse.ArgumentParser(description="TWSE Trading Day Evaluator")
    parser.add_argument("command", choices=["check-today", "is-trading-day", "next-day", "current-day"])
    parser.add_argument("--date", help="ISO format date (YYYY-MM-DD)", default=None)
    parser.add_argument("--config", help="Path to twse_holidays.json", default=None)
    args = parser.parse_args()

    holidays = load_twse_holidays(args.config)
    target_dt: date
    if args.date:
        target_dt = date.fromisoformat(args.date)
    else:
        target_dt = datetime.now(TAIPEI).date()

    if args.command in ("check-today", "is-trading-day"):
        trading = is_twse_trading_day(target_dt, holidays)
        print(f"Date: {target_dt.isoformat()}, IsTradingDay: {trading}")
        sys.exit(0 if trading else 1)
    elif args.command == "next-day":
        nxt = get_next_trading_day(target_dt, holidays)
        print(nxt.isoformat())
    elif args.command == "current-day":
        cur = get_current_trading_day(target_dt, holidays)
        print(cur.isoformat())


if __name__ == "__main__":
    main()
