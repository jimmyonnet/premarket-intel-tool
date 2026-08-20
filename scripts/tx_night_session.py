#!/usr/bin/env python3
"""
Part 1 data source: TX futures night session (台指期夜盤/盤後, symbol WTXP&)
trend chart.

Why this exists as two pieces (collector + assembler) instead of one fetch:
wantgoo.com's own minute-bar chart is powered by an internal JSON API
(`/investrue/wtxp&/minute-candlestick`) that returned 400 on every direct
call during design -- it likely needs extra request state (session token /
specific params) we could not reverse-engineer without risking looking like
abusive traffic to their site. Rather than depend on an undocumented private
endpoint, this script builds its OWN minute-resolution series by being
called repeatedly (every ~30min via the `collect-night-session` GitHub
Action) through the night session window, snapshotting the current quote
each time and appending it to a small per-session-date data file. The
morning build step (`build_page.py`) just reads back all of that day's
snapshots to draw the chart.

FETCH METHOD -- headless browser, not requests (changed 2026-08-20):
The single-quote snapshot page (`https://www.wantgoo.com/futures/wtxp&`) is
server-rendered -- open/high/low/current/volume are plain text in the
initial HTML, same verification method as fetch_indices.py. That page loads
fine in a real browser. But a plain `requests.get()` to it gets 403
Forbidden from a GitHub Actions runner, confirmed on the actual first
scheduled run, not assumed. Two real fix attempts on `requests` both still
403'd (see README for the full history: full browser-style headers, then a
session/cookie warm-up hitting the homepage first) -- the homepage loaded
fine both times, only this quote page didn't, which points to TLS/browser-
fingerprint bot detection on that specific endpoint rather than a blocked
IP range or a missing header. That kind of check is set at the TLS
handshake / HTTP engine level, below where `requests` headers apply, so no
amount of header tuning could satisfy it. Switching the fetch to a real
headless Chromium via Playwright (`fetch_with_browser()` below) fixed it --
confirmed live on GitHub Actions, not assumed. Trade-off: `collect` now
needs `playwright install --with-deps chromium` in the workflow (see
collect-night-session.yml) and each run is slower (~30-60s browser
launch+install vs. a plain HTTP GET), but this repo is public so GitHub
Actions minutes are unlimited regardless -- correctness over speed here.

Usage:
    # one snapshot, appended to data/night_session/<target-date>.jsonl
    python tx_night_session.py collect --data-dir ../data/night_session

    # read back today's snapshots as a chart-ready list
    python tx_night_session.py assemble --data-dir ../data/night_session --date 2026-08-21

    # offline test mode for `collect` (no browser/network needed --
    # fixtures are pre-flattened text, see fetch_with_browser() docstring)
    python tx_night_session.py collect --fixture ../fixtures/wantgoo_wtxp.txt --data-dir /tmp/out
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

WTXP_URL = "https://www.wantgoo.com/futures/wtxp&"

TAIPEI = datetime.timezone(datetime.timedelta(hours=8))


def fetch_with_browser(url: str) -> str:
    """Fetch `url` with a real headless Chromium (Playwright) and return the
    rendered page's HTML. See the module docstring's "FETCH METHOD" section
    for why this replaced a plain `requests.get()` (403 from this specific
    endpoint, confirmed not fixable with headers alone).
    """
    if sync_playwright is None:
        raise RuntimeError(
            "playwright is not installed -- run "
            "`playwright install --with-deps chromium` (see requirements.txt)"
        )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(locale="zh-TW")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Server-rendered -- values are already in the HTML at this
            # point (verified during design) -- but give any live-quote
            # hydration a brief moment to settle rather than trusting the
            # very first paint.
            page.wait_for_timeout(1500)
            return page.content()
        finally:
            browser.close()


def get_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n")
    except ImportError:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
        return re.sub(r"<[^>]+>", "\n", text)


def parse_snapshot(text: str, now: datetime.datetime) -> dict:
    """
    Pattern (see fixtures/wantgoo_wtxp.txt):
        44718.00
        -185.00 -0.41%
        開盤
        44982.00
        昨收
        44802.00
        最高
        45000.00
        最低
        44612.00
        ...
        成交量(口)
        7,644
    """
    def grab(pattern, cast=float, default=None):
        m = re.search(pattern, text)
        if not m:
            return default
        return cast(m.group(1).replace(",", ""))

    price = grab(r"\n(-?[\d,]+\.\d+)\s*\n\s*-?[\d,]+\.\d+\s*-?[\d.]+%")
    change = grab(r"\n(-?[\d,]+\.\d+)\s+-?[\d.]+%")
    change_pct = grab(r"\n-?[\d,]+\.\d+\s+(-?[\d.]+)%")
    open_ = grab(r"開盤\s*\n\s*([\d,]+\.\d+)")
    prev_close = grab(r"昨收\s*\n\s*([\d,]+\.\d+)")
    high = grab(r"最高\s*\n\s*([\d,]+\.\d+)")
    low = grab(r"最低\s*\n\s*([\d,]+\.\d+)")
    volume = grab(r"成交量\(口\)\s*\n\s*([\d,]+)", cast=int)

    return {
        "collected_at": now.isoformat(),
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "open": open_,
        "prev_close": prev_close,
        "high": high,
        "low": low,
        "volume": volume,
    }


def next_trading_day(d: datetime.date) -> datetime.date:
    """Next weekday. Does NOT account for TW market holidays (see README)."""
    nd = d + datetime.timedelta(days=1)
    while nd.weekday() >= 5:  # Sat=5, Sun=6
        nd += datetime.timedelta(days=1)
    return nd


def target_session_date(now: datetime.datetime) -> datetime.date:
    """
    Which cash trading day does a snapshot collected `now` belong to?
    Night session runs ~15:00 -> ~05:00 next day (Taipei time) and always
    preps the NEXT cash open.
      - collected in the evening (hour >= 15): belongs to the next trading day.
      - collected after midnight (hour < 5): the session that started the
        previous evening is still running and belongs to TODAY's cash open.
      - anything else (05:00-15:00, i.e. cash session hours): not a valid
        night-session collection window; caller should skip.
    """
    if now.hour >= 15:
        return next_trading_day(now.date())
    if now.hour < 5:
        return now.date()
    raise ValueError(
        f"now={now.isoformat()} is outside the night-session window "
        "(15:00-05:00 Taipei); the collect-night-session Action should not "
        "be scheduled to run here."
    )


def cmd_collect(args):
    now = datetime.datetime.now(TAIPEI)
    if args.fixture:
        html_or_text = Path(args.fixture).read_text(encoding="utf-8")
        text = html_or_text  # fixture is already flattened text
    else:
        html = fetch_with_browser(WTXP_URL)
        text = get_text(html)

    snapshot = parse_snapshot(text, now)

    if args.fixture:
        session_date = args.date or now.date().isoformat()
    else:
        session_date = target_session_date(now).isoformat()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / f"{session_date}.jsonl"
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    missing = [k for k, v in snapshot.items() if v is None and k != "collected_at"]
    if missing:
        print(f"WARNING: snapshot missing fields {missing}", file=sys.stderr)
    print(f"appended snapshot to {out_path}: {snapshot}", file=sys.stderr)


def cmd_assemble(args):
    data_dir = Path(args.data_dir)
    path = data_dir / f"{args.date}.jsonl"
    if not path.exists():
        print(json.dumps({"date": args.date, "points": [], "_warning": "no data file"}))
        return
    points = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            points.append(json.loads(line))
    points.sort(key=lambda p: p["collected_at"])
    out = {
        "date": args.date,
        "points": points,
        "open": points[0]["open"] if points else None,
        "prev_close": points[0]["prev_close"] if points else None,
        "high": max((p["high"] for p in points if p.get("high") is not None), default=None),
        "low": min((p["low"] for p in points if p.get("low") is not None), default=None),
        "latest": points[-1] if points else None,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="take one snapshot and append it")
    c.add_argument("--data-dir", required=True)
    c.add_argument("--fixture", default=None, help="offline test: read this file instead of the network")
    c.add_argument("--date", default=None, help="override session date (fixture mode only)")
    c.set_defaults(func=cmd_collect)

    a = sub.add_parser("assemble", help="read back a session's snapshots as chart data")
    a.add_argument("--data-dir", required=True)
    a.add_argument("--date", required=True)
    a.set_defaults(func=cmd_assemble)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
