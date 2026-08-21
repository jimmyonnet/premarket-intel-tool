#!/usr/bin/env python3
"""
Part 3 (extra) data source: chengwaye.com's per-stock 法人買賣/當沖 detail.

  https://chengwaye.com/daily

The page lists today's "漲停" (limit-up) stock list (28 codes on the day
this was built), and for each one embeds the full 法人買賣Top15 /
當沖Top10 dataset used by its own click-to-expand row detail + bubble
chart, as two hydration <script type="application/json"> tags:

  <script id="all-broker-data" type="application/json">
    { "<code>": {
        "buyers":     [ {name, net, buyV, sellV, buyP, sellP, buyStd, sellStd}, ... up to 15 ],
        "sellers":    [ same shape, ... up to 15 ],
        "daytraders": [ {name, buyV, sellV, buyP, sellP, total}, ... up to 10 ]
      }, ... }
  </script>
  <script id="all-prices-data" type="application/json">
    { "<code>": {close, flat, limitUp, name}, ... }
  </script>

Confirmed against the live site (2026-08-21, via browser DOM inspection):
  - buyV/sellV/net/total are in SHARES (股) -- divide by 1000 for 張(lots)
    to match how the site's own tables display them.
  - buyers[].net is always >= 0, sellers[].net is always <= 0; both arrays
    are already sorted by |net| descending (i.e. rank 1 = biggest).
  - buyP/sellP is null when that side has 0 volume (rendered as "—").
  - There is NO field anywhere in this data corresponding to the site's
    rendered 當沖Top10 "總損益" (day-trade P&L) column -- multiple formula
    attempts (sellV*sellP - buyV*buyP, plus variants using close/flat as a
    residual price) failed to reproduce a real sample value from the site.
    This script does not emit a total_pnl field; build_page.py/the
    template must not display or estimate one. Do not try to backfill
    this by guessing -- showing a wrong P&L number to a day trader making
    real decisions is worse than showing nothing.

This is a plain server-rendered page (same site family as
chengwaye.com/disposal-forecast, which fetch_disposal.py already fetches
successfully with plain requests) -- these are Next.js-style hydration
script tags, which are always present in the initial server HTML (that's
the point of them), not injected later by client JS. No Playwright/login
needed, unlike Part 3's PressPlay fetch.

Usage:
    python fetch_chengwaye_daily.py [--fixture PATH]
"""
import argparse
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

URL = "https://chengwaye.com/daily"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def fetch_html(fixture: Path = None) -> str:
    if fixture is not None:
        return fixture.read_text(encoding="utf-8")
    if requests is None:
        raise RuntimeError("requests not installed and no --fixture given")
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_page_date(soup, html_text: str):
    """Best-effort page date label, e.g. "2026/08/20" -- shown to the
    reader as a source-date note, same spirit as Part 2's date_check.
    Not validated/aborted-on like Part 2, since this section is additive
    (missing/stale date label just means we skip the note, not the data)."""
    select = soup.find("select", id="date-picker")
    if select is not None:
        opt = select.find("option", selected=True) or select.find("option")
        if opt is not None:
            text = opt.get_text(strip=True)
            if re.match(r"^\d{4}/\d{2}/\d{2}$", text):
                return text
    m = re.search(r"漲停當日\s*(\d{4}/\d{2}/\d{2})", html_text)
    return m.group(1) if m else None


def parse_json_script(soup, script_id: str):
    tag = soup.find("script", id=script_id)
    if tag is None or not tag.string:
        return {}
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        print(f"WARNING: #{script_id} is not valid JSON, treating as empty", file=sys.stderr)
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, default=None, help="offline test HTML file")
    args = ap.parse_args()

    if BeautifulSoup is None:
        print("ERROR: beautifulsoup4 is required for this script", file=sys.stderr)
        sys.exit(2)

    html = fetch_html(args.fixture)
    soup = BeautifulSoup(html, "html.parser")

    broker_data = parse_json_script(soup, "all-broker-data")
    prices_data = parse_json_script(soup, "all-prices-data")
    page_date = parse_page_date(soup, html)

    codes = {}
    for code, broker in broker_data.items():
        price = prices_data.get(code) or {}
        codes[code] = {
            "name": price.get("name"),
            "close": price.get("close"),
            "flat": price.get("flat"),
            "limit_up": price.get("limitUp"),
            "buyers": broker.get("buyers") or [],
            "sellers": broker.get("sellers") or [],
            "daytraders": broker.get("daytraders") or [],
        }

    result = {
        "source": URL,
        "page_date": page_date,
        "codes": codes,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
