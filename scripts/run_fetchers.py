#!/usr/bin/env python3
"""Reliable, dependency-aware data fetch runner for Premarket Intel Tool."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from source_status import (
        SOURCES_METADATA,
        SourceItem,
        evaluate_source_health,
        save_source_status,
        source_policy,
    )
except ModuleNotFoundError:
    from scripts.source_status import (
        SOURCES_METADATA,
        SourceItem,
        evaluate_source_health,
        save_source_status,
        source_policy,
    )

TAIPEI = timezone(timedelta(hours=8))
DATA_LATEST = Path(__file__).parent.parent / "data" / "latest"


@dataclass(frozen=True)
class FetchTask:
    """One graph node.  Dependencies are source IDs, not implementation order."""

    source_id: str
    command: list[str]
    target_file: Path
    fallback_content: str
    timeout: int = 45
    extract_date_fn: Any = None
    dependencies: tuple[str, ...] = ()
    modes: tuple[str, ...] = ("full",)
    max_attempts: int = 3
    retry_delay_seconds: int = 30


@dataclass
class TaskGraphResult:
    statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)


def pressplay_fallback_info(content: Any) -> tuple[bool, str | None]:
    """Return whether a PressPlay payload is not from the live browser fetch."""
    if not isinstance(content, dict):
        return False, None
    article = content.get("source_article") or {}
    if not isinstance(article, dict):
        return False, None
    mode = article.get("fetch_mode")
    if mode == "live_browser":
        return False, None
    labels = {
        "fallback_cache": "PressPlay 登入抓取失敗，沿用當日快取文章",
        "fallback_fixture": "PressPlay 登入抓取失敗，沿用備援 fixture 文章",
        "manual_override": "使用手動提供的 PressPlay 文章覆寫",
        "fixture": "使用離線 fixture PressPlay 文章",
        "no_credentials": "未設定 PressPlay 登入憑證",
        "fallback_empty": "PressPlay 登入抓取失敗且沒有可用文章",
    }
    if mode in labels:
        return True, labels[mode]
    if article.get("fixture"):
        return True, "PressPlay 文章來自快取或 fixture，未確認為即時登入抓取"
    return False, None


def run_command(cmd: list[str], env: dict[str, str] | None = None, timeout: int = 60) -> tuple[int, str, str]:
    """Run a subprocess and return (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=timeout, env=env or os.environ.copy(), check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


def _safe_json_bytes(path: Path) -> bytes | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        raw = path.read_bytes()
        json.loads(raw.decode("utf-8"))
        return raw
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


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
    """Fetch one source with bounded retries and safe previous-snapshot fallback."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(TAIPEI).isoformat()
    previous_signature = None
    previous_content = _safe_json_bytes(target_file)
    if target_file.exists():
        previous_signature = (target_file.stat().st_mtime_ns, target_file.stat().st_size)
        if previous_content is None and target_file.stat().st_size > 0:
            print(f"[Fetch Cache] {source_id} previous snapshot is invalid and will not be reused.", file=sys.stderr)

    print(f"[Fetch] Starting {source_id} -> {target_file.name}...")
    attempts = max(1, max_attempts)
    exit_code, stdout, stderr, attempt = 1, "", "", 0
    for attempt in range(1, attempts + 1):
        exit_code, stdout, stderr = run_command(cmd, env=env, timeout=timeout)
        if exit_code == 0:
            break
        if attempt < attempts:
            print(f"[Fetch Retry] {source_id} attempt {attempt}/{attempts} failed; retrying in {retry_delay_seconds}s...", file=sys.stderr)
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
        if stdout.strip():
            try:
                parsed = json.loads(stdout)
                target_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except (TypeError, ValueError):
                target_file.write_text(stdout, encoding="utf-8")
        else:
            current_signature = (target_file.stat().st_mtime_ns, target_file.stat().st_size) if target_file.exists() else None
            if previous_signature is not None and current_signature == previous_signature:
                status = "warning"
                fallback_used = True
                error_summary = "指令成功但未產生新資料，沿用前次快照"

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
                if isinstance(content, dict):
                    if content.get("is_fallback") or (content.get("latest") or {}).get("is_fallback"):
                        fallback_used = True
                    if source_id == "pressplay":
                        pp_fallback, pp_reason = pressplay_fallback_info(content)
                        if pp_fallback:
                            fallback_used = True
                            status = "warning"
                            error_summary = content.get("source_article", {}).get("fallback_reason") or pp_reason
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
                elif extract_date_fn:
                    data_date = extract_date_fn(content)
            except Exception as exc:
                fallback_used = True
                error_summary = f"JSON 解析失敗: {str(exc)[:100]}"
                if previous_content is not None:
                    target_file.write_bytes(previous_content)
                    status = "warning"
                else:
                    target_file.write_text(fallback_content, encoding="utf-8")
                    status = "failed"

    meta = source_policy(source_id)
    notification = None
    if fallback_used or status in ("failed", "warning"):
        notification = f"{meta['notification_level']}: {error_summary or '使用備援資料'}"
    return {
        "source_id": source_id,
        "name": meta["name"],
        "is_required": meta["is_required"],
        "reliability_tier": meta["reliability_tier"],
        "ttl_minutes": meta["ttl_minutes"],
        "hard_expiry_minutes": meta["hard_expiry_minutes"],
        "fallback_policy": meta["fallback_policy"],
        "notification_level": meta["notification_level"],
        "dependencies": list(meta.get("dependencies", [])),
        "status": status,
        "fetched_at": now_iso,
        "data_date": data_date,
        "age_minutes": 0.0,
        "error_summary": error_summary,
        "fallback_used": fallback_used,
        "retry_attempts": retry_attempts,
        "impact_desc": meta["impact_desc"],
        "notification": notification,
    }


def inspect_existing_source_file(source_id: str, file_path: Path) -> dict[str, Any] | None:
    """Construct a status entry for an existing on-disk snapshot."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None
    try:
        content = json.loads(file_path.read_text(encoding="utf-8"))
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=TAIPEI)
        age_minutes = max(0.0, (datetime.now(TAIPEI) - mtime).total_seconds() / 60.0)
        fallback_used = False
        status = "ok"
        error_summary = None
        data_date = None
        if isinstance(content, dict):
            if content.get("is_fallback") or (content.get("latest") or {}).get("is_fallback"):
                fallback_used = True
            if source_id == "pressplay":
                pp_fallback, pp_reason = pressplay_fallback_info(content)
                if pp_fallback:
                    fallback_used = True
                    status = "warning"
                    error_summary = content.get("source_article", {}).get("fallback_reason") or pp_reason
            if content.get("_status") == "fetch_failed":
                status, fallback_used = "failed", True
                error_summary = content.get("_error", "前次抓取失敗")
            data_date = content.get("date") or content.get("page_date") or (content.get("date_check") or {}).get("page_says_applies_to") or content.get("today")
        meta = source_policy(source_id)
        return {
            "source_id": source_id, "name": meta["name"], "is_required": meta["is_required"],
            "reliability_tier": meta["reliability_tier"], "ttl_minutes": meta["ttl_minutes"],
            "hard_expiry_minutes": meta["hard_expiry_minutes"], "fallback_policy": meta["fallback_policy"],
            "notification_level": meta["notification_level"], "dependencies": list(meta.get("dependencies", [])),
            "status": status, "fetched_at": mtime.isoformat(), "data_date": data_date,
            "age_minutes": round(age_minutes, 1), "error_summary": error_summary,
            "fallback_used": fallback_used, "retry_attempts": 0, "impact_desc": meta["impact_desc"],
            "notification": None,
        }
    except Exception:
        return None


def task_is_fresh(source_id: str, file_path: Path, now: datetime | None = None) -> bool:
    """Return whether an existing snapshot is within its source TTL."""
    if not file_path.exists() or file_path.stat().st_size <= 0:
        return False
    current = now or datetime.now(TAIPEI)
    age_minutes = max(0.0, (current - datetime.fromtimestamp(file_path.stat().st_mtime, tz=TAIPEI)).total_seconds() / 60.0)
    return age_minutes <= int(source_policy(source_id)["ttl_minutes"])


def _task_catalog(python_bin: str, data_dir: Path, today_str: str) -> dict[str, FetchTask]:
    return {
        "twse_summary": FetchTask("twse_summary", [python_bin, "scripts/fetch_twse_summary.py"], data_dir / "twse_summary.json", "{}", 30, modes=("full", "morning-core")),
        "night_session": FetchTask("night_session", [python_bin, "scripts/tx_night_session.py", "assemble", "--data-dir", "data/night_session", "--date", today_str], data_dir / "night_session.json", "{}", 30, lambda c: c.get("date"), modes=("full", "morning-core")),
        "calendar": FetchTask("calendar", [python_bin, "scripts/fetch_calendar.py"], data_dir / "calendar.json", "{}", 30, lambda c: c.get("today"), modes=("full", "morning-core")),
        "news": FetchTask("news", [python_bin, "scripts/fetch_news.py"], data_dir / "news.json", "[]", 30, modes=("full", "morning-core")),
        "indices": FetchTask("indices", [python_bin, "scripts/fetch_indices.py"], data_dir / "indices.json", "{}", 35, modes=("full", "morning-core", "asia-open-update")),
        "disposal": FetchTask("disposal", [python_bin, "scripts/fetch_disposal.py", "--skip-date-check"], data_dir / "disposal.json", "{}", 40, lambda c: (c.get("date_check") or {}).get("page_says_applies_to"), modes=("full", "disposal")),
        "pressplay": FetchTask("pressplay", [python_bin, "scripts/fetch_pressplay_groups.py"], data_dir / "pressplay.json", "{}", 50, lambda c: c.get("chengwaye_date"), modes=("full", "candidates", "morning-core")),
        "chengwaye_daily": FetchTask("chengwaye_daily", [python_bin, "scripts/fetch_chengwaye_daily.py"], data_dir / "chengwaye_daily.json", "{}", 40, lambda c: c.get("page_date"), dependencies=("pressplay",), modes=("full", "candidates", "morning-core")),
        "chengwaye_stock_history": FetchTask("chengwaye_stock_history", [python_bin, "scripts/fetch_chengwaye_stock_history.py", "--pressplay", str(data_dir / "pressplay.json")], data_dir / "stock_history.json", '{"source":"https://chengwaye.com/stock/","codes":{},"failed_codes":[],"_status":"fetch_failed"}', 120, lambda c: c.get("fetched_at"), dependencies=("pressplay", "chengwaye_daily"), modes=("full", "candidates", "morning-core")),
        "financials": FetchTask("financials", [python_bin, "scripts/fetch_financials.py"], data_dir / "financials.json", '{"att":[],"fin":[],"rev":[]}', 150, modes=("full", "financials")),
    }


def _blocked_status(task: FetchTask, reason: str) -> dict[str, Any]:
    meta = source_policy(task.source_id)
    return {
        "source_id": task.source_id, "name": meta["name"], "is_required": meta["is_required"],
        "reliability_tier": meta["reliability_tier"], "ttl_minutes": meta["ttl_minutes"],
        "hard_expiry_minutes": meta["hard_expiry_minutes"], "fallback_policy": meta["fallback_policy"],
        "notification_level": meta["notification_level"], "dependencies": list(task.dependencies),
        "status": "blocked", "fetched_at": datetime.now(TAIPEI).isoformat(), "data_date": None,
        "age_minutes": 9999.0, "error_summary": reason, "fallback_used": False, "retry_attempts": 0,
        "impact_desc": meta["impact_desc"], "notification": f"{meta['notification_level']}: {reason}",
    }


def run_task_graph(
    tasks: Iterable[FetchTask],
    mode: str,
    max_workers: int = 4,
    fetch_fn: Callable[..., dict[str, Any]] = fetch_source,
    status_map: dict[str, dict[str, Any]] | None = None,
    respect_ttl: bool = False,
) -> TaskGraphResult:
    """Execute ready graph layers concurrently and dependants topologically.

    A failed/fallback parent is considered settled so independent branches keep
    running; a dependent node is blocked only when an upstream node is unable
    to produce a usable file.  This isolates high-risk failures without
    allowing stock history to race ahead of PressPlay input.
    """
    selected = {task.source_id: task for task in tasks if mode in task.modes}
    result = TaskGraphResult(statuses=dict(status_map or {}))
    pending = set(selected)
    completed: set[str] = set()
    max_workers = max(1, int(max_workers))

    def dependency_failed(task: FetchTask) -> str | None:
        for dep in task.dependencies:
            dep_status = result.statuses.get(dep, {})
            if dep in selected and dep not in completed:
                return f"依賴來源 {dep} 尚未完成"
            if dep_status.get("status") in ("failed", "blocked"):
                return f"依賴來源 {dep} 未產出可用資料"
            if not dep_status:
                return f"依賴來源 {dep} 尚未完成"
        return None

    while pending:
        ready = [selected[sid] for sid in sorted(pending) if all(dep not in selected or dep in completed for dep in selected[sid].dependencies)]
        if not ready:
            for sid in sorted(pending):
                result.statuses[sid] = _blocked_status(selected[sid], "任務圖存在循環或未滿足依賴")
                result.order.append(sid)
            break

        futures: dict[Future[dict[str, Any]], FetchTask] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(ready))) as executor:
            for task in ready:
                reason = dependency_failed(task)
                if reason:
                    result.statuses[task.source_id] = _blocked_status(task, reason)
                    result.order.append(task.source_id)
                    continue
                if respect_ttl and task_is_fresh(task.source_id, task.target_file):
                    cached = inspect_existing_source_file(task.source_id, task.target_file) or _blocked_status(task, "TTL 內找不到可用快照")
                    cached["refresh_skipped"] = True
                    cached["skip_reason"] = f"現有快照仍在 TTL {source_policy(task.source_id)['ttl_minutes']} 分鐘內"
                    result.statuses[task.source_id] = cached
                    result.order.append(task.source_id)
                    continue
                futures[executor.submit(
                    fetch_fn, task.source_id, task.command, task.target_file, task.fallback_content,
                    task.timeout, None, task.extract_date_fn, task.max_attempts, task.retry_delay_seconds,
                )] = task
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result.statuses[task.source_id] = future.result()
                except Exception as exc:
                    result.statuses[task.source_id] = _blocked_status(task, f"任務執行例外：{exc}")
            # Completion remains concurrent, but persisted audit order is stable.
            result.order.extend(task.source_id for task in sorted(ready, key=lambda item: item.source_id))
        completed.update(task.source_id for task in ready)
        pending.difference_update(task.source_id for task in ready)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Premarket Intel Tool Fetch Runner")
    parser.add_argument("--mode", choices=["full", "morning-core", "asia-open-update", "disposal", "candidates", "financials"], default="full")
    parser.add_argument("--date", help="Today's date (YYYY-MM-DD)", default=None)
    parser.add_argument("--allow-unsafe-exit", action="store_true", help="Do not exit with code 1 even if unsafe")
    parser.add_argument("--workers", type=int, default=4, help="Independent fetch task maximum parallelism")
    parser.add_argument("--respect-ttl", action="store_true", help="Skip external fetches when an existing snapshot is within its source TTL")
    args = parser.parse_args()

    today_str = args.date or datetime.now(TAIPEI).strftime("%Y-%m-%d")
    DATA_LATEST.mkdir(parents=True, exist_ok=True)
    existing_status_file = DATA_LATEST / "source_status.json"
    status_map: dict[str, Any] = {}
    if existing_status_file.exists():
        try:
            status_map = json.loads(existing_status_file.read_text(encoding="utf-8")).get("sources", {})
        except (OSError, json.JSONDecodeError, TypeError):
            status_map = {}

    source_file_map = {
        "twse_summary": DATA_LATEST / "twse_summary.json", "indices": DATA_LATEST / "indices.json",
        "night_session": DATA_LATEST / "night_session.json", "disposal": DATA_LATEST / "disposal.json",
        "pressplay": DATA_LATEST / "pressplay.json", "chengwaye_daily": DATA_LATEST / "chengwaye_daily.json",
        "chengwaye_stock_history": DATA_LATEST / "stock_history.json", "calendar": DATA_LATEST / "calendar.json",
        "financials": DATA_LATEST / "financials.json", "news": DATA_LATEST / "news.json",
    }
    for sid, file_path in source_file_map.items():
        item = inspect_existing_source_file(sid, file_path)
        if item:
            if sid not in status_map:
                status_map[sid] = item
            else:
                status_map[sid]["age_minutes"] = item["age_minutes"]
                status_map[sid].setdefault("ttl_minutes", item["ttl_minutes"])
                status_map[sid].setdefault("hard_expiry_minutes", item["hard_expiry_minutes"])

    graph = run_task_graph(_task_catalog(sys.executable, DATA_LATEST, today_str).values(), args.mode, args.workers, status_map=status_map, respect_ttl=args.respect_ttl)
    save_source_status(graph.statuses)
    eval_result = evaluate_source_health({"sources": graph.statuses})
    print("\n==========================================")
    print(f"PAGE READINESS: {eval_result.overall_status.upper()} ({eval_result.status_label})")
    print(f"TASK GRAPH ORDER: {' → '.join(graph.order)}")
    print("Reasons / Alerts:")
    for reason in eval_result.summary_reasons:
        print(f" - {reason}")
    for notification in eval_result.notifications:
        print(f"NOTIFY[{notification['level']}] {notification['source_id']}: {notification['message']}")
    print("==========================================\n")
    if eval_result.overall_status == "unsafe" and not args.allow_unsafe_exit:
        print("CRITICAL: One or more required sources failed! Marked as UNSAFE.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
