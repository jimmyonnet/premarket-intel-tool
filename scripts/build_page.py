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
        --out ../docs/index.html
"""
import argparse
import json
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
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--template-dir",
        default=str(Path(__file__).parent / "templates"),
    )
    args = ap.parse_args()

    indices = load_json(args.indices) or {}
    night = load_json(args.night_session) or {}
    disposal = load_json(args.disposal) or {}

    spark = build_sparkline(night.get("points") or [])

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
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
