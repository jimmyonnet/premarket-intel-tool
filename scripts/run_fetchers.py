#!/usr/bin/env python3
"""
Unified data fetch runner for Premarket Intel Tool.
Executes individual fetchers, captures errors, provides safe fallbacks,
and maintains an audit-ready data/latest/source_status.json file.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from source_status import (
    SOURCES_METADATA,
    SourceItem,
    evaluate_source_health,
    save_source_status,
)

TAIPEI = timezone(timedelta(hours=8))
DATA_LATEST = Path(__file__).parent.parent / "data" / "latest"


def run_command(cmd: list[str], env: dict[str, str] | None = None, timeout: int = 60) -> tuple[int, str, str]:
    """Runs a shell command and returns (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env or os.environ.copy(),
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


def fetch_source(
    source_id: str,
    cmd: list[str],
    target_file: Path,
    fallback_content: str,
    timeout: int = 45,
    env: dict[str, str] | None = None,
    extract_date_fn: Any = None,
) -> dict[str, Any]:
    """Executes fetch command for a specific source and writes result & status dict."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TAIPEI)
    now_iso = now.isoformat()

    print(f"[Fetch] Starting {source_id} -> {target_file.name}...")
    exit_code, stdout, stderr = run_command(cmd, env=env, timeout=timeout)

    fallback_used = False
    status = "ok"
    error_summary = None
    data_date = None

    if exit_code != 0:
        print(f"[Fetch Error] {source_id} failed with code {exit_code}: {stderr[:200]}", file=sys.stderr)
        status = "failed"
        fallback_used = True
        error_summary = f"指令執行失敗 (code {exit_code})"
        if not target_file.exists() or target_file.stat().st_size == 0:
            target_file.write_text(fallback_content, encoding="utf-8")
    else:
        # If script wrote output to stdout instead of directly to target_file
        if stdout.strip() and (not target_file.exists() or target_file.stat().st_size == 0 or ">" in " ".join(cmd)):
            try:
                # Validate JSON stdout
                parsed = json.loads(stdout)
                target_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                target_file.write_text(stdout, encoding="utf-8")

        # Validate target file exists and is valid JSON
        if not target_file.exists() or target_file.stat().st_size == 0:
            target_file.write_text(fallback_content, encoding="utf-8")
            status = "failed"
            fallback_used = True
            error_summary = "產出檔案為空"
        else:
            try:
                content = json.loads(target_file.read_text(encoding="utf-8"))
                # Check for special internal status flags
                if isinstance(content, dict):
                    if content.get("is_fallback") or (content.get("latest") or {}).get("is_fallback"):
                        fallback_used = True
                    if content.get("_status") == "fetch_failed":
                        status = "failed"
                        fallback_used = True
                        error_summary = content.get("_error", "登入或來源抓取失敗")
                    elif extract_date_fn:
                        data_date = extract_date_fn(content)
            except Exception as e:
                status = "failed"
                fallback_used = True
                error_summary = f"JSON 解析失敗: {str(e)[:100]}"
                target_file.write_text(fallback_content, encoding="utf-8")

    meta = SOURCES_METADATA.get(source_id, {"name": source_id, "is_required": False, "impact_desc": ""})

    return {
        "source_id": source_id,
        "name": meta["name"],
        "is_required": meta["is_required"],
        "status": status,
        "fetched_at": now_iso,
        "data_date": data_date,
        "age_minutes": 0.0,
        "error_summary": error_summary,
        "fallback_used": fallback_used,
        "impact_desc": meta["impact_desc"],
    }


def inspect_existing_source_file(source_id: str, file_path: Path) -> dict[str, Any] | None:
    """If source is already present on disk, construct a valid status map entry."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None
    try:
        content = json.loads(file_path.read_text(encoding="utf-8"))
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=TAIPEI)
        age_minutes = max(0.0, (datetime.now(TAIPEI) - mtime).total_seconds() / 60.0)
        
        fallback_used = False
        data_date = None
        status = "ok"
        error_summary = None

        if isinstance(content, dict):
            if content.get("is_fallback") or (content.get("latest") or {}).get("is_fallback"):
                fallback_used = True
            if content.get("_status") == "fetch_failed":
                status = "failed"
                fallback_used = True
                error_summary = content.get("_error", "前次抓取失敗")
            data_date = content.get("date") or content.get("page_date") or (content.get("date_check") or {}).get("page_says_applies_to") or content.get("today")

        meta = SOURCES_METADATA.get(source_id, {"name": source_id, "is_required": False, "impact_desc": ""})
        return {
            "source_id": source_id,
            "name": meta["name"],
            "is_required": meta["is_required"],
            "status": status,
            "fetched_at": mtime.isoformat(),
            "data_date": data_date,
            "age_minutes": round(age_minutes, 1),
            "error_summary": error_summary,
            "fallback_used": fallback_used,
            "impact_desc": meta["impact_desc"],
        }
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Premarket Intel Tool Fetch Runner")
    parser.add_argument("--mode", choices=["full", "asia-open-update"], default="full")
    parser.add_argument("--date", help="Today's date (YYYY-MM-DD)", default=None)
    parser.add_argument("--allow-unsafe-exit", action="store_true", help="Do not exit with code 1 even if unsafe")
    args = parser.parse_args()

    today_str = args.date or datetime.now(TAIPEI).strftime("%Y-%m-%d")
    DATA_LATEST.mkdir(parents=True, exist_ok=True)

    # Load existing status if updating partially
    existing_status_file = DATA_LATEST / "source_status.json"
    status_map: dict[str, Any] = {}
    if existing_status_file.exists():
        try:
            status_map = json.loads(existing_status_file.read_text(encoding="utf-8")).get("sources", {})
        except Exception:
            status_map = {}

    # File mapping for all sources
    source_file_map = {
        "twse_summary": DATA_LATEST / "twse_summary.json",
        "indices": DATA_LATEST / "indices.json",
        "night_session": DATA_LATEST / "night_session.json",
        "disposal": DATA_LATEST / "disposal.json",
        "pressplay": DATA_LATEST / "pressplay.json",
        "chengwaye_daily": DATA_LATEST / "chengwaye_daily.json",
        "calendar": DATA_LATEST / "calendar.json",
        "financials": DATA_LATEST / "financials.json",
        "news": DATA_LATEST / "news.json",
    }

    # Pre-fill status for sources present on disk
    for sid, fpath in source_file_map.items():
        if sid not in status_map:
            item = inspect_existing_source_file(sid, fpath)
            if item:
                status_map[sid] = item

    python_bin = sys.executable

    if args.mode == "full":
        # 1. TWSE Summary
        status_map["twse_summary"] = fetch_source(
            "twse_summary",
            [python_bin, "scripts/fetch_twse_summary.py"],
            DATA_LATEST / "twse_summary.json",
            "{}",
            timeout=30,
        )

        # 2. Indices
        status_map["indices"] = fetch_source(
            "indices",
            [python_bin, "scripts/fetch_indices.py"],
            DATA_LATEST / "indices.json",
            "{}",
            timeout=35,
        )

        # 3. Night session
        status_map["night_session"] = fetch_source(
            "night_session",
            [python_bin, "scripts/tx_night_session.py", "assemble", "--data-dir", "data/night_session", "--date", today_str],
            DATA_LATEST / "night_session.json",
            "{}",
            timeout=30,
            extract_date_fn=lambda c: c.get("date"),
        )

        # 4. Disposal forecast
        status_map["disposal"] = fetch_source(
            "disposal",
            [python_bin, "scripts/fetch_disposal.py", "--skip-date-check"],
            DATA_LATEST / "disposal.json",
            "{}",
            timeout=40,
            extract_date_fn=lambda c: (c.get("date_check") or {}).get("page_says_applies_to"),
        )

        # 5. PressPlay
        status_map["pressplay"] = fetch_source(
            "pressplay",
            [python_bin, "scripts/fetch_pressplay_groups.py"],
            DATA_LATEST / "pressplay.json",
            "{}",
            timeout=50,
            extract_date_fn=lambda c: c.get("chengwaye_date"),
        )

        # 6. Chengwaye Daily detail
        status_map["chengwaye_daily"] = fetch_source(
            "chengwaye_daily",
            [python_bin, "scripts/fetch_chengwaye_daily.py"],
            DATA_LATEST / "chengwaye_daily.json",
            "{}",
            timeout=40,
            extract_date_fn=lambda c: c.get("page_date"),
        )

        # 7. Financial Calendar
        status_map["calendar"] = fetch_source(
            "calendar",
            [python_bin, "scripts/fetch_calendar.py"],
            DATA_LATEST / "calendar.json",
            "{}",
            timeout=30,
            extract_date_fn=lambda c: c.get("today"),
        )

        # 8. Financials announcements + Embeds build
        status_map["financials"] = fetch_source(
            "financials",
            [python_bin, "scripts/fetch_financials.py"],
            DATA_LATEST / "financials.json",
            "{}",
            timeout=30,
        )
        # Always build embeds
        run_command([python_bin, "scripts/build_embeds.py"], timeout=30)

        # 9. News
        status_map["news"] = fetch_source(
            "news",
            [python_bin, "scripts/fetch_news.py"],
            DATA_LATEST / "news.json",
            "[]",
            timeout=30,
        )

    elif args.mode == "asia-open-update":
        print("[Fetch] Updating indices (Asia market open refresh)...")
        status_map["indices"] = fetch_source(
            "indices",
            [python_bin, "scripts/fetch_indices.py"],
            DATA_LATEST / "indices.json",
            "{}",
            timeout=35,
        )

    # Save consolidated source status JSON
    save_source_status(status_map)

    # Evaluate readiness
    eval_result = evaluate_source_health({"sources": status_map})
    print("\n==========================================")
    print(f"PAGE READINESS: {eval_result.overall_status.upper()} ({eval_result.status_label})")
    print("Reasons / Alerts:")
    for r in eval_result.summary_reasons:
        print(f" - {r}")
    print("==========================================\n")

    if eval_result.overall_status == "unsafe" and not args.allow_unsafe_exit:
        print("CRITICAL: One or more required sources failed! Marked as UNSAFE.", file=sys.stderr)
        # We allow workflow to build diagnostic page, but exit with failure if required
        sys.exit(1)


if __name__ == "__main__":
    main()
