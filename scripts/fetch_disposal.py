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


BADGE_SPECS = [
    (6, "3①"),
    (7, "5"),
    (8, "6"),
    (9, "12"),
]

# The "處置標準條件" cell's text segments carry the site's own color-coding
# as inline style="color:#hex" on leaf spans (confirmed present in raw
# server HTML, same as the badge titles -- see parse_badge_title). Mapped
# onto this project's own CSS variables rather than the source's raw hex,
# so the replicated colors stay consistent with the rest of the page's
# dark-panel palette: gray tones -> muted (not-yet-met conditions), the
# source's red/green (already Taiwan-convention 漲=red/跌=green, matching
# this project's --rise/--fall) -> --rise/--fall, its amber "closest to
# triggering" highlight -> --amber, its bold-white "already met" emphasis
# -> --text (this page's default is already near-white) rendered bold.
# Unknown/future hex values fall back to muted rather than breaking.
_CONDITION_COLOR_RE = re.compile(r"color:\s*(#[0-9a-fA-F]{3,6})")
_CONDITION_COLOR_MAP = {
    "555": "var(--muted)", "555555": "var(--muted)",
    "888": "var(--muted)", "888888": "var(--muted)",
    "aaa": "var(--muted)", "aaaaaa": "var(--muted)",
    "8b949e": "var(--muted)", "e0e0e0": "var(--muted)",
    "f39c12": "var(--amber)",
    "e74c3c": "var(--rise)", "2ea043": "var(--rise)",
    "2ecc71": "var(--fall)",
    "fff": "var(--text)", "ffffff": "var(--text)",
}


def parse_condition_segments(td):
    """Extract the 處置標準條件 cell's colored text segments, preserving
    the source site's own color-coding instead of flattening to plain
    text (see _CONDITION_COLOR_MAP for the color -> meaning mapping).
    Walks leaf elements carrying an inline color style, in document
    order, and concatenates their text with no added separators (matches
    how the source's own spans butt up against each other with spacing
    already baked into the text nodes). Falls back to a single uncolored
    segment with the cell's flat text if no styled spans are found
    (layout changed -- degrade gracefully, same philosophy as the rest
    of this file), or [] for an empty/missing cell."""
    if td is None:
        return []
    styled = [
        el for el in td.find_all(True)
        if el.get("style") and "color" in el.get("style", "") and not el.find(True)
    ]
    if not styled:
        text = td.get_text(strip=True)
        return [{"text": text, "color": None, "bold": False}] if text else []
    segments = []
    for el in styled:
        text = el.get_text(strip=True)
        if not text:
            continue
        m = _CONDITION_COLOR_RE.search(el.get("style", ""))
        hex_val = m.group(1).lstrip("#").lower() if m else None
        color_var = _CONDITION_COLOR_MAP.get(hex_val, "var(--muted)") if hex_val else None
        segments.append({
            "text": text,
            "color": color_var,
            "bold": hex_val in ("fff", "ffffff"),
        })
    return segments


def parse_badge_title(td):
    """The "3①/5/6/12" progress-dot cells (連續3日第1款／連續5日／10日內6
    次／30日內12次) render their X/Y value only inside a child <div
    title="連續5日（第1~7款） 4/5">, as a JS-free flex row of small filled/
    unfilled dot <span>s -- there is no visible text, so get_text() alone
    returns "". Confirmed against the live site (2026-08-21) that this
    title attribute is present in the raw server HTML (checked via the
    page's own fetch(), not just the post-hydration DOM), so plain
    requests+BeautifulSoup can read it same as everything else here.
    Returns None if the cell/div/title isn't there (layout changed --
    degrade gracefully, same philosophy as the rest of this file)."""
    if td is None:
        return None
    div = td.find("div")
    title = (div.get("title") if div is not None else None) or td.get("title")
    if not title:
        return None
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*$", title)
    if not m:
        return {"title": title, "current": None, "threshold": None}
    return {"title": title, "current": int(m.group(1)), "threshold": int(m.group(2))}


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


def rows_as_dicts(table, columns, with_badges=False, with_condition_segments=False):
    """Iterate <tr> in <tbody>, zip cell text with `columns` names.

    Confirmed against the live site (2026-08-20): the two "away from
    disposal" tables interleave each real data row with a second, hidden
    <tr> holding the "▶" expandable detail panel (collapses to a single
    <td colspan=...> with a long calculation breakdown). That row only
    produces 1 cell, so requiring an exact column-count match both drops
    it and guards against any other row shape that doesn't match what we
    expect, rather than silently emitting a mostly-empty row.

    with_badges=True additionally reads the 4 "3①/5/6/12" progress-dot
    cells at fixed positions (see BADGE_SPECS/parse_badge_title) into a
    row["badges"] list of {short, title, current, threshold} dicts, in
    the same left-to-right order as the source page's columns. Used by
    the two "away from disposal" tables only -- parse_active's table has
    no such cells.

    with_condition_segments=True additionally reads the "condition"
    column (must be present in `columns`) into a row["condition_segments"]
    list via parse_condition_segments, preserving the source's own
    color-coding instead of the flattened plain-text `condition` value.
    """
    out = []
    if table is None:
        return out
    body = table.find("tbody") or table
    condition_idx = columns.index("condition") if with_condition_segments and "condition" in columns else None
    for tr in body.find_all("tr"):
        tds = tr.find_all("td")
        cells = [td.get_text(strip=True) for td in tds]
        # Real data rows have >= len(columns) cells (there may be extra
        # trailing icon/info cells on the live site beyond what we name --
        # zip() below just ignores those). The collapsed "▶" detail rows
        # have exactly 1 cell, always < len(columns), so this drops them
        # without needing to know the live site's exact real cell count.
        if len(cells) < len(columns):
            continue
        row = dict(zip(columns, cells))
        if with_badges:
            row["badges"] = []
            for idx, short in BADGE_SPECS:
                b = parse_badge_title(tds[idx]) if idx < len(tds) else None
                row["badges"].append({
                    "short": short,
                    "title": (b or {}).get("title"),
                    "current": (b or {}).get("current"),
                    "threshold": (b or {}).get("threshold"),
                })
        if condition_idx is not None:
            row["condition_segments"] = parse_condition_segments(
                tds[condition_idx] if condition_idx < len(tds) else None
            )
        out.append(row)
    return out


def parse_one_away(soup):
    table = find_table_after_heading(soup, "差1次就處置")
    columns = ["market", "code", "name", "close", "condition", "earliest_disposal"]
    return rows_as_dicts(table, columns, with_badges=True, with_condition_segments=True)


def parse_two_away(soup):
    table = find_table_after_heading(soup, "差2次處置")
    columns = ["market", "code", "name", "close", "condition", "earliest_disposal"]
    return rows_as_dicts(table, columns, with_badges=True)


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
