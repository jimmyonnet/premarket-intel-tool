#!/usr/bin/env python3
"""
Part 4 data source: a user-maintained financial/economic events calendar,
published as a public Google Calendar ICS feed.

  https://calendar.google.com/calendar/ical/.../public/basic.ics

Fetches the ICS feed and expands it (including recurring events, via
recurring_ical_events -- plain icalendar does not expand RRULEs) to a
flat list of event occurrences whose local (Asia/Taipei) date falls
within [today, today + --days-ahead], sorted by date then time.

Like Part 3's PressPlay/chengwaye_daily fetches, this is allowed to fail
without blocking the rest of the page build -- the GitHub Actions step
falls back to an empty JSON on error, and build_page.py/the template
both render a clean "no events" Part 4 rather than crashing the whole
page over an unreachable or malformed calendar feed.

Usage:
    python fetch_calendar.py [--ics-url URL] [--fixture PATH] [--today YYYY-MM-DD] [--days-ahead N]
"""
import argparse
import datetime
import json
from pathlib import Path

import requests
import icalendar
import recurring_ical_events

DEFAULT_ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_c040a8d14375de55799b6fdd8ece2ee2f32aa85fd0e5b39d14b1e07f90df424e"
    "%40group.calendar.google.com/public/basic.ics"
)
TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
DEFAULT_DAYS_AHEAD = 14
HEADERS = {"User-Agent": "premarket-intel-tool (+github actions calendar sync)"}


def fetch_ics_bytes(url: str, fixture: Path = None) -> bytes:
    if fixture is not None:
        return fixture.read_bytes()
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.content


def extract_events(ics_bytes: bytes, start_date, end_date):
    """All event occurrences (recurring events expanded) whose local date
    falls in [start_date, end_date] inclusive, sorted by date then time
    (all-day events sort before timed events on the same date, since a
    missing time string sorts before any "HH:MM")."""
    cal = icalendar.Calendar.from_ical(ics_bytes)
    occurrences = recurring_ical_events.of(cal).between(start_date, end_date)

    events = []
    for comp in occurrences:
        dt = comp.get("dtstart").dt
        all_day = not isinstance(dt, datetime.datetime)
        if all_day:
            ev_date, time_str = dt, None
        else:
            if dt.tzinfo is not None:
                dt = dt.astimezone(TAIPEI)
            ev_date, time_str = dt.date(), dt.strftime("%H:%M")

        if ev_date < start_date or ev_date > end_date:
            continue  # timezone conversion can shift a UTC date across the boundary

        summary = str(comp.get("summary", "") or "").strip()
        if not summary:
            continue
        description = str(comp.get("description", "") or "").strip()
        events.append({
            "date": ev_date.isoformat(),
            "time": time_str,
            "all_day": all_day,
            "summary": summary,
            "description": description[:200] or None,
        })

    events.sort(key=lambda e: (e["date"], e["time"] or ""))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ics-url", default=DEFAULT_ICS_URL)
    ap.add_argument("--fixture", type=Path, default=None, help="offline test .ics file")
    ap.add_argument(
        "--today", type=str, default=None,
        help="override 'today' (YYYY-MM-DD); defaults to real today (Asia/Taipei date)",
    )
    ap.add_argument("--days-ahead", type=int, default=DEFAULT_DAYS_AHEAD)
    args = ap.parse_args()

    today = (
        datetime.date.fromisoformat(args.today) if args.today
        else datetime.datetime.now(TAIPEI).date()
    )
    end_date = today + datetime.timedelta(days=args.days_ahead)

    ics_bytes = fetch_ics_bytes(args.ics_url, args.fixture)
    events = extract_events(ics_bytes, today, end_date)

    result = {
        "source": args.ics_url,
        "today": today.isoformat(),
        "range_end": end_date.isoformat(),
        "events": events,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
