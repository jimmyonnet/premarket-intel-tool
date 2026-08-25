#!/usr/bin/env python3
"""Build the server-rendered premarket GitHub Pages document and data packages."""

from __future__ import annotations

import math

import argparse
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from jinja2 import Environment, FileSystemLoader

from trading_calendar import (
    get_next_trading_day,
    get_current_trading_day,
    is_twse_trading_day,
    load_twse_holidays,
)
from source_status import evaluate_source_health, SOURCES_METADATA
from build_packages import write_packages


def fmt_num(v, decimals=2, fallback="—"):
    if v is None or v == "" or str(v).lower() in ("nan", "null", "none"):
        return fallback
    try:
        f = float(v)
        if math.isnan(f):
            return fallback
        if decimals == 0:
            return f"{int(round(f)):,}"
        return f"{f:,.{decimals}f}"
    except Exception:
        return str(v)


def fmt_pct(v, decimals=2, fallback="—"):
    if v is None or v == "" or str(v).lower() in ("nan", "null", "none"):
        return fallback
    try:
        f = float(v)
        if math.isnan(f):
            return fallback
        return f"{f:+.{decimals}f}%"
    except Exception:
        return str(v)


TAIPEI = timezone(timedelta(hours=8))
NEW_YORK = ZoneInfo("America/New_York")



def build_us_market_context(now, indices):
    """Describe the US session and the newest source timestamp conservatively.

    Yahoo Finance Chart exposes a source update timestamp but not a dependable
    delay-minutes entitlement field. The page therefore reports the observed
    quote time and session, without claiming that the snapshot is zero-delay.
    """
    ny_now = now.astimezone(NEW_YORK)
    minutes = ny_now.hour * 60 + ny_now.minute
    is_weekday = ny_now.weekday() < 5
    if is_weekday and 9 * 60 + 30 <= minutes < 16 * 60:
        session_key, session_label, badge, pill_class = "regular", "美股盤中快照", "盤中", "pill-live"
    elif is_weekday and 4 * 60 <= minutes < 9 * 60 + 30:
        session_key, session_label, badge, pill_class = "pre", "美股盤前", "盤前", "pill-amber"
    elif is_weekday and 16 * 60 <= minutes < 20 * 60:
        session_key, session_label, badge, pill_class = "after", "美股盤後", "盤後", "pill-amber"
    else:
        session_key, session_label, badge, pill_class = "closed", "最新收盤快照", "收盤", "pill-fresh"

    timestamps = []
    for quote in (indices.get("us_indices", {}) or {}).values():
        raw = quote.get("updated_at") if isinstance(quote, dict) else None
        if raw:
            try:
                timestamps.append(datetime.fromisoformat(raw))
            except (TypeError, ValueError):
                pass
    latest = max(timestamps) if timestamps else None
    if latest is not None:
        age_minutes = max(0, round((now - latest).total_seconds() / 60))
        age_label = f"{max(1, age_minutes)} 分鐘前" if age_minutes < 60 else f"{age_minutes / 60:.1f} 小時前"
        updated_label = latest.strftime("%m/%d %H:%M")
        detail = f"Yahoo Finance · 來源更新 {updated_label}（{age_label}）· 延遲分鐘數未提供"
        title = "Yahoo Finance Chart 提供來源更新時間；未提供可驗證的延遲分鐘數"
    else:
        updated_label = "來源時間未提供"
        detail = "Yahoo Finance · 來源時間未提供 · 延遲分鐘數未提供"
        title = "來源未提供可驗證的行情時間，請以 Yahoo Finance 報價頁交易資訊為準"

    if session_key == "regular":
        detail += " · 美國正常交易時段"
    elif session_key == "pre":
        detail += " · 尚未進入美股正常交易時段"
    elif session_key == "after":
        detail += " · 正常交易時段已結束"
    else:
        detail += " · 美國非正常交易時段"

    return {
        "session_key": session_key,
        "label": session_label,
        "badge": badge,
        "badge_short": badge,
        "pill_class": pill_class,
        "updated_label": updated_label,
        "detail": detail,
        "title": title,
    }



ASIA_SESSION_WINDOWS_TPE = {
    # Japan: 09:00-11:30 and 12:30-15:30 JST (UTC+9), displayed in Taipei time.
    "^N225": ((8 * 60, 10 * 60 + 30), (11 * 60 + 30, 14 * 60 + 30)),
    # Korea: 09:00-15:30 KST (UTC+9), displayed in Taipei time.
    "^KS11": ((8 * 60, 14 * 60 + 30),),
}


def build_asia_market_context(now, symbol, quote=None):
    """Describe an Asia quote's session without implying zero-delay data.

    Yahoo's quote pages expose a source quote time for these cards, while the
    page build timestamp is separate. The pill therefore describes the local
    exchange session only; the adjacent source-time pill keeps the 20-minute
    Yahoo delay disclosure visible.
    """
    quote = quote or {}
    windows = ASIA_SESSION_WINDOWS_TPE.get(symbol, ())
    minutes = now.hour * 60 + now.minute
    is_weekday = now.weekday() < 5

    if not quote or quote.get("price") is None and quote.get("value") is None:
        badge = "行情未提供"
        pill_class = "pill-amber"
        session_key = "missing"
    elif is_weekday and any(start <= minutes < end for start, end in windows):
        badge = "盤中"
        pill_class = "pill-live"
        session_key = "regular"
    elif not is_weekday:
        badge = "休市"
        pill_class = "pill-fresh"
        session_key = "closed"
    else:
        badge = "收盤"
        pill_class = "pill-fresh"
        session_key = "closed"

    return {
        "session_key": session_key,
        "badge": badge,
        "pill_class": pill_class,
        "title": f"{symbol} 交易時段狀態；旁側 Yahoo 來源時間仍以延遲 20 分鐘說明為準",
    }


def normalize_indices(raw_indices):
    norm = {}
    if not raw_indices:
        return norm
    norm.update(raw_indices)
    
    us = dict(raw_indices.get("us_indices", {}))
    adrs = dict(raw_indices.get("adrs", {}))
    asia = dict(raw_indices.get("asia_open", {}))
    
    # Normalize US
    mapping = {
        "sp500": ["^GSPC", "S&P 500", "sp500", "S&P 500指數"],
        "nasdaq": ["^IXIC", "那斯達克", "nasdaq", "NASDAQ指數"],
        "dow": ["^DJI", "道瓊工業", "dow", "道瓊工業指數"],
        "sox": ["^SOX", "費城半導體", "sox", "費城半導體指數"],
    }
    for key, aliases in mapping.items():
        if key in us:
            item = dict(us[key])
            item["price"] = item.get("value")
            for alias in aliases:
                norm[alias] = item
                us[alias] = item
                
    # Normalize ADRs & Key Stocks
    stock_mapping = {
        "tsmc": ["TSM", "台積電 ADR", "tsmc"],
        "nvda": ["NVDA", "輝達 (NVDA)", "nvda"],
        "aapl": ["AAPL", "蘋果 (AAPL)", "aapl"],
        "micron": ["MU", "美光", "micron"],
        "umc": ["UMC", "聯電 ADR", "umc"],
        "ase": ["ASX", "日月光 ADR", "ase"],
    }
    for key, aliases in stock_mapping.items():
        if key in adrs:
            item = dict(adrs[key])
            item["price"] = item.get("value")
            for alias in aliases:
                norm[alias] = item
                adrs[alias] = item
                
    # Normalize Asia
    asia_mapping = {
        "nikkei225": ["^N225", "日經 225", "日經225指數", "nikkei225"],
        "kospi": ["^KS11", "韓國 KOSPI", "韓國綜合指數", "kospi"],
    }
    for key, aliases in asia_mapping.items():
        if key in asia:
            item = dict(asia[key])
            item["price"] = item.get("value")
            for alias in aliases:
                norm[alias] = item
                asia[alias] = item
                
    norm["us_indices"] = us
    norm["adrs"] = adrs
    norm["asia_open"] = asia
    return norm


def prepare_calendar_timeline(events, today_str):
    today_dt = date.fromisoformat(today_str) if today_str else datetime.now(TAIPEI).date()
    tomorrow_dt = today_dt + timedelta(days=1)
    
    days_to_sunday = 6 - today_dt.weekday()
    this_week_end_dt = today_dt + timedelta(days=days_to_sunday)
    
    WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    
    by_date = {}
    seen_ids = set()
    counter = 1

    for ev in events:
        ev_d_str = ev.get("date")
        if not ev_d_str:
            continue
        try:
            ev_d = date.fromisoformat(ev_d_str)
        except ValueError:
            continue
            
        ev["weekday_label"] = WEEKDAY_NAMES[ev_d.weekday()]
        
        # Guarantee unique ID
        eid = ev.get("id") or f"ev-{ev_d_str}-{counter}"
        while eid in seen_ids:
            counter += 1
            eid = f"ev-{ev_d_str}-{counter}"
        seen_ids.add(eid)
        ev["id"] = eid
        counter += 1
        
        if ev_d not in by_date:
            if ev_d == today_dt:
                rel_label = "今日"
            elif ev_d == tomorrow_dt:
                rel_label = "明日"
            elif ev_d <= this_week_end_dt:
                rel_label = "本週"
            else:
                rel_label = "下週"
            by_date[ev_d] = {
                "date_str": ev_d_str,
                "display_date": f"{rel_label} · {ev_d.strftime('%m/%d')} {WEEKDAY_NAMES[ev_d.weekday()]}",
                "is_today": (ev_d == today_dt),
                "open": (ev_d == today_dt),
                "events": []
            }
        by_date[ev_d]["events"].append(ev)
        
    date_groups = [by_date[d] for d in sorted(by_date.keys())]
    return date_groups

def evaluate_date_check(today: date, page_applies_to: str | None) -> dict[str, Any]:
    """
    Rigorously evaluates whether the disposal source date aligns with the intended trading day.
    """
    if not page_applies_to or not str(page_applies_to).strip():
        return {
            "status": "unknown",
            "label": "日期待確認",
            "class_name": "is-warning",
            "tooltip": "處置資料未標註適用日期",
        }

    target_date = None
    clean_applies = str(page_applies_to).strip()
    if "/" in clean_applies:
        parts = clean_applies.split("/")
        if len(parts) == 2:
            try:
                target_date = date(today.year, int(parts[0]), int(parts[1]))
            except ValueError:
                pass
    elif "-" in clean_applies:
        try:
            target_date = date.fromisoformat(clean_applies)
        except ValueError:
            pass

    if target_date is None:
        return {
            "status": "unknown",
            "label": "格式未辨識",
            "class_name": "is-warning",
            "tooltip": f"處置資料日期格式無法解析: {clean_applies}",
        }

    next_td = get_next_trading_day(today)
    curr_td = get_current_trading_day(today)

    if target_date == next_td:
        return {
            "status": "aligned_next",
            "label": "已對齊次日",
            "class_name": "is-ok",
            "tooltip": f"資料日期已對齊次一交易日（{next_td.strftime('%m/%d')}）",
        }
    elif target_date == today or target_date == curr_td:
        return {
            "status": "same_day",
            "label": "當日盤後",
            "class_name": "is-info",
            "tooltip": f"資料日期為當日交易日（{target_date.strftime('%m/%d')}）",
        }
    else:
        diff_days = (target_date - today).days
        diff_str = f"相差 {diff_days:+d} 天" if diff_days != 0 else "日期待確認"
        return {
            "status": "warning",
            "label": "日期異常",
            "class_name": "is-danger",
            "tooltip": f"處置來源標註適用 {clean_applies}，但目標交易日為 {next_td.strftime('%m/%d')}（{diff_str}）",
        }



def build_sparkline(points, width=680, height=180, pad=28):
    """
    Returns a dict of SVG-ready values for a single-series line chart:
    polyline points string, prev-close reference line y, axis labels,
    and per-point tooltip circles. All in Python so the template stays
    dumb (no computed logic in Jinja).
    """
    if not points:
        return None

    prices = [p["price"] for p in points if p.get("price") is not None]
    if not prices:
        return None

    prev_close = points[0].get("prev_close")
    lo = min(prices + ([prev_close] if prev_close else []))
    hi = max(prices + ([prev_close] if prev_close else []))
    span = (hi - lo) or 1.0
    lo -= span * 0.08
    hi += span * 0.08
    span = hi - lo

    n = len(points)
    plot_w = width - pad * 2
    plot_h = height - pad * 2

    def xy(i, price):
        x = pad + (plot_w * (i / max(n - 1, 1)))
        y = pad + plot_h * (1 - (price - lo) / span)
        return x, y

    coords = []
    dots = []
    for i, p in enumerate(points):
        if p.get("price") is None:
            continue
        x, y = xy(i, p["price"])
        coords.append(f"{x:.1f},{y:.1f}")
        ts = p["collected_at"]
        try:
            hhmm = datetime.fromisoformat(ts).strftime("%H:%M")
        except ValueError:
            hhmm = ""
        dots.append({"x": round(x, 1), "y": round(y, 1), "label": f"{hhmm}  {p['price']:.0f}"})

    prev_close_y = None
    if prev_close is not None:
        _, prev_close_y = xy(0, prev_close)
        prev_close_y = round(prev_close_y, 1)

    latest = points[-1]
    is_rise = (latest.get("price") or 0) >= (prev_close or 0)

    return {
        "width": width,
        "height": height,
        "polyline": " ".join(coords),
        "prev_close_y": prev_close_y,
        "prev_close": prev_close,
        "dots": dots,
        # only label first/last per "selective direct labels, never every point"
        "first_dot": dots[0] if dots else None,
        "last_dot": dots[-1] if dots else None,
        "is_rise": is_rise,
    }


def _empty_pressplay_section():
    return {"raw_tokens": [], "matched": [], "unmatched": []}


def _fmt_lots(shares):
    """Shares -> 張(lots) display string, matching how every other table
    on this page shows volume (site's raw JSON is in shares; /1000)."""
    if shares is None:
        return "—"
    return f"{shares / 1000.0:,.0f}"


def _fmt_net_lots(shares):
    if shares is None:
        return "—"
    lots = shares / 1000.0
    sign = "+" if lots >= 0 else ""
    return f"{sign}{lots:,.0f}"


def _fmt_broker_price(p):
    if p is None:
        return "—"
    return f"{p:g}"


def _fmt_broker_rows(entries, kind):
    """Raw chengwaye buyers/sellers/daytraders entries -> display-ready
    row dicts (all formatting done here, not in the template)."""
    out = []
    for e in entries or []:
        row = {
            "name": (e.get("name") or "").strip(),
            "buyV": _fmt_lots(e.get("buyV")),
            "buyP": _fmt_broker_price(e.get("buyP")),
            "sellV": _fmt_lots(e.get("sellV")),
            "sellP": _fmt_broker_price(e.get("sellP")),
        }
        if kind == "daytraders":
            row["total"] = _fmt_lots(e.get("total"))
        else:
            row["net"] = _fmt_net_lots(e.get("net"))
        out.append(row)
    return out


def build_institutional_section(pressplay, chengwaye_daily, stock_history=None):
    """
    Part 3 extra: per-stock 法人買賣Top15／當沖Top10 detail, for every
    stock already shown in Part 3 (found_group.matched + not_found_group.
    matched, i.e. "顯示在盤前文章的標的") that also has data in chengwaye.
    com/daily's same-day 28-stock list. Stocks without a data match are
    silently skipped (not shown as "no data") -- this is the scope the
    user confirmed. See fetch_chengwaye_daily.py's module docstring for
    why there is no 總損益 (day-trade P&L) field: it isn't in the source
    data, and this deliberately never estimates one.
    """
    codes_data = (chengwaye_daily or {}).get("codes") or {}
    history_data = (stock_history or {}).get("codes") or {}
    if not codes_data:
        return {
            "stocks": [],
            "stocks_by_code": {},
            "candidate_count": 0,
            "matched_count": 0,
            "page_date": None,
        }

    candidates = []
    seen_codes = set()
    for row in (
        (pressplay.get("not_found_group", {}).get("matched") or [])
        + (pressplay.get("found_group", {}).get("matched") or [])
    ):
        code = (row.get("code") or "").replace("⏸", "").strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        candidates.append({**row, "code": code})

    items = []
    for row in candidates:
        cw = codes_data.get(row.get("code"))
        if not cw:
            continue
        buyers = cw.get("buyers") or []
        sellers = cw.get("sellers") or []
        daytraders = cw.get("daytraders") or []
        items.append({
            "code": row.get("code"),
            "name": row.get("name") or cw.get("name") or row.get("code"),
            "market": row.get("market"),
            "foreign": row.get("foreign"),
            "trust": row.get("trust"),
            "dealer": row.get("dealer"),
            "buyers": _fmt_broker_rows(buyers[:15], "buyers"),
            "sellers": _fmt_broker_rows(sellers[:15], "sellers"),
            "daytraders": _fmt_broker_rows(daytraders[:10], "daytraders"),
            "limit_up_history": history_data.get(row.get("code")),
        })

    return {
        "stocks": items,
        "stocks_by_code": {item["code"]: item for item in items},
        "candidate_count": len(candidates),
        "matched_count": len(items),
        "page_date": (chengwaye_daily or {}).get("page_date"),
    }


def build_calendar_grid(today_str, range_end_str, events):
    """
    Part 4: a real Sun-Sat weekly grid (padded to full weeks) covering
    [today, range_end], for an at-a-glance calendar view sitting above the
    detailed agenda list. Cells only carry a day number + event-count dots
    -- a 7-column cell is far too narrow for Chinese-language event titles
    -- and link to that day's spot in the agenda list below via a
    same-page #cal-YYYY-MM-DD anchor (plain HTML anchor scroll, no JS,
    consistent with the rest of this static page).
    """
    if not today_str or not range_end_str:
        return None
    today = date.fromisoformat(today_str)
    range_end = date.fromisoformat(range_end_str)

    by_date = {}
    for ev in events:
        by_date.setdefault(ev["date"], []).append(ev)

    def sunday_of_week(d):
        return d - timedelta(days=(d.weekday() + 1) % 7)  # weekday(): Mon=0..Sun=6

    grid_start = sunday_of_week(today)
    grid_end = sunday_of_week(range_end) + timedelta(days=6)

    days = []
    d = grid_start
    while d <= grid_end:
        iso = d.isoformat()
        in_range = today <= d <= range_end
        days.append({
            "date": iso,
            "day": d.day,
            # month label on the 1st (so a grid crossing a month boundary
            # is legible) and on the very first cell (so the grid's own
            # starting month is never ambiguous).
            "month_label": f"{d.month}/{d.day}" if (d.day == 1 or d == grid_start) else None,
            "is_today": d == today,
            "in_range": in_range,
            "count": len(by_date.get(iso, [])) if in_range else 0,
        })
        d += timedelta(days=1)

    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    return {"weekday_labels": ["日", "一", "二", "三", "四", "五", "六"], "weeks": weeks}


def load_json(path):
    """Defensive loader: a fetch step that failed partway (e.g. the disposal
    date-check abort) can leave behind a missing or empty/truncated file.
    Treat any of that as "no data" rather than crashing the whole page build
    -- the template already renders sensible empty states."""
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"WARNING: {path} is not valid JSON, treating as empty", file=__import__("sys").stderr)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indices", required=True)
    ap.add_argument("--night-session", required=True)
    ap.add_argument("--disposal", required=True)
    ap.add_argument(
        "--pressplay", default=None,
        help="optional: Part 3 PressPlay group-list JSON; omitted/missing/empty renders an empty Part 3 state",
    )
    ap.add_argument(
        "--chengwaye-daily", default=None,
        help="optional: Part 3 extra -- chengwaye.com/daily 法人買賣/當沖 detail JSON; "
             "omitted/missing/empty just skips this sub-section",
    )
    ap.add_argument(
        "--stock-history", default=None,
        help="optional: Chengwaye per-stock limit-up history JSON; missing entries render a fallback card",
    )
    ap.add_argument(
        "--calendar", default=None,
        help="optional: Part 4 financial calendar JSON (fetch_calendar.py); "
        "omitted/missing/empty renders an empty Part 4 state",
    )
    ap.add_argument("--financials", required=False, help="Path to financials.json")
    ap.add_argument("--news", required=False, help="Path to news.json")
    ap.add_argument("--ai-summary", required=False, help="Optional path to ai_summary.json")
    ap.add_argument("--twse-summary", required=False, help="Path to twse_summary.json")
    ap.add_argument("--source-status", required=False, default=None, help="Path to source_status.json")
    ap.add_argument("--data-date", required=False, default=None, help="Optional data date override (e.g. 08/24)")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--template-dir",
        default=str(Path(__file__).parent / "templates"),
    )
    args = ap.parse_args()

    # Single Source of Truth for Build Timestamp & Version
    now = datetime.now(TAIPEI)
    build_time_str = now.strftime("%Y-%m-%d %H:%M")
    build_time_hm = now.strftime("%H:%M")
    build_version = now.strftime("%Y%m%d_%H%M")
    generated_at_str = now.strftime("%Y/%m/%d %H:%M")

    indices = normalize_indices(load_json(args.indices) or {}) or {}
    night = load_json(args.night_session) or {}
    disposal = load_json(args.disposal) or {}
    pressplay_raw = load_json(args.pressplay) or {}

    if not pressplay_raw:
        pressplay = {
            "source_article": {},
            "chengwaye_date": None,
            "not_found_group": _empty_pressplay_section(),
            "found_group": _empty_pressplay_section(),
            "_status": "fetch_failed"
        }
    else:
        pressplay = {
            "source_article": pressplay_raw.get("source_article") or {},
            "chengwaye_date": pressplay_raw.get("chengwaye_date"),
            "not_found_group": pressplay_raw.get("not_found_group") or _empty_pressplay_section(),
            "found_group": pressplay_raw.get("found_group") or _empty_pressplay_section(),
            "_status": pressplay_raw.get("_status", "ok"),
        }

    spark = build_sparkline(night.get("points") or [])

    chengwaye_daily = load_json(args.chengwaye_daily) or {}
    stock_history = load_json(args.stock_history) or {}
    institutional = build_institutional_section(pressplay, chengwaye_daily, stock_history)

    calendar_raw = load_json(args.calendar) or {}
    financials_data = load_json(args.financials) if args.financials else {}
    news_data = load_json(args.news) if args.news else []
    ai_summary_data = load_json(args.ai_summary) if args.ai_summary else {}
    twse_data = load_json(args.twse_summary) if args.twse_summary else {} or {}
    cal_events = calendar_raw.get("events") or []
    cal_today = calendar_raw.get("today") or now.strftime("%Y-%m-%d")
    calendar_section = {
        "today": cal_today,
        "range_end": calendar_raw.get("range_end"),
        "events": cal_events,
        "date_groups": prepare_calendar_timeline(cal_events, cal_today),
    }
    calendar_section["grid"] = build_calendar_grid(
        calendar_section["today"], calendar_section["range_end"], calendar_section["events"]
    )

    # Determine data_date from single authority
    if args.data_date and args.data_date.strip():
        data_date = args.data_date.strip()
    else:
        page_applies = (disposal.get("date_check", {}) or {}).get("page_says_applies_to")
        if page_applies:
            data_date = page_applies
        else:
            raw_d = (disposal.get("date_check", {}) or {}).get("today") or night.get("date") or now.strftime("%Y-%m-%d")
            if len(raw_d) == 10 and raw_d[4] == '-' and raw_d[7] == '-':
                data_date = raw_d[5:].replace('-', '/')
            else:
                data_date = raw_d
    
    # Calculate hours since last US close (US 16:00 EDT == 04:00 Taipei next day)
    us_close_today = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now < us_close_today:
        us_close_today -= timedelta(days=1)
    hours_since_us_close = round((now - us_close_today).total_seconds() / 3600, 1)
    us_close_at_iso = us_close_today.isoformat()

    us_market_context = build_us_market_context(now, indices)
    asia_market_context = {
        symbol: build_asia_market_context(
            now,
            symbol,
            (indices.get("asia_open", {}) or {}).get(symbol),
        )
        for symbol in ("^N225", "^KS11")
    }

    # Calculate data stale hours
    data_dt_str = (night.get("latest") or {}).get("collected_at")
    if data_dt_str:
        try:
            data_dt = datetime.fromisoformat(data_dt_str)
            stale_hours = round((now - data_dt).total_seconds() / 3600, 1)
        except Exception:
            stale_hours = 0.0
    else:
        stale_hours = 0.0

    stale_hours = max(0.0, stale_hours)

    # Health & Credibility Evaluation
    status_file_path = args.source_status or (Path("data") / "latest" / "source_status.json")
    status_json = load_json(status_file_path)
    date_check_eval = evaluate_date_check(now.date(), (disposal.get("date_check", {}) or {}).get("page_says_applies_to"))
    health_eval = evaluate_source_health(status_json, date_check_eval)

    meta_path = Path(args.out).parent / "data_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    
    meta_data = {
        "build_time": build_time_str,
        "build_version": build_version,
        "data_date": data_date,
        "stale_hours": stale_hours,
        "hours_since_us_close": hours_since_us_close,
        "us_market_context": us_market_context,
        "overall_status": health_eval.overall_status,
        "status_label": health_eval.status_label,
        "status_badge_class": health_eval.status_badge_class,
        "summary_reasons": health_eval.summary_reasons,
        "sources": health_eval.sources,
    }
    meta_data = write_packages(
        meta_path.parent,
        indices=indices,
        night=night,
        disposal=disposal,
        pressplay=pressplay,
        chengwaye_daily=chengwaye_daily,
        calendar=calendar_section,
        financials=financials_data or {},
        news=news_data,
        ai_summary=ai_summary_data or {},
        twse=twse_data,
        meta=meta_data,
        stock_history=stock_history,
    )
    meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Tie the runtime cache to both the build and the exact package hashes.
    # This prevents a new index from reusing an old JSON package after a
    # successful deployment, while network-first still keeps live data fresh.
    sw_path = Path(args.out).parent / "sw.js"
    if sw_path.exists():
        import re
        data_revision = str(meta_data.get("data_revision") or build_version)
        sw_content = sw_path.read_text(encoding="utf-8")
        sw_content = re.sub(
            r"const CACHE_NAME = '[^']+';",
            f"const CACHE_NAME = 'pmit-{build_version}-data-{data_revision}';",
            sw_content,
        )
        sw_content = re.sub(r"const DATA_REVISION = '[^']+';", f"const DATA_REVISION = '{data_revision}';", sw_content)
        sw_path.write_text(sw_content, encoding="utf-8")
        print(f"updated {sw_path} cache name to pmit-{build_version}-data-{data_revision}")

    env = Environment(loader=FileSystemLoader(args.template_dir), autoescape=True)
    tmpl = env.get_template("premarket.html.j2")

    html = tmpl.render(
        generated_at=generated_at_str,
        build_time=build_time_hm,
        build_version=build_version,
        data_date=data_date,
        stale_hours=stale_hours,
        hours_since_us_close=hours_since_us_close,
        us_close_at_iso=us_close_at_iso,
        us_market_context=us_market_context,
        asia_market_context=asia_market_context,
        meta=meta_data,
        health=health_eval.to_dict(),
        indices=indices,
        us_indices=indices.get("us_indices", {}),
        asia_open=indices.get("asia_open", {}),
        indices_missing=indices.get("_missing_fields", []),
        night=night,
        spark=spark,
        disposal=disposal,
        date_check=disposal.get("date_check", {}),
        date_check_eval=date_check_eval,
        pressplay=pressplay,
        institutional=institutional,
        calendar=calendar_section,
        financials=financials_data,
        news=news_data,
        ai_summary=ai_summary_data or {},
        twse=twse_data,
        twse_holidays_list=sorted(list(load_twse_holidays())),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
