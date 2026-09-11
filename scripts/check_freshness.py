#!/usr/bin/env python3
"""
Premarket Intel Tool - Published artifact freshness watchdog.

A workflow that fails loudly is easy to notice; one that stops running is not.
This checks the published data package against the market date it should carry,
so a silently stalled pipeline surfaces as a failed run instead of a page that
quietly keeps saying "今日尚未產生預測".

Zero external dependencies (standard library only).
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))

# Published artifacts that must carry the current market date, as
# (path relative to the docs directory, name of the date field).
DAILY_ARTIFACTS = (
    ("data/opening_forecast.json", "market_date"),
    ("data/opening_result.json", "market_date"),
)


def check_artifacts(docs_dir: Path, market_date: date) -> list[str]:
    """Return one message per stale or unreadable artifact; empty means fresh."""
    expected = market_date.isoformat()
    problems: list[str] = []

    for relative_path, date_field in DAILY_ARTIFACTS:
        path = Path(docs_dir) / relative_path
        if not path.exists():
            problems.append(f"{relative_path} 不存在（預期 {date_field}={expected}）")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            problems.append(f"{relative_path} 無法讀取或解析：{exc}")
            continue
        if not isinstance(payload, dict):
            problems.append(f"{relative_path} 頂層不是物件，無法讀取 {date_field}")
            continue

        actual = payload.get(date_field)
        if not actual:
            problems.append(f"{relative_path} 缺少 {date_field} 欄位（預期 {expected}）")
        elif actual != expected:
            problems.append(f"{relative_path} 的 {date_field}={actual}，但今日應為 {expected}")

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Published artifact freshness watchdog")
    parser.add_argument("--docs-dir", default="docs", help="Published package directory")
    parser.add_argument(
        "--market-date",
        default=None,
        help="ISO market date the package should carry (default: today in Taipei)",
    )
    args = parser.parse_args()

    market_date = (
        date.fromisoformat(args.market_date)
        if args.market_date
        else datetime.now(TAIPEI).date()
    )

    problems = check_artifacts(Path(args.docs_dir), market_date)
    if not problems:
        print(f"資料新鮮度正常：所有每日產出物都標記為 {market_date.isoformat()}")
        return

    for problem in problems:
        print(f"::error::資料新鮮度異常：{problem}", file=sys.stderr)
    print(
        f"{len(problems)} 個每日產出物未更新到 {market_date.isoformat()}，"
        "請檢查 generate-opening-forecast 與 verify-opening-result 的執行紀錄。",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
