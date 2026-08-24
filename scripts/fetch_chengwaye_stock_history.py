#!/usr/bin/env python3
"""Fetch hard limit-up history from Chengwaye per-stock pages.

The source page is a server-rendered HTML document at
https://chengwaye.com/stock/{code}.  We intentionally parse only the
summary metrics and the visible "漲停紀錄" table; no browser automation or
client-side scraping is required.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

try:
    import requests
except ImportError:  # pragma: no cover - covered by fixture mode in tests
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - dependency is in requirements.txt
    BeautifulSoup = None

TAIPEI = timezone(timedelta(hours=8))
BASE_URL = "https://chengwaye.com/stock/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def clean_code(value: Any) -> str:
    text = str(value or "").replace("⏸", "").strip()
    return text if re.fullmatch(r"\d{4,5}", text) else ""


def collect_codes(pressplay_payload: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for group_key in ("not_found_group", "found_group"):
        group = pressplay_payload.get(group_key) or {}
        for row in group.get("matched") or []:
            code = clean_code((row or {}).get("code"))
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def fetch_html(code: str, fixture_dir: Path | None = None) -> str:
    if fixture_dir is not None:
        candidates = (fixture_dir / f"{code}.html", fixture_dir / f"chengwaye_stock_{code}.html")
        for path in candidates:
            if path.exists():
                return path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"fixture not found for stock {code}")
    if requests is None:
        raise RuntimeError("requests not installed and no fixture directory supplied")
    response = requests.get(urljoin(BASE_URL, code), headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def _cell_text(cell: Any) -> str:
    return " ".join(cell.stripped_strings).strip() if cell is not None else ""


def _metric_map(soup: Any) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for metric in soup.select(".metric"):
        label = _cell_text(metric.find("span"))
        value = _cell_text(metric.find("strong"))
        if label:
            metrics[label] = value
    return metrics


def _parse_records(soup: Any) -> list[dict[str, str]]:
    heading = next((h for h in soup.find_all(["h2", "h3"]) if "漲停紀錄" in _cell_text(h)), None)
    table = heading.find_next("table") if heading is not None else None
    if table is None:
        return []
    headers = [_cell_text(cell) for cell in table.select("thead th")]
    key_map = {
        "漲停日": "date",
        "收盤": "close",
        "AI 族群": "group",
        "隔日開盤": "next_open",
        "隔日均價": "next_avg",
        "隔日收盤": "next_close",
        "隔日走勢": "next_trend",
    }
    records: list[dict[str, str]] = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) != len(headers):
            continue
        record: dict[str, str] = {}
        for header, cell in zip(headers, cells):
            key = key_map.get(header)
            if key:
                record[key] = _cell_text(cell)
        if record.get("date"):
            records.append(record)
    return records


def parse_stock_page(html: str, code: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required")
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    heading_text = _cell_text(heading)
    name = re.sub(rf"\s*{re.escape(code)}\s*$", "", heading_text).strip() or code
    subtitle = _cell_text(soup.select_one(".hero-subtitle"))
    metrics = _metric_map(soup)
    records = _parse_records(soup)
    if not records:
        raise ValueError(f"no 漲停紀錄 table found for {code}")
    summary = {
        "limit_up_count": metrics.get("漲停次數", "—"),
        "latest_limit_up": metrics.get("最近漲停", "—"),
        "avg_next_open": metrics.get("隔日平均開盤", "—"),
        "avg_next_close": metrics.get("隔日平均收盤", "—"),
    }
    return {
        "code": code,
        "name": name,
        "source_url": urljoin(BASE_URL, code),
        "summary": summary,
        "records": records,
        "period_note": subtitle,
        "record_count": len(records),
    }


def fetch_one(code: str, fixture_dir: Path | None = None) -> tuple[str, dict[str, Any] | None, str | None]:
    try:
        return code, parse_stock_page(fetch_html(code, fixture_dir), code), None
    except Exception as exc:  # one stock must not abort all other candidates
        return code, None, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Chengwaye per-stock limit-up history")
    parser.add_argument("--pressplay", type=Path, required=True, help="pressplay.json containing matched candidate codes")
    parser.add_argument("--fixture-dir", type=Path, default=None, help="offline directory with {code}.html fixtures")
    parser.add_argument("--max-codes", type=int, default=80, help="maximum candidate pages per run")
    args = parser.parse_args()

    if BeautifulSoup is None:
        print("ERROR: beautifulsoup4 is required", file=sys.stderr)
        raise SystemExit(2)

    pressplay = json.loads(args.pressplay.read_text(encoding="utf-8")) if args.pressplay.exists() else {}
    codes = collect_codes(pressplay)[: max(0, args.max_codes)]
    fetched: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []

    # A small bounded pool keeps the run fast without hammering the source.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(codes)))) as pool:
        futures = [pool.submit(fetch_one, code, args.fixture_dir) for code in codes]
        for future in futures:
            code, payload, error = future.result()
            if payload is not None:
                fetched[code] = payload
            else:
                failures.append({"code": code, "error": error or "unknown error"})

    result = {
        "source": BASE_URL,
        "fetched_at": datetime.now(TAIPEI).isoformat(),
        "requested_codes": codes,
        "codes": {code: fetched[code] for code in codes if code in fetched},
        "failed_codes": failures,
        "_status": "ok" if not failures else ("partial" if fetched else "fetch_failed"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
