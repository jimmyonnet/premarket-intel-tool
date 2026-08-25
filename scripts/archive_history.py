#!/usr/bin/env python3
"""Archive the latest data snapshot and prune old history files.

Archives today's raw/processed data into ``history/YYYY-MM-DD.json`` and keeps
only a bounded number of days by default.  The retention policy is explicit so
scheduled builds cannot silently grow the repository forever.
"""

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_RETENTION_DAYS = 60


def prune_history(history_dir: str | Path = "history", *, today: str, retain_days: int = DEFAULT_RETENTION_DAYS) -> list[str]:
    """Delete dated JSON archives older than the inclusive retention window."""
    if retain_days < 1:
        raise ValueError("retain_days must be at least 1")
    root = Path(history_dir)
    if not root.exists():
        return []
    try:
        today_date = datetime.strptime(today, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("today must use YYYY-MM-DD") from exc

    removed: list[str] = []
    for archive in root.glob("????-??-??.json"):
        try:
            archive_date = datetime.strptime(archive.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        age_days = (today_date - archive_date).days
        if age_days >= retain_days:
            archive.unlink()
            removed.append(str(archive))
    return removed


def archive_daily_data(
    data_dir: str = "data/latest",
    history_dir: str = "history",
    date_override: str | None = None,
    retain_days: int = DEFAULT_RETENTION_DAYS,
) -> str:
    now = datetime.now(TAIPEI)
    date_str = date_override or now.strftime("%Y-%m-%d")

    src_path = Path(data_dir)
    dst_dir = Path(history_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    archive_file = dst_dir / f"{date_str}.json"

    combined = {
        "archived_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "data_date": date_str,
        "retention_days": retain_days,
        "sources": {},
    }

    if src_path.exists():
        for json_file in src_path.glob("*.json"):
            try:
                combined["sources"][json_file.stem] = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                combined["sources"][json_file.stem] = {"error": str(exc)}

    meta_path = Path("docs/data_meta.json")
    if meta_path.exists():
        try:
            combined["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    archive_file.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    removed = prune_history(dst_dir, today=date_str, retain_days=retain_days)
    print(f"Archived daily snapshot to {archive_file} ({archive_file.stat().st_size} bytes)")
    if removed:
        print(f"Pruned {len(removed)} history archive(s) older than {retain_days} days")
    return str(archive_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive premarket data and prune old history")
    parser.add_argument("date", nargs="?", help="archive date override (YYYY-MM-DD)")
    parser.add_argument("--data-dir", default="data/latest")
    parser.add_argument("--history-dir", default="history")
    parser.add_argument("--retain-days", type=int, default=DEFAULT_RETENTION_DAYS)
    args = parser.parse_args()
    archive_daily_data(args.data_dir, args.history_dir, args.date, args.retain_days)
