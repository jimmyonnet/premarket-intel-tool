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
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    from source_status import (
        SOURCES_METADATA,
        SourceItem,
        evaluate_source_health,
        save_source_status,
    )
except ModuleNotFoundError:  # Support package-style imports in test runners.
    from scripts.source_status import (
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
    max_attempts: int = 3,
    retry_delay_seconds: int = 30,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Fetch one source with bounded retries and a safe previous-snapshot fallback."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TAIPEI)
    now_iso = now.isoformat()
    previous_signature = None
    previous_content = None
    if target_file.exists():
        previous_signature = (target_file.stat().st_mtime_ns, target_file.stat().st_size)
        if target_file.stat().st_size > 0:
            cached_bytes = target_file.read_bytes()
            try:
                json.loads(cached_bytes.decode("utf-8"))
                previous_content = cached_bytes
            except (UnicodeDecodeError, json.JSONDecodeError):
                print(f"[Fetch Cache] {source_id} previous snapshot is invalid and will not be reused.", file=sys.stderr)

    print(f"[Fetch] Starting {source_id} -> {target_file.name}...")
    attempts = max(1, max_attempts)
    exit_code = 1
    stdout = ""
    stderr = ""
    attempt = 0
    for attempt in range(1, attempts + 1):
        exit_code, stdout, stderr = run_command(cmd, env=env, timeout=timeout)
        if exit_code == 0:
            break
        if attempt < attempts:
            print(
                f"[Fetch Retry] {source_id} attempt {attempt}/{attempts} failed; "
                f"retrying in {retry_delay_seconds}s...",
                file=sys.stderr,
            )
            sleep_fn(retry_delay_seconds)
    retry_attempts = max(0, attempt - 1)

    fallback_used = False
    status = "ok"
    error_summary = None
    data_date = None

    if exit_code != 0:
        print(f"[Fetch Error] {source_id} failed with code {exit_code}: {stderr[:200]}", file=sys.stderr)
        fallback_used = True
        error_summary = f"重試 {attempt} 次後指令執行失敗 (code {exit_code})"
        if previous_content is not None:
            target_file.write_bytes(previous_content)
            status = "warning"
        else:
            status = "failed"
            target_file.write_text(fallback_content, encoding="utf-8")
    else:
        # If script wrote output to stdout, update target_file
        if stdout.strip():
            try:
                # Validate JSON stdout
                parsed = json.loads(stdout)
                target_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                target_file.write_text(stdout, encoding="utf-8")
        else:
            current_signature = (target_file.stat().st_mtime_ns, target_file.stat().st_size) if target_file.exists() else None
            if previous_signature is not None and current_signature == previous_signature:
                status = "warning"
                fallback_used = True
                error_summary = "指令成功但未產生新資料，沿用前次快照"

        # Validate target file exists and is valid JSON
        if not target_file.exists() or target_file.stat().st_size == 0:
            fallback_used = True
            error_summary = "產出檔案為空"
            if previous_content is not None:
                target_file.write_bytes(previous_content)
                status = "warning"
            else:
                target_file.write_text(fallback_content, encoding="utf-8")
                status = "failed"
        else:
            try:
                content = json.loads(target_file.read_text(encoding="utf-8"))
                # Check for special internal status flags
                if isinstance(content, dict):
                    if content.get("is_fallback") or (content.get("latest") or {}).get("is_fallback"):
                        fallback_used = True
                    if content.get("_status") == "fetch_failed":
                        fallback_used = True
                        error_summary = content.get("_error", "登入或來源抓取失敗")
                        if previous_content is not None:
                            target_file.write_bytes(previous_content)
                            status = "warning"
                        else:
                            status = "failed"
                    elif extract_date_fn:
                        data_date = extract_date_fn(content)
            except Exception as e:
                fallback_used = True
                error_summary = f"JSON 解析失敗: {str(e)[:100]}"
                if previous_content is not None:
                    target_file.write_bytes(previous_content)
                    status = "warning"
                else:
                    target_file.write_text(fallback_content, encoding="utf-8")
                    status = "failed"

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
        "retry_attempts": retry_attempts,
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
            "retry_attempts": 0,
            "impact_desc": meta["impact_desc"],
        }
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Premarket Intel Tool Fetch Runner")
    parser.add_argument(
        "--mode",
        choices=["full", "morning-core", "asia-open-update", "disposal", "candidates", "financials"],
        default="full",
        help="full is used for manual updates; scheduled modes refresh only their named page section.",
    )
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
        "chengwaye_stock_history": DATA_LATEST / "stock_history.json",
        "calendar": DATA_LATEST / "calendar.json",
        "financials": DATA_LATEST / "financials.json",
        "news": DATA_LATEST / "news.json",
    }

    # Pre-fill status for sources present on disk. On a partial refresh, keep
    # the prior fetch outcome but recalculate every untouched source's age from
    # its actual file modification time, so the page never reports old data as
    # freshly fetched merely because a different section was refreshed.
    for sid, fpath in source_file_map.items():
        item = inspect_existing_source_file(sid, fpath)
        if item:
            if sid not in status_map:
                status_map[sid] = item
            else:
                status_map[sid]["age_minutes"] = item["age_minutes"]

    python_bin = sys.executable

    if args.mode in ("full", "morning-core"):
        # Morning market context: yesterday's Taiwan close, overnight futures,
        # macro calendar and overnight news.
        status_map["twse_summary"] = fetch_source(
            "twse_summary",
            [python_bin, "scripts/fetch_twse_summary.py"],
            DATA_LATEST / "twse_summary.json",
            "{}",
            timeout=30,
        )

        status_map["night_session"] = fetch_source(
            "night_session",
            [python_bin, "scripts/tx_night_session.py", "assemble", "--data-dir", "data/night_session", "--date", today_str],
            DATA_LATEST / "night_session.json",
            "{}",
            timeout=30,
            extract_date_fn=lambda c: c.get("date"),
        )
        status_map["calendar"] = fetch_source(
            "calendar",
            [python_bin, "scripts/fetch_calendar.py"],
            DATA_LATEST / "calendar.json",
            "{}",
            timeout=30,
            extract_date_fn=lambda c: c.get("today"),
        )
        status_map["news"] = fetch_source(
            "news",
            [python_bin, "scripts/fetch_news.py"],
            DATA_LATEST / "news.json",
            "[]",
            timeout=30,
        )

    if args.mode in ("full", "morning-core", "asia-open-update"):
        # Broad indices are refreshed in the morning and again around the
        # Japan/Korea open; the latter mode intentionally leaves other data
        # sources untouched.
        status_map["indices"] = fetch_source(
            "indices",
            [python_bin, "scripts/fetch_indices.py"],
            DATA_LATEST / "indices.json",
            "{}",
            timeout=35,
        )

    if args.mode in ("full", "disposal"):
        # Chengwaye publishes the forecast for the next trading day at about
        # 19:30 Taipei time. The scheduled workflow gives it a five-minute
        # buffer before fetching this source.
        status_map["disposal"] = fetch_source(
            "disposal",
            [python_bin, "scripts/fetch_disposal.py", "--skip-date-check"],
            DATA_LATEST / "disposal.json",
            "{}",
            timeout=40,
            extract_date_fn=lambda c: (c.get("date_check") or {}).get("page_says_applies_to"),
        )

    if args.mode in ("full", "candidates", "morning-core"):
        # Candidate stocks combine the PressPlay premarket article with the
        # Chengwaye daily institutional / day-trading detail.
        status_map["pressplay"] = fetch_source(
            "pressplay",
            [python_bin, "scripts/fetch_pressplay_groups.py"],
            DATA_LATEST / "pressplay.json",
            "{}",
            timeout=50,
            extract_date_fn=lambda c: c.get("chengwaye_date"),
        )

        status_map["chengwaye_daily"] = fetch_source(
            "chengwaye_daily",
            [python_bin, "scripts/fetch_chengwaye_daily.py"],
            DATA_LATEST / "chengwaye_daily.json",
            "{}",
            timeout=40,
            extract_date_fn=lambda c: c.get("page_date"),
        )

        status_map["chengwaye_stock_history"] = fetch_source(
            "chengwaye_stock_history",
            [python_bin, "scripts/fetch_chengwaye_stock_history.py", "--pressplay", str(DATA_LATEST / "pressplay.json")],
            DATA_LATEST / "stock_history.json",
            '{"source":"https://chengwaye.com/stock/","codes":{},"failed_codes":[],"_status":"fetch_failed"}',
            timeout=120,
            extract_date_fn=lambda c: c.get("fetched_at"),
        )

    if args.mode in ("full", "financials"):
        # Post-market self-reported earnings, financials and revenue notices.
        status_map["financials"] = fetch_source(
            "financials",
            [python_bin, "scripts/fetch_financials.py"],
            DATA_LATEST / "financials.json",
            '{"att":[],"fin":[],"rev":[]}',
            timeout=150,
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
