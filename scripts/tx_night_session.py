#!/usr/bin/env python3
"""
Part 1 data source: TX futures night session (台指期夜盤/盤後) trend & quotes.

Implements multi-provider fallback chain:
1. Yahoo Finance (yfinance / Ticker "TXF=F" 1m interval)
2. FinMind Open Data API
3. Wantgoo / TAIFEX official quote API
4. Offline Fixture fallback

Usage:
    # take one snapshot using default fallback chain (yahoo -> finmind -> wantgoo -> fixture)
    python tx_night_session.py collect --data-dir data/night_session

    # take snapshot with explicit provider
    python tx_night_session.py collect --data-dir data/night_session --provider yahoo

    # assemble chart series and latest summary
    python tx_night_session.py assemble --data-dir data/night_session --date 2026-08-22
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import requests

TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
TAIFEX_API_URL = "https://mis.taifex.com.tw/futures/api/getQuoteList"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def fetch_yahoo_snapshot(now: datetime.datetime) -> dict:
    """Fetch TX night session quote via yfinance TXF=F."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("TXF=F")
        df = ticker.history(period="1d", interval="1m")
        if df is not None and not df.empty:
            recent_5m = df.tail(5)
            latest_row = recent_5m.iloc[-1]
            price = round(float(latest_row["Close"]), 2)
            open_ = round(float(df["Open"].iloc[0]), 2)
            high = round(float(df["High"].max()), 2)
            low = round(float(df["Low"].min()), 2)
            volume = int(df["Volume"].sum())
            prev_close = open_
            try:
                if hasattr(ticker, "fast_info") and getattr(ticker.fast_info, "previous_close", None):
                    prev_close = float(ticker.fast_info.previous_close)
            except Exception:
                pass
            change = round(price - prev_close, 2)
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0

            return {
                "provider": "yahoo",
                "provider_name": "Yahoo",
                "collected_at": now.isoformat(),
                "symbol": "臺指期 TXF=F",
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "open": open_,
                "prev_close": prev_close,
                "high": high,
                "low": low,
                "volume": volume,
            }
    except Exception as e:
        print(f"Yahoo provider failed: {e}", file=sys.stderr)
    return None


def fetch_finmind_snapshot(now: datetime.datetime) -> dict:
    """Fetch TX futures quote from FinMind dataset."""
    try:
        url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanFuturesSnapshot&data_id=TX"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            if items:
                item = items[0]
                price = float(item.get("close") or item.get("price") or item.get("settlement_price"))
                open_ = float(item.get("open") or price)
                high = float(item.get("high") or price)
                low = float(item.get("low") or price)
                change = float(item.get("change") or 0.0)
                change_pct = float(item.get("change_rate") or 0.0)
                prev_close = round(price - change, 2)
                volume = int(item.get("volume") or 0)
                return {
                    "provider": "finmind",
                    "provider_name": "FinMind",
                    "collected_at": now.isoformat(),
                    "symbol": "臺指期",
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "open": open_,
                    "prev_close": prev_close,
                    "high": high,
                    "low": low,
                    "volume": volume,
                }
    except Exception as e:
        print(f"FinMind provider failed: {e}", file=sys.stderr)
    return None


def fetch_taifex_snapshot(now: datetime.datetime) -> dict:
    """Fetch quote directly from official TAIFEX / Wantgoo source."""
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
        return None

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
        "provider": "wantgoo",
        "provider_name": "Wantgoo / TAIFEX",
        "collected_at": now.isoformat(),
        "symbol": selected_quote.get("DispCName") or "臺指期",
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "open": open_,
        "prev_close": prev_close,
        "high": high,
        "low": low,
        "volume": volume,
    }


def fetch_fixture_snapshot(now: datetime.datetime, fixture_path: Path = None) -> dict:
    """Load from fallback fixture when all live sources fail."""
    candidates = [
        Path("fixtures/night_session.json"),
        Path("fixtures/night_session_fallback.json"),
        Path("data/latest/night_session.json")
    ]
    if fixture_path:
        candidates.insert(0, Path(fixture_path))

    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                latest = data.get("latest") or (data if data.get("price") else None)
                if latest and latest.get("price"):
                    out = dict(latest)
                    out["provider"] = "fixture"
                    out["provider_name"] = f"fixtures/{data.get('date', 'fallback')}"
                    out["is_fallback"] = True
                    out["collected_at"] = now.isoformat()
                    return out
            except Exception:
                pass

    return {
        "provider": "fixture",
        "provider_name": "fixtures/fallback",
        "is_fallback": True,
        "collected_at": now.isoformat(),
        "symbol": "臺指期 (離線快照)",
        "price": 45203.0,
        "change": 65.0,
        "change_pct": 0.14,
        "open": 45220.0,
        "prev_close": 45138.0,
        "high": 45474.0,
        "low": 45126.0,
        "volume": 15611,
    }


def fetch_snapshot_with_fallback(now: datetime.datetime, preferred_provider: str = None, fixture_path: str = None) -> dict:
    """Fallback chain: yahoo -> finmind -> wantgoo -> fixture."""
    providers = {
        "yahoo": fetch_yahoo_snapshot,
        "finmind": fetch_finmind_snapshot,
        "wantgoo": fetch_taifex_snapshot,
        "fixture": lambda n: fetch_fixture_snapshot(n, fixture_path),
    }

    if preferred_provider and preferred_provider in providers:
        # Preferred first, then others in order
        order = [preferred_provider] + [p for p in ["yahoo", "finmind", "wantgoo", "fixture"] if p != preferred_provider]
    else:
        order = ["yahoo", "finmind", "wantgoo", "fixture"]

    for name in order:
        try:
            snapshot = providers[name](now)
            if snapshot and snapshot.get("price") is not None:
                return snapshot
        except Exception as e:
            print(f"Provider {name} failed: {e}", file=sys.stderr)

    return fetch_fixture_snapshot(now, fixture_path)


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
        snapshot = fetch_fixture_snapshot(now, args.fixture)
    else:
        snapshot = fetch_snapshot_with_fallback(now, preferred_provider=args.provider, fixture_path=args.fixture)

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
    live_snapshot = fetch_snapshot_with_fallback(now, preferred_provider=args.provider if hasattr(args, "provider") else None)

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
        "provider": latest_val.get("provider", "wantgoo"),
        "provider_name": latest_val.get("provider_name", "Wantgoo / TAIFEX"),
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
    c.add_argument("--provider", default=None, choices=["yahoo", "finmind", "wantgoo", "fixture"], help="preferred data provider")
    c.set_defaults(func=cmd_collect)

    a = sub.add_parser("assemble", help="read back a session's snapshots as chart data")
    a.add_argument("--data-dir", required=True)
    a.add_argument("--date", required=True)
    a.add_argument("--provider", default=None, choices=["yahoo", "finmind", "wantgoo", "fixture"], help="preferred data provider")
    a.set_defaults(func=cmd_assemble)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
