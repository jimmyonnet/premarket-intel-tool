#!/usr/bin/env python3
"""
Part 4 data source: a user-maintained financial/economic events calendar,
published as a public Google Calendar ICS feed.

  https://calendar.google.com/calendar/ical/.../public/basic.ics

Fetches the ICS feed and expands it (including recurring events, via
recurring_ical_events -- plain icalendar does not expand RRULEs) to a
flat list of event occurrences whose local (Asia/Taipei) date falls
within [today, today + --days-ahead], sorted by date then time.

Includes automatic event category classification (FED/央行, 總經數據, 期貨結算, 個股/法說),
Simplified to Traditional Chinese conversion, and MM link extraction.
"""
import argparse
import datetime
import json
import re
from pathlib import Path

import requests
import icalendar
import recurring_ical_events

DEFAULT_ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_c040a8d14375de55799b6fdd8ece2ee2f32aa85fd0e5b39d14b1e07f90df424e"
    "%40group.calendar.google.com/public/basic.ics"
)
TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
DEFAULT_DAYS_AHEAD = 14
HEADERS = {"User-Agent": "premarket-intel-tool (+github actions calendar sync)"}

S2TW_MAP = {
    "MM图表连结": "MM圖表連結",
    "图表": "圖表",
    "连结": "連結",
    "市场": "市場",
    "预期": "預期",
    "制造业": "製造業",
    "采购": "採購",
    "经理人": "經理人",
    "指数": "指數",
    "欧元区": "歐元區",
    "德国": "德國",
    "美国": "美國",
    "中国": "中國",
    "台湾": "台灣",
    "环比": "月增率(MoM)",
    "同比": "年增率(YoY)",
    "申请": "申請",
    "救济金": "救濟金",
    "人数": "人數",
    "失业": "失業",
    "库存": "庫存",
    "周变动": "週變動",
    "工业": "工業",
    "企业": "企業",
    "利润": "利潤",
    "累计": "累計",
    "景气": "景氣",
    "对策": "對策",
    "信号": "信號",
    "分数": "分數",
    "零售": "零售",
    "销售": "銷售",
    "订单": "訂單",
    "耐用品": "耐用品",
    "服务业": "服務業",
    "实际": "實際",
    "生产": "生產",
    "总值": "總值",
    "季环比": "季增率(QoQ)",
    "原油": "原油",
}


def s2tw(text: str) -> str:
    if not text:
        return text
    for s, tw in S2TW_MAP.items():
        text = text.replace(s, tw)
    return text


def fetch_ics_bytes(url: str, fixture: Path = None) -> bytes:
    if fixture is not None:
        return fixture.read_bytes()
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.content


def classify_event(summary: str, description: str) -> dict:
    text = f"{summary} {description or ''}".upper()
    if any(k in text for k in ["FED", "聯準會", "FOMC", "鮑爾", "POWELL", "利率決議", "降息", "升息", "央行"]):
        return {"category": "fed", "category_name": "FED/央行"}
    if any(k in text for k in ["CPI", "PCE", "PPI", "非農", "GDP", "PMI", "失業率", "零售", "工廠訂單", "耐用品"]):
        return {"category": "econ", "category_name": "總經數據"}
    if any(k in text for k in ["結算", "期指", "選擇權", "摩台", "台指期", "SETTLEMENT", "FUTURES"]):
        return {"category": "futures", "category_name": "期貨結算"}
    if any(k in text for k in ["法說", "財報", "除權息", "股東會", "庫藏股", "營收", "新股上市", "掛牌", "EARNING"]):
        return {"category": "stock", "category_name": "個股/法說"}
    return {"category": "general", "category_name": "事件"}


def extract_events(ics_bytes: bytes, start_date, end_date):
    cal = icalendar.Calendar.from_ical(ics_bytes)
    occurrences = recurring_ical_events.of(cal).between(start_date, end_date)

    events = []
    for comp in occurrences:
        dt = comp.get("dtstart").dt
        all_day = not isinstance(dt, datetime.datetime)
        if all_day:
            ev_date, time_str = dt, None
        else:
            if dt.tzinfo is not None:
                dt = dt.astimezone(TAIPEI)
            ev_date, time_str = dt.date(), dt.strftime("%H:%M")

        if ev_date < start_date or ev_date > end_date:
            continue

        summary = str(comp.get("summary", "") or "").strip()
        if not summary:
            continue
        description = str(comp.get("description", "") or "").strip()

        # Convert Simplified to Traditional Chinese
        summary = s2tw(summary)
        description = s2tw(description)

        # Extract MM link if present
        mm_link = None
        link_match = re.search(r"https?://[^\s]+", description)
        if link_match:
            mm_link = link_match.group(0)
            description = re.sub(r"(MM\s*圖表連結|MM\s*图表连结)?:\s*https?://[^\s]+", "", description).strip()

        cat_info = classify_event(summary, description)

        events.append({
            "date": ev_date.isoformat(),
            "time": time_str,
            "all_day": all_day,
            "summary": summary,
            "description": description[:200] or None,
            "mm_link": mm_link,
            "category": cat_info["category"],
            "category_name": cat_info["category_name"],
        })

    events.sort(key=lambda e: (e["date"], e["time"] or ""))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ics-url", default=DEFAULT_ICS_URL)
    ap.add_argument("--fixture", type=Path, default=None, help="offline test .ics file")
    ap.add_argument(
        "--today", type=str, default=None,
        help="override 'today' (YYYY-MM-DD); defaults to real today (Asia/Taipei date)",
    )
    ap.add_argument("--days-ahead", type=int, default=DEFAULT_DAYS_AHEAD)
    args = ap.parse_args()

    today = (
        datetime.date.fromisoformat(args.today) if args.today
        else datetime.datetime.now(TAIPEI).date()
    )
    end_date = today + datetime.timedelta(days=args.days_ahead)

    ics_bytes = fetch_ics_bytes(args.ics_url, args.fixture)
    events = extract_events(ics_bytes, today, end_date)

    result = {
        "source": args.ics_url,
        "today": today.isoformat(),
        "range_end": end_date.isoformat(),
        "events": events,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
