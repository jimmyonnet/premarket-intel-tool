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
import math
from datetime import datetime, timezone, timedelta
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


def _nice_step(span, target_ticks=4):
    """Round gridline step (1/2/2.5/5 x 10^n) for an axis spanning `span`
    with roughly `target_ticks` gridlines. Standard "nice numbers" pick,
    used for the bubble chart's price axis."""
    if span <= 0:
        return 1.0
    raw = span / target_ticks
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = mag * m
        if step >= raw:
            return step
    return mag * 10


def _volume_ticks(max_lots, target=4):
    """Round tick values (1/2/5 x 10^n, e.g. 20/50/100/200) below
    max_lots for the bubble chart's diverging volume axis -- same visual
    grammar as the source site's axis (coarse round numbers, denser near
    the center), adaptive per stock since traded volume varies a lot
    stock to stock. Returns the largest `target` candidates so the ticks
    shown are close to the actual data's scale."""
    if max_lots <= 1:
        return [1] if max_lots > 0 else []
    candidates = []
    scale = 1
    while scale <= max_lots:
        for b in (1, 2, 5):
            v = b * scale
            if v <= max_lots:
                candidates.append(v)
        scale *= 10
    candidates = sorted(set(candidates))
    return candidates[-target:] if len(candidates) > target else candidates


def _declutter(items, label_clearance=18):
    """1D vertical collision avoidance for stacked bubbles + their labels.

    Sort by cy, then push down any bubble whose center is close enough
    to the previous one that either (a) their circles would overlap, or
    (b) this bubble's above-bubble name label would overlap the previous
    bubble's circle. Liquid, high-volume stocks often have several
    brokers within a few cents of each other -- true average-price
    positions would stack their bubbles/labels into unreadable soup, so
    positions are nudged apart while keeping the same top-to-bottom (=
    high-to-low price) order. This is the standard "beeswarm" tradeoff:
    vertical position is approximate-but-legible, not pixel-exact
    against the price axis -- the real average price is still in the
    table directly below every chart, and each bubble's exact figures
    are in its hover tooltip.
    """
    items = sorted(items, key=lambda b: b["cy"])
    for i in range(1, len(items)):
        min_cy = items[i - 1]["cy"] + items[i - 1]["r"] + items[i]["r"] + label_clearance
        if items[i]["cy"] < min_cy:
            items[i]["cy"] = min_cy
    return items


def build_bubble_chart(buyers, sellers, max_each=10, width=680, height=300):
    """
    Diverging 買超/賣超 bubble chart (Part 3 extra section): buy-side (red)
    bubbles left of a center axis, sell-side (green) right of it, sized
    sqrt(net)-scaled like before, but now placed on two REAL, gridlined
    axes instead of an artificial rank grid:
      - Y = the broker's average price (buyP / sellP) -- shared with a
        left-hand price scale + horizontal gridlines (nudged apart when
        crowded -- see _declutter_and_stagger).
      - X = sqrt(|net| lots)-scaled distance from center -- mirrored,
        with vertical gridlines labelled at round lot values (e.g.
        20/50/100/200), read outward from 0 like the source site's axis.
      - Each bubble's exact broker/net/price is in an SVG hover tooltip
        (<title>); only the name is a permanent on-chart label, matching
        how the source site's chart itself only labels names (its exact
        figures are hover-only there too).

    This is a from-scratch SVG rebuild off visual inspection of the
    source site's per-stock chart, not a pixel clone: that chart is a
    <canvas> (confirmed via DOM inspection, 2026-08-21 -- no SVG/DOM
    structure to read values back out of), and it plots against the
    stock's full 平盤→漲停 band, which needs prev-close + limit-price
    data this pipeline doesn't fetch. Deliberately skipped for the same
    reason as that band: the source's faint decorative spoke/leader
    lines fanning out from center (no data-bearing purpose visible on
    inspection).

    buyers/sellers are raw chengwaye entries (buyV/sellV/net in SHARES,
    buyP/sellP are per-broker avg prices); entries missing a price are
    dropped (can't be placed on the Y axis). Only the first `max_each` of
    each (already sorted by |net| descending by the source) are plotted
    to keep a static SVG legible -- full top-15 lists are in the tables
    below. All geometry computed here so the template stays dumb (same
    pattern as build_sparkline above).
    """
    buyers = (buyers or [])[:max_each]
    sellers = (sellers or [])[:max_each]

    def lots(shares):
        return (shares or 0) / 1000.0

    b_pts, s_pts = [], []
    for b in buyers:
        price, net = b.get("buyP"), lots(b.get("net"))
        if price is None or net <= 0:
            continue
        b_pts.append((net, price, (b.get("name") or "").strip()))
    for s in sellers:
        price, net = s.get("sellP"), lots(s.get("net"))
        if price is None or net >= 0:
            continue
        s_pts.append((abs(net), price, (s.get("name") or "").strip()))

    if not b_pts and not s_pts:
        return None

    all_pts = b_pts + s_pts
    prices = [p for _, p, _ in all_pts]
    max_vol = max(v for v, _, _ in all_pts)
    lo, hi = min(prices), max(prices)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.15
    lo -= pad
    hi += pad

    pad_l, pad_r, pad_t, pad_b = 44, 12, 18, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    cx0 = pad_l + plot_w / 2
    plot_half = plot_w / 2 - 6
    plot_top, plot_bottom = pad_t, height - pad_b

    def y_of(price):
        return plot_top + plot_h * (1 - (price - lo) / (hi - lo))

    def x_off(v):
        return ((v / max_vol) ** 0.5) * plot_half if max_vol > 0 else 0.0

    r_min, r_max = 6, 18

    def make_bubble(v, price, name, side):
        off = x_off(v)
        cx = cx0 - off if side == "buy" else cx0 + off
        r = r_min + (r_max - r_min) * ((v / max_vol) ** 0.5 if max_vol > 0 else 0.0)
        sign = "+" if side == "buy" else "-"
        return {
            "cx": round(cx, 1),
            "cy": round(y_of(price), 1),
            "r": round(r, 1),
            "side": side,
            "name": name[:6],
            "title_text": f"{name}　{sign}{v:,.0f} 張｜均價 {price:g}",
        }

    buy_bubbles = _declutter([make_bubble(v, p, n, "buy") for v, p, n in b_pts])
    sell_bubbles = _declutter([make_bubble(v, p, n, "sell") for v, p, n in s_pts])
    bubbles = buy_bubbles + sell_bubbles

    # Decluttering (above) can push a bubble's cy past the original
    # plot_bottom when many brokers cluster at nearly the same price --
    # extend the canvas downward to fit rather than clipping it or
    # rescaling the whole price axis. The price/volume SCALES computed
    # above (y_of/x_off) are left untouched; only the bottom margin grows.
    label_room = 4  # a little breathing room below the lowest bubble
    max_extent = max((b["cy"] + b["r"] for b in bubbles), default=plot_bottom)
    if max_extent + label_room > plot_bottom:
        plot_bottom = max_extent + label_room
        height = round(plot_bottom + pad_b, 1)

    for b in bubbles:
        b["cx"] = round(b["cx"], 1)
        b["cy"] = round(b["cy"], 1)

    step = _nice_step(hi - lo)
    price_lines = []
    t = math.ceil(lo / step) * step
    while t <= hi + 1e-9:
        price_lines.append({"y": round(y_of(t), 1), "label": f"{t:g}"})
        t += step

    volume_lines = []
    for v in _volume_ticks(max_vol):
        off = x_off(v)
        volume_lines.append({"x": round(cx0 - off, 1), "label": f"{v:g}"})
        volume_lines.append({"x": round(cx0 + off, 1), "label": f"{v:g}"})

    return {
        "width": width,
        "height": height,
        "center_x": round(cx0, 1),
        "plot_top": plot_top,
        "plot_bottom": round(plot_bottom, 1),
        "axis_label_y": round(height - 6, 1),
        "bubbles": bubbles,
        "price_lines": price_lines,
        "volume_lines": volume_lines,
    }


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
            "bubble": build_bubble_chart(buyers, sellers),
        })

    return {
        "stocks": items,
        "candidate_count": len(candidates),
        "matched_count": len(items),
        "page_date": (chengwaye_daily or {}).get("page_date"),
    }


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

    now = datetime.now(TAIPEI)

    env = Environment(loader=FileSystemLoader(args.template_dir), autoescape=True)
    tmpl = env.get_template("premarket.html.j2")

    html = tmpl.render(
        generated_at=now.strftime("%Y/%m/%d %H:%M"),
        us_indices=indices.get("us_indices", {}),
        asia_open=indices.get("asia_open", {}),
        indices_missing=indices.get("_missing_fields", []),
        night=night,
        spark=spark,
        disposal=disposal,
        date_check=disposal.get("date_check", {}),
        pressplay=pressplay,
        institutional=institutional,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
