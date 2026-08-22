#!/usr/bin/env python3
"""
Assembles the final morning page (docs/index.html) from the three data
sources' JSON output:
  - indices.json    (fetch_indices.py)
  - night_session.json (tx_night_session.py assemble)
  - disposal.json   (fetch_disposal.py)

Design language reused verbatim from the existing 覆盤準備台.html tool:
Taiwan convention colors (red = 漲/rise, green = 跌/fall -- opposite of US),
dark panel UI, monospace for numbers. See CSS in the template for the token
list.

Usage:
    python build_page.py \
        --indices indices.json \
        --night-session night_session.json \
        --disposal disposal.json \
        --pressplay pressplay.json \
        --out ../docs/index.html

Note on --pressplay (Part 3): unlike the other three sources, this arg is
OPTIONAL and defaults to None. fetch_pressplay_groups.py's login step can
fail for real reasons outside our control (see that script's KNOWN RISK
docstring) -- when it does, the workflow writes an empty {} instead of
aborting, and this script must render a clean empty state rather than
crashing the whole page build over a missing Part 3 section. See
_empty_pressplay_section() / the pressplay dict built in main() below: the
template is only ever handed a fully-populated structure, never a bare {}
or missing key, specifically to avoid a Jinja2 Undefined chained-attribute
crash (confirmed locally: `{{ data.missing_key.sub_key }}` raises
UndefinedError even though `{{ data.missing_key }}` alone does not).
"""
import argparse
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TAIPEI = timezone(timedelta(hours=8))


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


def build_institutional_section(pressplay, chengwaye_daily):
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
    if not codes_data:
        return {"stocks": [], "candidate_count": 0, "matched_count": 0, "page_date": None}

    candidates = []
    seen_codes = set()
    for row in (
        (pressplay.get("not_found_group", {}).get("matched") or [])
        + (pressplay.get("found_group", {}).get("matched") or [])
    ):
        code = row.get("code")
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        candidates.append(row)

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
        })

    return {
        "stocks": items,
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
        "--calendar", default=None,
        help="optional: Part 4 financial calendar JSON (fetch_calendar.py); "
        "omitted/missing/empty renders an empty Part 4 state",
    )
    ap.add_argument("--financials", required=False, help="Path to financials.json")
    ap.add_argument("--news", required=False, help="Path to news.json")
    ap.add_argument("--twse-summary", required=False, help="Path to twse_summary.json")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--template-dir",
        default=str(Path(__file__).parent / "templates"),
    )
    args = ap.parse_args()

    indices = load_json(args.indices) or {}
    night = load_json(args.night_session) or {}
    disposal = load_json(args.disposal) or {}
    pressplay_raw = load_json(args.pressplay) or {}
    # Fully pre-default every nested key the template touches -- see the
    # module docstring's note on --pressplay for why this can't be left to
    # the template's own `or {}` fallbacks.
    pressplay = {
        "source_article": pressplay_raw.get("source_article") or {},
        "chengwaye_date": pressplay_raw.get("chengwaye_date"),
        "not_found_group": pressplay_raw.get("not_found_group") or _empty_pressplay_section(),
        "found_group": pressplay_raw.get("found_group") or _empty_pressplay_section(),
    }

    spark = build_sparkline(night.get("points") or [])

    chengwaye_daily = load_json(args.chengwaye_daily) or {}
    institutional = build_institutional_section(pressplay, chengwaye_daily)

    calendar_raw = load_json(args.calendar)
    financials_data = load_json(args.financials) if args.financials else {}
    news_data = load_json(args.news) if args.news else []
    twse_data = load_json(args.twse_summary) if args.twse_summary else {} or {}
    calendar_section = {
        "today": calendar_raw.get("today"),
        "range_end": calendar_raw.get("range_end"),
        "events": calendar_raw.get("events") or [],
    }
    calendar_section["grid"] = build_calendar_grid(
        calendar_section["today"], calendar_section["range_end"], calendar_section["events"]
    )

    now = datetime.now(TAIPEI)

    # Calculate data_date, stale_hours and hours_since_us_close
    data_date = disposal.get("date_check", {}).get("today") or night.get("date") or now.strftime("%Y-%m-%d")
    
    # Calculate hours since last US close (US 16:00 EDT == 04:00 Taipei next day)
    us_close_today = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now < us_close_today:
        us_close_today -= timedelta(days=1)
    hours_since_us_close = round((now - us_close_today).total_seconds() / 3600, 1)

    # Calculate data stale hours
    data_dt_str = (night.get("latest") or {}).get("collected_at")
    if data_dt_str:
        try:
            data_dt = datetime.fromisoformat(data_dt_str)
            stale_hours = round((now - data_dt).total_seconds() / 3600, 1)
        except Exception:
            stale_hours = 0
    else:
        stale_hours = 0

    stale_hours = max(0, stale_hours)
    build_time = now.strftime("%H:%M")

    # Write data_meta.json
    meta_path = Path(args.out).parent / "data_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_data = {
        "build_time": now.isoformat(),
        "data_date": data_date,
        "stale_hours": stale_hours,
        "hours_since_us_close": hours_since_us_close,
    }
    meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")

    env = Environment(loader=FileSystemLoader(args.template_dir), autoescape=True)
    tmpl = env.get_template("premarket.html.j2")

    html = tmpl.render(
        generated_at=now.strftime("%Y/%m/%d %H:%M"),
        build_time=build_time,
        data_date=data_date,
        stale_hours=stale_hours,
        hours_since_us_close=hours_since_us_close,
        indices=indices,
        us_indices=indices.get("us_indices", {}),
        asia_open=indices.get("asia_open", {}),
        indices_missing=indices.get("_missing_fields", []),
        night=night,
        spark=spark,
        disposal=disposal,
        date_check=disposal.get("date_check", {}),
        pressplay=pressplay,
        institutional=institutional,
        calendar=calendar_section,
        financials=financials_data,
        news=news_data,
        twse=twse_data,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
