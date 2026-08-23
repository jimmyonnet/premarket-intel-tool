#!/usr/bin/env python3
"""
Premarket Intel Tool - Notification Dispatcher
Supports Webhook notifications for both Success (Summary) and Failure (Error) events.
Compatible with LINE Notify, Discord Webhooks, Slack, and Generic JSON Webhooks.
Zero external dependencies (uses standard library urllib only).
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))

def send_http_post(url: str, data: dict = None, form_data: dict = None, headers: dict = None) -> bool:
    """Helper to send HTTP POST request using urllib.request."""
    if not url:
        return False
    try:
        req_headers = headers or {}
        if form_data:
            encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif data:
            encoded_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            if "Content-Type" not in req_headers:
                req_headers["Content-Type"] = "application/json; charset=utf-8"
        else:
            encoded_data = b""

        req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[Notify] Webhook response: {resp.status}")
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[Notify] Failed to send webhook to {url}: {e}", file=sys.stderr)
        return False

def build_summary_content() -> dict:
    """Extracts summary information from latest data files."""
    now = datetime.now(TAIPEI)
    
    # Load disposal data
    disposal_file = Path("data/latest/disposal.json")
    disposal = json.loads(disposal_file.read_text("utf-8")) if disposal_file.exists() else {}
    
    one_away = disposal.get("one_flag_from_disposal") or []
    current_disposal = disposal.get("currently_in_disposal") or []
    exiting = [r for r in current_disposal if r.get("trading_days_left") in (0, "0", "0天", "出關")]
    
    # Load pressplay candidate data
    pp_file = Path("data/latest/pressplay.json")
    pressplay = json.loads(pp_file.read_text("utf-8")) if pp_file.exists() else {}
    found_group = (pressplay.get("found_group") or {}).get("matched") or []
    
    # Load meta data
    meta_file = Path("docs/data_meta.json")
    meta = json.loads(meta_file.read_text("utf-8")) if meta_file.exists() else {}
    data_date = meta.get("data_date") or now.strftime("%m/%d")

    # Format text lists
    one_away_strs = [f"{r.get('code')} {r.get('name')}" for r in one_away[:6]]
    exiting_strs = [f"{r.get('code')} {r.get('name')}" for r in exiting[:6]]
    found_strs = [f"{r.get('code', '').replace('⏸','')} {r.get('name')}" for r in found_group[:8]]

    msg_lines = [
        f"📊【台股盤前情報準備台】{data_date} 盤前情報速報",
        "────────────────────"
    ]

    if one_away:
        msg_lines.append(f"🚨 差 1 次處置預警 ({len(one_away)}檔):")
        msg_lines.append("   " + ", ".join(one_away_strs) + ("..." if len(one_away) > 6 else ""))
    else:
        msg_lines.append("🚨 差 1 次處置預警: 今日無")

    if exiting:
        msg_lines.append(f"🎉 今日出關 ({len(exiting)}檔):")
        msg_lines.append("   " + ", ".join(exiting_strs) + ("..." if len(exiting) > 6 else ""))

    if found_group:
        msg_lines.append(f"🎯 盤前族群聚焦 ({len(found_group)}檔):")
        msg_lines.append("   " + ", ".join(found_strs) + ("..." if len(found_group) > 8 else ""))

    msg_lines.append("────────────────────")
    msg_lines.append("🔗 完整情報: https://jimmyonnet.github.io/premarket-intel-tool/")

    raw_text = "\n".join(msg_lines)
    return {
        "text": raw_text,
        "date": data_date,
        "one_away": one_away_strs,
        "exiting": exiting_strs,
        "candidates": found_strs
    }

def notify_success():
    summary = build_summary_content()
    text = summary["text"]
    print("=== SUMMARY MESSAGE ===")
    print(text)
    
    # 1. LINE Notify
    line_token = os.getenv("LINE_NOTIFY_TOKEN")
    if line_token:
        send_http_post(
            "https://notify-api.line.me/api/notify",
            form_data={"message": "\n" + text},
            headers={"Authorization": f"Bearer {line_token}"}
        )
        
    # 2. Discord Webhook
    discord_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_url:
        send_http_post(discord_url, data={"content": text})
        
    # 3. Generic Summary Webhook
    generic_url = os.getenv("SUMMARY_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
    if generic_url:
        send_http_post(generic_url, data={
            "event": "premarket_summary",
            "message": text,
            "data": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

def notify_failure():
    repo = os.getenv("GITHUB_REPOSITORY", "premarket-intel-tool")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server_url}/{repo}/actions/runs/{run_id}" if run_id else ""
    now_str = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")

    text = f"❌【PMIT 警報】GitHub Actions 盤前資料建置失敗！\n時間：{now_str} (台北)\n專案：{repo}\n紀錄：{run_url}\n請盡速至 GitHub Actions 檢查 Logs。"
    print("=== FAILURE MESSAGE ===")
    print(text)

    # 1. LINE Notify
    line_token = os.getenv("LINE_NOTIFY_TOKEN")
    if line_token:
        send_http_post(
            "https://notify-api.line.me/api/notify",
            form_data={"message": "\n" + text},
            headers={"Authorization": f"Bearer {line_token}"}
        )

    # 2. Discord Webhook
    discord_url = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("ERROR_WEBHOOK_URL")
    if discord_url:
        send_http_post(discord_url, data={"content": text})

    # 3. Generic Error Webhook
    error_url = os.getenv("ERROR_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
    if error_url and error_url != discord_url:
        send_http_post(error_url, data={
            "event": "workflow_failed",
            "repository": repo,
            "run_url": run_url,
            "message": text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

def main():
    parser = argparse.ArgumentParser(description="Premarket Notification Dispatcher")
    parser.add_argument("--mode", choices=["success", "failure"], default="success")
    args = parser.parse_args()

    if args.mode == "success":
        notify_success()
    else:
        notify_failure()

if __name__ == "__main__":
    main()
