#!/usr/bin/env python3
"""
Archives today's raw/processed data into history/YYYY-MM-DD.json.
Uses Taipei timezone to determine today's trading/calendar date.
Zero external dependencies (uses standard library only).
"""
import os
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))

def archive_daily_data(data_dir: str = "data/latest", history_dir: str = "history", date_override: str = None) -> str:
    now = datetime.now(TAIPEI)
    date_str = date_override or now.strftime("%Y-%m-%d")
    
    src_path = Path(data_dir)
    dst_dir = Path(history_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    
    archive_file = dst_dir / f"{date_str}.json"
    
    combined = {
        "archived_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "data_date": date_str,
        "sources": {}
    }
    
    if src_path.exists():
        for json_file in src_path.glob("*.json"):
            try:
                combined["sources"][json_file.stem] = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as e:
                combined["sources"][json_file.stem] = {"error": str(e)}
    
    # Also include meta if available
    meta_path = Path("docs/data_meta.json")
    if meta_path.exists():
        try:
            combined["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    archive_file.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Archived daily snapshot to {archive_file} ({archive_file.stat().st_size} bytes)")
    return str(archive_file)

if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else None
    archive_daily_data(date_override=d)
