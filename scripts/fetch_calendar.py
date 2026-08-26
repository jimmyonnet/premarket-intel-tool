from __future__ import annotations
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
from opencc import OpenCC

try:
    from trading_calendar import (
        get_current_trading_day,
        get_next_trading_day,
        is_twse_trading_day,
        load_twse_holidays,
    )
except ModuleNotFoundError:  # Support package-style imports in test runners.
    from scripts.trading_calendar import (
        get_current_trading_day,
        get_next_trading_day,
        is_twse_trading_day,
        load_twse_holidays,
    )

DEFAULT_ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_c040a8d14375de55799b6fdd8ece2ee2f32aa85fd0e5b39d14b1e07f90df424e"
    "%40group.calendar.google.com/public/basic.ics"
)
TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
DEFAULT_DAYS_AHEAD = 14
HEADERS = {"User-Agent": "premarket-intel-tool (+github actions calendar sync)"}
S2TW_CONVERTER = OpenCC("s2twp")

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
    return S2TW_CONVERTER.convert(text)


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



def parse_economic_details(summary: str, description: str, ev_date: datetime.date, time_str: str | None, all_day: bool):
    text = f"{summary} {description or ''}".upper()

    # 1. Country & Flag & Timezone
    if any(k in summary for k in ["美國", "美聯儲", "美", "US"]) or "FED" in text or "FOMC" in text:
        country, flag, tz_name, tz_lbl = "US", "🇺🇸", "America/New_York", "ET"
    elif any(k in summary for k in ["台灣", "台股", "台指", "台積電", "TW"]):
        country, flag, tz_name, tz_lbl = "TW", "🇹🇼", "Asia/Taipei", "TPE"
    elif any(k in summary for k in ["日本", "日銀", "JP"]):
        country, flag, tz_name, tz_lbl = "JP", "🇯🇵", "Asia/Tokyo", "JST"
    elif any(k in summary for k in ["歐元區", "歐洲", "德國", "法國", "ECB", "EU"]):
        country, flag, tz_name, tz_lbl = "EU", "🇪🇺", "Europe/Berlin", "CET"
    elif any(k in summary for k in ["中國", "陸", "人行", "CN"]):
        country, flag, tz_name, tz_lbl = "CN", "🇨🇳", "Asia/Shanghai", "CST"
    elif any(k in summary for k in ["英國", "BOE", "GB"]):
        country, flag, tz_name, tz_lbl = "GB", "🇬🇧", "Europe/London", "GMT"
    else:
        country, flag, tz_name, tz_lbl = "GLOBAL", "🌐", "UTC", "UTC"

    # 2. Category
    if any(k in text for k in ["FED", "聯準會", "FOMC", "利率決議", "降息", "升息", "央行", "ECB", "BOJ", "人行"]):
        category, category_name = "central_bank", "央行"
    elif any(k in text for k in ["演講", "談話", "聽證會", "POWELL", "SPEECH", "TESTIMONY"]):
        category, category_name = "speech", "演講"
    elif any(k in text for k in ["休市", "假期", "連假", "HOLIDAY"]):
        category, category_name = "holiday", "假期"
    elif any(k in text for k in ["法說", "財報", "除權息", "股東會", "庫藏股", "營收", "新股上市", "掛牌", "EARNING"]):
        category, category_name = "earnings", "財報"
    elif any(k in text for k in ["CPI", "PCE", "PPI", "非農", "GDP", "PMI", "失業率", "零售", "工廠訂單", "耐用品", "景氣對策", "進出口", "貿易", "利潤"]):
        category, category_name = "macro", "總經"
    else:
        category, category_name = "other", "其他"

    # 3. Importance (1 | 2 | 3)
    if any(k in text for k in ["GDP", "CPI", "PCE", "非農", "FOMC", "利率決議", "失業率", "鮑爾", "POWELL", "台積電"]):
        importance = 3
    elif any(k in text for k in ["PMI", "零售", "耐用品", "PPI", "原油庫存", "景氣對策", "工廠訂單", "初次申請失業"]):
        importance = 2
    else:
        importance = 1

    # 4. Values: Forecast, Previous, Actual
    forecast = None
    previous = None
    actual = None

    if description:
        m_fc = re.search(r"(?:市場預期|預期值?|預估|Consensus|Forecast)\s*[:：]\s*([^\n\r,;]+)", description, re.IGNORECASE)
        if m_fc:
            forecast = m_fc.group(1).strip()

        m_prev = re.search(r"(?:前值|前期值?|前前期|Previous)\s*[:：]\s*([^\n\r,;]+)", description, re.IGNORECASE)
        if m_prev:
            previous = m_prev.group(1).strip()

        m_act = re.search(r"(?:實際|公布值?|公佈值?|Actual)\s*[:：]\s*([^\n\r,;]+)", description, re.IGNORECASE)
        if m_act:
            actual = m_act.group(1).strip()

    # 5. Datetime UTC and Origin Timezone Calculation
    if all_day or not time_str:
        datetime_utc = f"{ev_date.isoformat()}T00:00:00Z"
        time_tpe_str = "全天"
        time_origin_str = "全天"
    else:
        hh, mm = map(int, time_str.split(":"))
        dt_taipei = datetime.datetime(ev_date.year, ev_date.month, ev_date.day, hh, mm, tzinfo=TAIPEI)
        dt_utc = dt_taipei.astimezone(datetime.timezone.utc)
        datetime_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_tpe_str = f"{time_str} TPE"

        if country == "US":
            dt_origin = dt_utc.astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
            origin_hhmm = dt_origin.strftime("%H:%M")
            day_diff = (dt_origin.date() - ev_date).days
            diff_lbl = f"{day_diff:+d}" if day_diff != 0 else ""
            time_origin_str = f"{origin_hhmm}{diff_lbl} ET"
        elif country == "JP":
            dt_origin = dt_utc.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
            time_origin_str = f"{dt_origin.strftime('%H:%M')} JST"
        elif country == "EU":
            dt_origin = dt_utc.astimezone(datetime.timezone(datetime.timedelta(hours=2)))
            time_origin_str = f"{dt_origin.strftime('%H:%M')} CET"
        elif country == "GB":
            dt_origin = dt_utc.astimezone(datetime.timezone(datetime.timedelta(hours=1)))
            time_origin_str = f"{dt_origin.strftime('%H:%M')} GMT"
        else:
            time_origin_str = time_tpe_str

    comparison = "pending"
    if actual and forecast:
        try:
            act_num = float(re.sub(r"[^0-9.-]", "", actual))
            fc_num = float(re.sub(r"[^0-9.-]", "", forecast))
            if abs(act_num - fc_num) < 0.001:
                comparison = "inline"
            elif act_num > fc_num:
                comparison = "beat"
            else:
                comparison = "miss"
        except Exception:
            comparison = "inline"

    return {
        "country": country,
        "flag": flag,
        "timezone_origin": tz_name,
        "timezone_label": tz_lbl,
        "time_origin_str": time_origin_str,
        "time_tpe_str": time_tpe_str,
        "datetime_utc": datetime_utc,
        "category": category,
        "category_name": category_name,
        "importance": importance,
        "forecast": forecast,
        "previous": previous,
        "actual": actual,
        "comparison": comparison,
    }


def _iter_months(start_date: datetime.date, end_date: datetime.date):
    cursor = start_date.replace(day=1)
    last_month = end_date.replace(day=1)
    while cursor <= last_month:
        yield cursor.year, cursor.month
        cursor = (cursor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def _third_wednesday(year: int, month: int) -> datetime.date:
    first = datetime.date(year, month, 1)
    days_to_wednesday = (2 - first.weekday()) % 7
    return first + datetime.timedelta(days=days_to_wednesday + 14)


def _last_day_of_month(year: int, month: int) -> datetime.date:
    if month == 12:
        return datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    return datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)


def get_local_rule_range_end(start_date: datetime.date, external_range_end: datetime.date) -> datetime.date:
    """Keep deterministic TW rules visible through the next complete month.

    The external ICS keeps its existing short look-ahead window, while Taiwan
    deadline/settlement rules need to include the next monthly cycle to remain
    actionable when that window ends before the next scheduled rule event.
    """
    next_month_start = (start_date.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return max(external_range_end, _last_day_of_month(next_month_start.year, next_month_start.month))


def _tw_rule_event(
    *,
    rule_type: str,
    ev_date: datetime.date,
    title: str,
    note: str,
    category: str,
    category_name: str,
    importance: int,
    id_suffix: str | None = None,
) -> dict:
    stable_suffix = id_suffix or ev_date.isoformat()
    return {
        "id": f"local-rule-{rule_type}-{stable_suffix}",
        "date": ev_date.isoformat(),
        "time": None,
        "all_day": True,
        "title": title,
        "summary": title,
        "description": note,
        "note": note,
        "mm_link": None,
        "source_url": None,
        "source": "local-rule",
        "semantic_type": rule_type,
        "category": category,
        "category_name": category_name,
        "country": "TW",
        "flag": "🇹🇼",
        "timezone_origin": "Asia/Taipei",
        "timezone_label": "TPE",
        "time_origin_str": "全天",
        "time_tpe_str": "全天",
        "datetime_utc": f"{ev_date.isoformat()}T00:00:00Z",
        "importance": importance,
        "forecast": None,
        "previous": None,
        "actual": None,
        "comparison": "pending",
    }


def generate_tw_market_rule_events(
    start_date: datetime.date,
    end_date: datetime.date,
    holidays: set[str] | None = None,
) -> list[dict]:
    """Generate deterministic Taiwan market events within the requested date range.

    Rules are deliberately limited to recurring disclosure deadlines, the third
    Wednesday derivatives settlement, quarter-end trading days, and dates
    already maintained in the TWSE holiday/manual-override JSON. This function
    never predicts temporary closures such as typhoon days.
    """
    active_holidays = holidays if holidays is not None else load_twse_holidays()
    events: list[dict] = []

    for year, month in _iter_months(start_date, end_date):
        revenue_deadline = datetime.date(year, month, 10)
        if start_date <= revenue_deadline <= end_date:
            events.append(_tw_rule_event(
                rule_type="revenue_deadline",
                ev_date=revenue_deadline,
                title="台股月營收申報截止日",
                note="依上市櫃公司每月 10 日前公告前一月營收之規則推算。",
                category="macro",
                category_name="總經",
                importance=2,
            ))

        scheduled_settlement = _third_wednesday(year, month)
        settlement_date = scheduled_settlement
        if not is_twse_trading_day(scheduled_settlement, active_holidays):
            settlement_date = get_next_trading_day(scheduled_settlement, active_holidays)
        if start_date <= settlement_date <= end_date:
            shifted_note = ""
            if settlement_date != scheduled_settlement:
                shifted_note = (
                    f"原訂 {scheduled_settlement.strftime('%m/%d')} 非交易日，"
                    f"順延至 {settlement_date.strftime('%m/%d')}。"
                )
            events.append(_tw_rule_event(
                rule_type="futures_settlement",
                ev_date=settlement_date,
                title="台指期／選擇權結算日",
                note="依第三週週三結算與 TWSE 交易日曆規則推算。" + shifted_note,
                category="macro",
                category_name="總經",
                importance=3,
            ))

        if month in (3, 6, 9, 12):
            quarter_end = _last_day_of_month(year, month)
            last_trading_day = get_current_trading_day(quarter_end, active_holidays)
            if start_date <= last_trading_day <= end_date:
                events.append(_tw_rule_event(
                    rule_type="quarter_end_trading_day",
                    ev_date=last_trading_day,
                    title="台股季底最後交易日",
                    note="依季末與 TWSE 交易日曆規則推算。",
                    category="macro",
                    category_name="總經",
                    importance=2,
                ))

    closure_dates = sorted(
        datetime.date.fromisoformat(iso_date)
        for iso_date in active_holidays
        if start_date <= datetime.date.fromisoformat(iso_date) <= end_date
    )
    closure_ranges: list[list[datetime.date]] = []
    for closure_date in closure_dates:
        if not closure_ranges or closure_date != closure_ranges[-1][-1] + datetime.timedelta(days=1):
            closure_ranges.append([closure_date])
        else:
            closure_ranges[-1].append(closure_date)

    for date_range in closure_ranges:
        range_start, range_end = date_range[0], date_range[-1]
        if range_start == range_end:
            title = "台股休市"
            date_label = range_start.strftime("%m/%d")
        else:
            title = f"台股休市（{range_start.strftime('%m/%d')}–{range_end.strftime('%m/%d')}）"
            date_label = f"{range_start.strftime('%m/%d')}–{range_end.strftime('%m/%d')}"
        events.append(_tw_rule_event(
            rule_type="market_holiday",
            ev_date=range_start,
            title=title,
            note=f"依 TWSE 開（休）市日期與人工停市覆蓋資料載入（{date_label}）。",
            category="holiday",
            category_name="假期",
            importance=1,
            id_suffix=f"{range_start.isoformat()}-{range_end.isoformat()}",
        ))

    return sorted(events, key=lambda event: (event["date"], event["time"] or "", event["id"]))


def event_semantic_type(event: dict) -> str | None:
    """Infer a narrow semantic type for external-vs-local rule de-duplication."""
    if event.get("semantic_type"):
        return event["semantic_type"]
    text = " ".join(str(event.get(key) or "") for key in ("title", "summary", "description", "note")).upper()
    country = event.get("country")
    if "營收" in text:
        return "revenue_deadline"
    if any(keyword in text for keyword in ("結算", "SETTLEMENT", "期指", "選擇權")):
        return "futures_settlement"
    if "季底" in text and any(keyword in text for keyword in ("交易", "最後", "LAST")):
        return "quarter_end_trading_day"
    if country == "TW" and (event.get("category") == "holiday" or any(keyword in text for keyword in ("休市", "連假", "HOLIDAY"))):
        return "market_holiday"
    return None


def merge_tw_market_rule_events(external_events: list[dict], local_events: list[dict]) -> list[dict]:
    """Merge local rules without replacing same-day, same-type external events."""
    external_keys = {
        (event.get("date"), event_semantic_type(event))
        for event in external_events
        if event_semantic_type(event)
    }
    retained_local_events = [
        event for event in local_events
        if (event.get("date"), event_semantic_type(event)) not in external_keys
    ]
    merged = list(external_events) + retained_local_events
    return sorted(merged, key=lambda event: (event.get("date") or "", event.get("time") or ""))

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
        details = parse_economic_details(summary, description, ev_date, time_str, all_day)
        ev_id = f"ev-{ev_date.isoformat()}-{len(events)+1}"

        events.append({
            "id": ev_id,
            "date": ev_date.isoformat(),
            "time": time_str,
            "all_day": all_day,
            "title": summary,
            "summary": summary,
            "description": description[:200] or None,
            "note": description[:200] or None,
            "mm_link": mm_link,
            "source_url": mm_link,
            "category": details["category"],
            "category_name": details["category_name"],
            "country": details["country"],
            "flag": details["flag"],
            "timezone_origin": details["timezone_origin"],
            "timezone_label": details["timezone_label"],
            "time_origin_str": details["time_origin_str"],
            "time_tpe_str": details["time_tpe_str"],
            "datetime_utc": details["datetime_utc"],
            "importance": details["importance"],
            "forecast": details["forecast"],
            "previous": details["previous"],
            "actual": details["actual"],
            "comparison": details["comparison"],
        })

    events.sort(key=lambda e: (e["date"], e["time"] or ""))
    return events


def filter_events_to_range(events: list[dict], start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    """Keep only events in the published inclusive date window."""
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    return [
        event for event in events
        if event.get("date") and start_iso <= event["date"] <= end_iso
    ]


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
    local_rule_range_end = get_local_rule_range_end(today, end_date)

    ics_bytes = fetch_ics_bytes(args.ics_url, args.fixture)
    external_events = extract_events(ics_bytes, today, end_date)
    local_events = generate_tw_market_rule_events(today, local_rule_range_end)
    events = merge_tw_market_rule_events(external_events, local_events)
    # Local rules may be generated through the next complete month so that
    # month-end trading-day calculations are correct. The published calendar,
    # however, must honour the requested [today, today + days_ahead] window.
    events = filter_events_to_range(events, today, end_date)

    result = {
        "source": args.ics_url,
        "today": today.isoformat(),
        "range_end": end_date.isoformat(),
        "events": events,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
