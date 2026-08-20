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

IMPORTANT EXCEPTION, found via live verification (2026-08-20): the rise/fall
SIGN is not one of them. Yahoo renders a falling index as a bare unsigned
number ("254.24", no "-", no arrow character in the text) styled with the
CSS class `C($c-trend-down)`; a rising one gets the same bare-number
treatment styled `C($c-trend-up)`. The direction is conveyed ONLY by that
class (and by a triangle icon that isn't part of the DOM text at all) --
there is no text-only way to recover it. So `change`/`change_pct` DO depend
on one CSS class lookup (see `trend_sign()`), the one deliberate exception
to the "no class names" rule above. This was caught because the shipped
page showed 費城半導體指數 as +2.12% when the live site had it falling
(green, per this project's TW convention) at -2.12%; see README.

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


def find_card(soup, label: str):
    """Return the nearest ancestor of `label`'s text node whose markup also
    contains a trend-direction class (c-trend-up / c-trend-down) -- i.e. the
    card/row that carries both the label and its rise/fall styling. Walks
    upward from the label so it works across the two DOM layouts confirmed
    live (card-based <a> elements on the markets page, list-based <li> rows
    on world-indices), without needing to know the exact tag structure.

    Returns None if `soup` is None (fixture/offline mode -- fixtures are
    pre-flattened text with no HTML structure to search) or nothing is found.
    """
    if soup is None:
        return None
    node = soup.find(string=lambda s: s and label in s)
    if node is None:
        return None
    ancestor = node.parent
    depth = 0
    while ancestor is not None and depth < 12:
        html = str(ancestor)
        if "c-trend-down" in html or "c-trend-up" in html:
            return ancestor
        ancestor = ancestor.parent
        depth += 1
    return None


def trend_sign(container) -> int:
    """-1 if `container`'s markup carries the falling-trend class, else +1.

    Covers rising and unknown/no-signal cases as +1 (no sign flip), since
    the regex-extracted magnitude is already unsigned/non-negative -- see
    the module docstring for why this class lookup is necessary at all.
    """
    if container is None:
        return 1
    if "c-trend-down" in str(container):
        return -1
    return 1


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


def parse_markets_block(text: str, targets, soup=None):
    """
    Pattern (markets page, after get_text -- blank lines collapse but order
    is preserved). Confirmed against the live site (2026-08-20): change and
    (change%) render as two SEPARATE text nodes/lines, not one "119.65
    (0.22%)" run -- the original regex required them adjacent with no
    whitespace and silently matched nothing as a result.
        道瓊工業指數
        53,463.05
        119.65
        (0.22%)

    `soup` (optional): the parsed HTML of the same page, used ONLY to look
    up the rise/fall sign via `trend_sign(find_card(...))` -- see the module
    docstring. When soup is None (fixture/offline mode), change/change_pct
    are left exactly as regex-extracted (unsigned), matching prior behavior.
    """
    results = {}
    for label, key in targets:
        # Find the label, then look ahead (within a short window) for a
        # "value" line followed by a "change" line followed by a "(change%)"
        # line -- allow whitespace/newlines between change and its "(...%)",
        # since the live page puts them on separate lines.
        m = re.search(
            re.escape(label)
            + r"\s*\n+\s*([\d,]+\.\d+)\s*\n+\s*(-?[\d,]+\.\d+)\s*\(([\-\d.]+)%\)",
            text,
        )
        if not m:
            continue
        value, change, change_pct = m.groups()
        change_f = float(change.replace(",", ""))
        change_pct_f = float(change_pct)
        if soup is not None:
            sign = trend_sign(find_card(soup, label))
            change_f = abs(change_f) * sign
            change_pct_f = abs(change_pct_f) * sign
        results[key] = {
            "name": label,
            "value": float(value.replace(",", "")),
            "change": change_f,
            "change_pct": change_pct_f,
        }
    return results


def parse_world_indices_block(text: str, targets, soup=None):
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

    `soup` (optional): see `parse_markets_block` -- same sign-lookup deal.
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
        change_f = float(change.replace(",", ""))
        change_pct_f = float(change_pct)
        if soup is not None:
            sign = trend_sign(find_card(soup, label))
            change_f = abs(change_f) * sign
            change_pct_f = abs(change_pct_f) * sign
        entry = {
            "name": label,
            "value": float(value.replace(",", "")),
            "change": change_f,
            "change_pct": change_pct_f,
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

    markets_soup = None
    world_soup = None
    if args.fixture_dir:
        markets_html = fetch(MARKETS_URL, args.fixture_dir / "yahoo_markets.md")
        world_html = fetch(WORLD_INDICES_URL, args.fixture_dir / "yahoo_world_indices.md")
        # Fixtures are already flattened markdown/text, not raw HTML -- no
        # structure to build a soup from, so the rise/fall sign lookup is
        # skipped in fixture mode (see parse_markets_block docstring; this
        # is an accepted gap in offline fixture testing, documented in
        # README's known-limitations section).
        markets_text = markets_html
        world_text = world_html
    else:
        markets_html = fetch(MARKETS_URL)
        world_html = fetch(WORLD_INDICES_URL)
        markets_text = get_text(markets_html)
        world_text = get_text(world_html)
        if BeautifulSoup is not None:
            markets_soup = BeautifulSoup(markets_html, "html.parser")
            world_soup = BeautifulSoup(world_html, "html.parser")

    us_indices = parse_markets_block(markets_text, MARKETS_TARGETS, soup=markets_soup)
    world_indices = parse_world_indices_block(world_text, WORLD_INDICES_TARGETS, soup=world_soup)

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
