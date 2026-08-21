#!/usr/bin/env python3
"""
Part 1 data source: TX futures night session (台指期夜盤/盤後) trend & quotes.

Fetches official quote data directly from TAIFEX (台灣期貨交易所 mis.taifex.com.tw API)
without headless browser dependencies or Cloudflare IP blocking risks.

Usage:
    # take one snapshot, appended to data/night_session/<target-date>.jsonl
    python tx_night_session.py collect --data-dir ../data/night_session

    # read back today's snapshots as a chart-ready list
    python tx_night_session.py assemble --data-dir ../data/night_session --date 2026-08-21
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import requests

TAIFEX_API_URL = "https://mis.taifex.com.tw/futures/api/getQuoteList"
TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def fetch_taifex_snapshot(now: datetime.datetime) -> dict:
    """Fetch real-time night session (or day session fallback) quote directly from TAIFEX official API."""
    market_types = ["1", "0"]
    selected_quote = None

    for mtype in market_types:
        try:
            resp = requests.post(
                TAIFEX_API_URL,
                json={"MarketType": mtype, "SymbolType": "F"},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                quote_list = data.get("RtData", {}).get("QuoteList", [])
                candidates = [
                    q for q in quote_list
                    if q.get("SymbolID", "").endswith("-M") and "臺指" in q.get("DispCName", "")
                ]
                if candidates and candidates[0].get("CLastPrice"):
                    selected_quote = candidates[0]
                    break
        except Exception as e:
            print(f"Warning: TAIFEX API MarketType={mtype} failed: {e}", file=sys.stderr)

    if not selected_quote:
        return {
            "collected_at": now.isoformat(),
            "price": None,
            "change": None,
            "change_pct": None,
            "open": None,
            "prev_close": None,
            "high": None,
            "low": None,
            "volume": None,
        }

    def to_float(val):
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return None

    def to_int(val):
        try:
            return int(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return None

    price = to_float(selected_quote.get("CLastPrice"))
    change = to_float(selected_quote.get("CDiff"))
    change_pct = to_float(selected_quote.get("CDiffRate"))
    open_ = to_float(selected_quote.get("COpenPrice"))
    prev_close = to_float(selected_quote.get("CRefPrice"))
    high = to_float(selected_quote.get("CHighPrice"))
    low = to_float(selected_quote.get("CLowPrice"))
    volume = to_int(selected_quote.get("CTotalVolume"))

    if change is not None and change_pct is not None:
        if change_pct < 0 and change > 0:
            change = -change
        elif change_pct > 0 and change < 0:
            change_pct = -change_pct

    return {
        "collected_at": now.isoformat(),
        "symbol": selected_quote.get("DispCName"),
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
    nd = d + datetime.timedelta(days=1)
    while nd.weekday() >= 5:
        nd += datetime.timedelta(days=1)
    return nd


def target_session_date(now: datetime.datetime) -> datetime.date:
    if now.hour >= 15:
        return next_trading_day(now.date())
    if now.hour < 5:
        return now.date()
    return now.date()


def cmd_collect(args):
    now = datetime.datetime.now(TAIPEI)
    if args.fixture:
        text = Path(args.fixture).read_text(encoding="utf-8")
        snapshot = json.loads(text) if text.startswith("{") else {"collected_at": now.isoformat()}
    else:
        snapshot = fetch_taifex_snapshot(now)

    session_date = args.date or (target_session_date(now).isoformat() if not args.fixture else now.date().isoformat())

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / f"{session_date}.jsonl"
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    print(f"appended snapshot to {out_path}: {snapshot}", file=sys.stderr)


def cmd_assemble(args):
    data_dir = Path(args.data_dir)
    path = data_dir / f"{args.date}.jsonl"

    points = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    points.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    points.sort(key=lambda p: p.get("collected_at", ""))

    now = datetime.datetime.now(TAIPEI)
    live_snapshot = fetch_taifex_snapshot(now)

    open_val = points[0]["open"] if points and points[0].get("open") is not None else live_snapshot.get("open")
    prev_close_val = points[0]["prev_close"] if points and points[0].get("prev_close") is not None else live_snapshot.get("prev_close")

    valid_highs = [p["high"] for p in points if p.get("high") is not None]
    if live_snapshot.get("high") is not None:
        valid_highs.append(live_snapshot["high"])
    high_val = max(valid_highs, default=None)

    valid_lows = [p["low"] for p in points if p.get("low") is not None]
    if live_snapshot.get("low") is not None:
        valid_lows.append(live_snapshot["low"])
    low_val = min(valid_lows, default=None)

    latest_val = points[-1] if points else live_snapshot

    out = {
        "date": args.date,
        "points": points,
        "open": open_val,
        "prev_close": prev_close_val,
        "high": high_val,
        "low": low_val,
        "latest": latest_val,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="take one snapshot and append it")
    c.add_argument("--data-dir", required=True)
    c.add_argument("--fixture", default=None)
    c.add_argument("--date", default=None)
    c.set_defaults(func=cmd_collect)

    a = sub.add_parser("assemble", help="read back a session's snapshots as chart data")
    a.add_argument("--data-dir", required=True)
    a.add_argument("--date", required=True)
    a.set_defaults(func=cmd_assemble)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
