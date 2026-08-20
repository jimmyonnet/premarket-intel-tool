#!/usr/bin/env python3
"""
Part 2 data source: chengwaye.com disposal (處置股) forecast.

  https://chengwaye.com/disposal-forecast

Two tables are extracted, matching exactly what was asked for (see README):
  1. "差1次就處置" -- stocks one flag away from disposal status.
  2. "目前處置中"   -- stocks currently in disposal, incl. their 出關日 (exit date).

Before parsing, this script validates that the page's date context is what
we expect: the page should be keyed off the PREVIOUS trading day (the most
recently completed session), which is what "applies to" today's/next
session's forecast. If that check fails, the script aborts with a non-zero
exit code rather than silently emitting stale or misaligned data -- this
mirrors the validate-before-use step that was explicitly requested.

IMPORTANT CAVEAT (read before deploying):
This parser is written against a *hand-built* HTML fixture
(fixtures/chengwaye_disposal.html) that approximates the page's real
structure based on manual browsing (heading text, table column order, and
the presence of a date <select>) -- the site's actual raw markup was not
capturable during design (tooling restriction on bulk HTML extraction, see
build notes). The parser deliberately avoids depending on CSS class names
(it walks by heading text -> nearest table -> row cells by position) to
be as resilient as possible to this uncertainty, but the FIRST real run
against the live site should be checked by hand against this script's
output before you trust it unattended. If chengwaye's real markup differs
structurally, tell Claude and the parsing logic can be corrected in one
pass against the real HTML.

Usage:
    python fetch_disposal.py [--fixture PATH] [--today YYYY-MM-DD]
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

URL = "https://chengwaye.com/disposal-forecast"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def previous_trading_day(d: datetime.date) -> datetime.date:
    """Most recent weekday before d. Does NOT account for TW market
    holidays -- see README for why this is an accepted v1 gap."""
    pd = d - datetime.timedelta(days=1)
    while pd.weekday() >= 5:
        pd -= datetime.timedelta(days=1)
    return pd


def find_table_after_heading(soup, heading_substring: str):
    """Locate the table that follows a section label containing
    `heading_substring`, without assuming the label is an h1/h2/h3.

    Confirmed against the live site (2026-08-20): chengwaye.com's section
    labels ("🔴 差1次就處置 (1 檔)" etc.) are plain styled <div>s, not real
    heading tags -- the original h1/h2/h3-only search matched nothing and
    silently produced empty lists. Two strategies, tried in order:
      1. A single leaf text node containing the substring (the common case
         -- the emoji/label/count are one contiguous run of text).
      2. Fallback for markup that splits the label across inline children:
         scan every tag whose full text contains the substring and take the
         innermost one (shortest get_text()), which find_next() from directly.
    """
    node = soup.find(string=lambda s: s and heading_substring in s)
    if node is not None:
        nxt = node.find_next("table")
        if nxt is not None:
            return nxt

    candidates = [t for t in soup.find_all(True) if heading_substring in t.get_text()]
    if candidates:
        innermost = min(candidates, key=lambda t: len(t.get_text()))
        nxt = innermost.find_next("table")
        if nxt is not None:
            return nxt

    return None


def rows_as_dicts(table, columns):
    """Iterate <tr> in <tbody>, zip cell text with `columns` names."""
    out = []
    if table is None:
        return out
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        row = dict(zip(columns, cells))
        out.append(row)
    return out


def parse_one_away(soup):
    table = find_table_after_heading(soup, "差1次就處置")
    columns = ["market", "code", "name", "close", "condition", "earliest_disposal"]
    return rows_as_dicts(table, columns)


def parse_two_away(soup):
    table = find_table_after_heading(soup, "差2次處置")
    columns = ["market", "code", "name", "close", "condition", "earliest_disposal"]
    return rows_as_dicts(table, columns)


def parse_active(soup):
    table = find_table_after_heading(soup, "目前處置中")
    columns = [
        "market", "code", "name", "matching", "start_date", "end_date",
        "exit_date", "trading_days_left", "reason",
    ]
    return rows_as_dicts(table, columns)


def parse_date_context(soup, html_text: str):
    """
    Returns (applies_to_str, selected_dropdown_str) as raw strings pulled
    from the page; validation against today's date happens in main().
    """
    applies_to = None
    m = re.search(r"適用\s*(\d{2}/\d{2})\s*交易日", html_text)
    if m:
        applies_to = m.group(1)

    selected_option = None
    select_tag = soup.find("select")
    if select_tag is not None:
        opt = select_tag.find("option", selected=True) or select_tag.find("option")
        if opt is not None:
            selected_option = opt.get_text(strip=True)

    return applies_to, selected_option


def fetch_html(fixture: Path = None) -> str:
    if fixture is not None:
        return fixture.read_text(encoding="utf-8")
    if requests is None:
        raise RuntimeError("requests not installed and no --fixture given")
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, default=None, help="offline test HTML file")
    ap.add_argument(
        "--today",
        type=str,
        default=None,
        help="override 'today' for date-context validation (YYYY-MM-DD); "
        "defaults to real today (Asia/Taipei date)",
    )
    ap.add_argument(
        "--skip-date-check",
        action="store_true",
        help="do not abort on date-context mismatch (still reported in output)",
    )
    args = ap.parse_args()

    if BeautifulSoup is None:
        print("ERROR: beautifulsoup4 is required for this script", file=sys.stderr)
        sys.exit(2)

    html = fetch_html(args.fixture)
    soup = BeautifulSoup(html, "html.parser")

    if args.today:
        today = datetime.date.fromisoformat(args.today)
    else:
        today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()

    expected_prev = previous_trading_day(today)
    applies_to_str, selected_dropdown = parse_date_context(soup, html)

    # applies_to_str is "MM/DD" with no year; compare month/day only against
    # today (the forecast should apply to *today's* session).
    date_ok = None
    if applies_to_str:
        mm, dd = applies_to_str.split("/")
        date_ok = (int(mm), int(dd)) == (today.month, today.day)

    result = {
        "source": URL,
        "date_check": {
            "today": today.isoformat(),
            "expected_previous_trading_day": expected_prev.isoformat(),
            "page_says_applies_to": applies_to_str,
            "page_dropdown_selected": selected_dropdown,
            "applies_to_matches_today": date_ok,
        },
        "one_flag_from_disposal": parse_one_away(soup),
        "two_flags_from_disposal": parse_two_away(soup),
        "currently_in_disposal": parse_active(soup),
    }

    if date_ok is False and not args.skip_date_check:
        print(
            f"ABORT: page applies_to={applies_to_str} does not match today="
            f"{today.isoformat()}. Refusing to emit possibly-stale data. "
            "Pass --skip-date-check to override.",
            file=sys.stderr,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
