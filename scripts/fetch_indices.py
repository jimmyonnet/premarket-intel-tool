#!/usr/bin/env python3
"""
Part 1 data source: previous-night US four major indices + Nikkei225 + KOSPI.

Sources (verified live during design, see /fixtures for saved samples):
  - https://tw.stock.yahoo.com/markets/       -> Dow, S&P500, Nasdaq, SOX, Nikkei225 (+HSI, unused)
  - https://tw.stock.yahoo.com/world-indices  -> KOSPI (韓國綜合指數) + everything above again

Both pages are server-side rendered: the numbers are present in the raw HTML
response before any JavaScript runs (verified via `fetch(location.href)` on
the live page and checking the raw response text). That means a plain
`requests.get()` is enough here -- no headless browser needed for Part 1's
index data.

Parsing strategy: flatten the page to visible text with BeautifulSoup's
`get_text()`, then run line/regex-based extraction anchored on the Chinese
index names. This is deliberately NOT based on CSS class names -- Yahoo's
class names are auto-generated/obfuscated and will drift; the Chinese labels
("道瓊工業指數" etc.) are the stable anchor.

Usage:
    python fetch_indices.py [--fixture-dir DIR] > indices.json

If --fixture-dir is given, reads local fixture files instead of hitting the
network (used for offline testing; see /fixtures).
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9",
}

MARKETS_URL = "https://tw.stock.yahoo.com/markets/"
WORLD_INDICES_URL = "https://tw.stock.yahoo.com/world-indices"

# name -> (chinese label, output key)
MARKETS_TARGETS = [
    ("道瓊工業指數", "dow"),
    ("S&P 500指數", "sp500"),
    ("NASDAQ指數", "nasdaq"),
    ("費城半導體指數", "sox"),
    ("日經225指數", "nikkei225"),
]

WORLD_INDICES_TARGETS = [
    ("韓國綜合指數", "kospi"),
    ("日經225指數", "nikkei225"),
]


def get_text(html: str) -> str:
    """Flatten HTML to visible text, one text node per line."""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n")
    # Extremely rough fallback if bs4 isn't installed: strip tags naively.
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return text


def parse_markets_block(text: str, targets):
    """
    Pattern (markets page, after get_text -- blank lines collapse but order
    is preserved):
        道瓊工業指數
        53,463.05
        119.65(0.22%)
    """
    results = {}
    for label, key in targets:
        # Find the label, then look ahead (within a short window) for a
        # "value" line followed by a "change(change%)" line.
        m = re.search(
            re.escape(label)
            + r"\s*\n+\s*([\d,]+\.\d+)\s*\n+\s*(-?[\d,]+\.\d+)\(([\-\d.]+)%\)",
            text,
        )
        if not m:
            continue
        value, change, change_pct = m.groups()
        results[key] = {
            "name": label,
            "value": float(value.replace(",", "")),
            "change": float(change.replace(",", "")),
            "change_pct": float(change_pct),
        }
    return results


def parse_world_indices_block(text: str, targets):
    """
    Pattern (world-indices page, per row, after get_text):
        韓國綜合指數
        ^KS11
        6,852.58        <- value
        381.41          <- change
        5.89%           <- change%
        6,680.34        <- bid/buy (ignored)
        6,471.17        <- ask/sell (ignored)
        6,904.55        <- open (ignored, columns vary by row)
        6,600.09        <- prior close (ignored)
        301,744         <- volume (ignored)
        08/20 14:32     <- timestamp (CST) <-- captured
    """
    results = {}
    for label, key in targets:
        m = re.search(
            re.escape(label)
            + r"\s*\n+\s*\^?[\w.]*\s*\n+\s*([\d,]+\.\d+)\s*\n+\s*(-?[\d,]+\.\d+)\s*\n+\s*([\-\d.]+)%",
            text,
        )
        if not m:
            continue
        value, change, change_pct = m.groups()
        entry = {
            "name": label,
            "value": float(value.replace(",", "")),
            "change": float(change.replace(",", "")),
            "change_pct": float(change_pct),
        }
        # Best-effort: grab the first "MM/DD HH:MM" timestamp after the match.
        tail = text[m.end(): m.end() + 400]
        ts = re.search(r"(\d{2}/\d{2}\s+\d{2}:\d{2})", tail)
        if ts:
            entry["updated_cst"] = ts.group(1)
        results[key] = entry
    return results


def fetch(url: str, fixture_path: Path = None) -> str:
    if fixture_path is not None:
        return fixture_path.read_text(encoding="utf-8")
    if requests is None:
        raise RuntimeError("requests is not installed and no fixture was given")
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fixture-dir",
        type=Path,
        default=None,
        help="Read from local fixture files instead of the network (offline test mode).",
    )
    args = ap.parse_args()

    if args.fixture_dir:
        markets_html = fetch(MARKETS_URL, args.fixture_dir / "yahoo_markets.md")
        world_html = fetch(WORLD_INDICES_URL, args.fixture_dir / "yahoo_world_indices.md")
        # Fixtures are already flattened markdown/text, not raw HTML.
        markets_text = markets_html
        world_text = world_html
    else:
        markets_html = fetch(MARKETS_URL)
        world_html = fetch(WORLD_INDICES_URL)
        markets_text = get_text(markets_html)
        world_text = get_text(world_html)

    us_indices = parse_markets_block(markets_text, MARKETS_TARGETS)
    world_indices = parse_world_indices_block(world_text, WORLD_INDICES_TARGETS)

    # Nikkei appears on both pages; prefer the world-indices one since it
    # carries a per-row timestamp, fall back to markets page.
    nikkei = world_indices.get("nikkei225") or us_indices.get("nikkei225")

    out = {
        "source": {
            "markets": MARKETS_URL,
            "world_indices": WORLD_INDICES_URL,
        },
        "us_indices": {
            "dow": us_indices.get("dow"),
            "sp500": us_indices.get("sp500"),
            "nasdaq": us_indices.get("nasdaq"),
            "sox": us_indices.get("sox"),
        },
        "asia_open": {
            "nikkei225": nikkei,
            "kospi": world_indices.get("kospi"),
        },
    }

    missing = [k for k, v in out["us_indices"].items() if v is None]
    missing += [k for k, v in out["asia_open"].items() if v is None]
    out["_missing_fields"] = missing
    if missing:
        print(f"WARNING: could not parse fields: {missing}", file=sys.stderr)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
