#!/usr/bin/env python3
"""Fetch Chengwaye market-unreflected announcements without treating fetch errors as zero.

The self-reported earnings and quarterly-report feeds carry ROC-calendar
``date`` / ``time`` fields.  The revenue feed exposes ``first_seen`` as the
source-native detector timestamp used by realtime-rev to partition
market-unreflected rows.  ``is_new`` and ``is_updated`` are retained as a
compatibility fallback only when a legacy revenue row has no ``first_seen``;
they must not replace the cutoff comparison when the timestamp is present.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from trading_calendar import is_twse_trading_day
except ImportError:  # imports from the repository root during pytest
    from scripts.trading_calendar import is_twse_trading_day

TAIPEI = timezone(timedelta(hours=8))
DATA_FILE = Path("data/latest/financials.json")
FETCH_TIMEOUT = (10, 120)
URLS = {
    "att": "https://chengwaye-data.pages.dev/realtime_att.json",
    "fin": "https://chengwaye-data.pages.dev/realtime_fin.json",
    "rev": "https://chengwaye-data.pages.dev/realtime_revenue.json",
}


def is_trading_day(date_obj):
    """Use the trusted TWSE snapshot; never infer a missing year silently."""
    target = date_obj.date() if isinstance(date_obj, datetime) else date_obj
    return is_twse_trading_day(target)


def get_cutoff(now: datetime | None = None) -> datetime:
    now = now or datetime.now(TAIPEI)
    if is_trading_day(now) and (now.hour > 13 or (now.hour == 13 and now.minute >= 30)):
        return now.replace(hour=13, minute=30, second=0, microsecond=0)
    for offset in range(1, 16):
        candidate = now - timedelta(days=offset)
        if is_trading_day(candidate):
            return candidate.replace(hour=13, minute=30, second=0, microsecond=0)
    return now.replace(hour=13, minute=30, second=0, microsecond=0)


def parse_roc_timestamp(item: dict[str, Any]) -> datetime | None:
    date_str = str(item.get("date") or "").strip()
    time_str = str(item.get("time") or "").strip()
    if not date_str or not time_str:
        return None
    try:
        roc_year, month, day = (int(part) for part in date_str.split("/"))
        hh, mm, *rest = (int(part) for part in time_str.split(":"))
        ss = rest[0] if rest else 0
        return datetime(roc_year + 1911, month, day, hh, mm, ss, tzinfo=TAIPEI)
    except (TypeError, ValueError):
        return None


def is_unreflected_timestamp(item: dict[str, Any], cutoff: datetime) -> bool:
    """Return whether a ROC-calendar announcement was made after the cutoff."""
    announced_at = parse_roc_timestamp(item)
    return announced_at is not None and announced_at > cutoff


def announcement_identity(item: dict[str, Any], key: str) -> tuple[str, str] | None:
    """Return the semantic identity used to remove repeated source observations."""
    code = str(item.get("code") or "").strip()
    subject = " ".join(str(item.get("subject") or item.get("title") or "").split()).casefold()
    if not code or not subject:
        return None
    return code, subject


def dedupe_announcements(key: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest row for each code/kind/subject announcement identity."""
    if key not in {"att", "fin"}:
        return entries
    positions: dict[tuple[str, str], int] = {}
    result: list[dict[str, Any]] = []
    for entry in entries:
        identity = announcement_identity(entry, key)
        if identity is None or identity not in positions:
            if identity is not None:
                positions[identity] = len(result)
            result.append(entry)
            continue
        position = positions[identity]
        current_time = parse_roc_timestamp(entry)
        previous_time = parse_roc_timestamp(result[position])
        if current_time is not None and (previous_time is None or current_time > previous_time):
            result[position] = entry
    return result


def is_unreflected_revenue(item: dict[str, Any], cutoff: datetime) -> bool:
    """Match realtime-rev: include rows first detected after the cutoff.

    ``first_seen`` is a naive Taipei-local timestamp in the revenue feed. A
    few legacy rows may not have it, so their explicit new/updated flags are
    used only as a backwards-compatible fallback.
    """
    first_seen = str(item.get("first_seen") or "").strip()
    if first_seen:
        try:
            detected_at = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            if detected_at.tzinfo is None:
                detected_at = detected_at.replace(tzinfo=TAIPEI)
            else:
                detected_at = detected_at.astimezone(TAIPEI)
            return detected_at > cutoff
        except ValueError:
            pass
    return bool(item.get("is_new")) or bool(item.get("is_updated"))


def select_unreflected(key: str, entries: list[dict[str, Any]], cutoff: datetime) -> list[dict[str, Any]]:
    if key == "rev":
        selected = [entry for entry in entries if is_unreflected_revenue(entry, cutoff)]
    else:
        selected = [entry for entry in entries if is_unreflected_timestamp(entry, cutoff)]
    return dedupe_announcements(key, selected)


def load_previous(path: Path = DATA_FILE) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def cached_rows(previous: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = previous.get(key)
    return rows if isinstance(rows, list) else []


def main():
    cutoff = get_cutoff()
    previous = load_previous()
    results: dict[str, Any] = {
        "cutoff_str": cutoff.strftime("%m/%d %H:%M"),
        "att": [],
        "fin": [],
        "rev": [],
        "source_status": {},
    }

    for key, url in URLS.items():
        try:
            response = requests.get(url, timeout=FETCH_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            if not isinstance(entries, list):
                raise ValueError("source entries is not a list")
            rows = select_unreflected(key, entries, cutoff)
            results[key] = rows
            results["source_status"][key] = {
                "state": "fresh",
                "total": len(entries),
                "unreflected": len(rows),
                "fetched_at": payload.get("fetched_at") if isinstance(payload, dict) else None,
            }
            print(f"{key}: {len(entries)} total, {len(rows)} unreflected", file=sys.stderr)
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            fallback = cached_rows(previous, key)
            results[key] = fallback
            results["source_status"][key] = {
                "state": "stale_cached" if fallback else "fetch_failed",
                "total": None,
                "unreflected": len(fallback),
            }
            print(
                f"{key}: fetch failed; retained {len(fallback)} cached unreflected rows ({type(exc).__name__})",
                file=sys.stderr,
            )

    os.makedirs(DATA_FILE.parent, exist_ok=True)
    DATA_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
