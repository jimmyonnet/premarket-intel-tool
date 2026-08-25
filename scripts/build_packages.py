#!/usr/bin/env python3
"""Build-time data packages for the lightweight GitHub Pages shell."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _clean_code(value: Any) -> str:
    return str(value or "").replace("⏸", "").strip()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("%", "").replace("億", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _match_seconds(value: Any) -> int | None:
    text = str(value or "")
    if "全額" in text:
        return 1200
    match = re.search(r"(\d+)\s*分", text)
    return int(match.group(1)) * 60 if match else None


def _trigger_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    condition = str(row.get("condition") or "")
    segments = row.get("condition_segments") or []
    if not condition and segments:
        condition = "".join(str(s.get("text") or "") for s in segments)
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([↑↓])\s*\(([+-]?[0-9]+(?:\.[0-9]+)?)%\)", condition)
    if not match:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([↑↓])", condition)
    if not match:
        return None
    return {
        "price": float(match.group(1)),
        "direction": "up" if match.group(2) == "↑" else "down",
        "pct": float(match.group(3)) if match.lastindex and match.lastindex >= 3 else None,
        "type": "突破即符合" if match.group(2) == "↑" else "跌破即符合",
    }


def _disposition_package(disposal: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for source in disposal.get("one_flag_from_disposal") or []:
        row = dict(source)
        rules = []
        for badge in row.get("badges") or []:
            current = _number(badge.get("current"))
            need = _number(badge.get("threshold"))
            if current is None or need is None:
                continue
            rules.append({
                "id": badge.get("short") or badge.get("title") or "rule",
                "label": badge.get("title") or badge.get("short") or "",
                "hit": int(current),
                "need": int(need),
                "remain": max(0, int(need - current)),
            })
        rules.sort(key=lambda rule: (rule["remain"], rule["need"]))
        trigger = _trigger_from_row(row)
        close = _number(row.get("close"))
        locked = "跌停" in str(row.get("condition") or "") or "鎖定" in str(row.get("condition") or "")
        items.append({
            "market": row.get("market"),
            "code": _clean_code(row.get("code")),
            "name": row.get("name") or _clean_code(row.get("code")),
            "close": close,
            "close_display": row.get("close"),
            "condition": row.get("condition"),
            "earliest_disposal": row.get("earliest_disposal"),
            "eta": str(row.get("earliest_disposal") or "").split(" ", 1)[0],
            "rules": rules,
            "primary_rule": rules[0] if rules else None,
            "trigger": trigger,
            "locked": locked,
            "condition_segments": row.get("condition_segments") or [],
        })

    releases = []
    for source in disposal.get("currently_in_disposal") or []:
        left = source.get("trading_days_left")
        if left not in (0, "0", "0天", "出關"):
            continue
        row = dict(source)
        releases.append({
            "market": row.get("market"),
            "code": _clean_code(row.get("code")),
            "name": row.get("name") or _clean_code(row.get("code")),
            "matching": row.get("matching"),
            "match_seconds": _match_seconds(row.get("matching")),
            "start_date": row.get("start_date"),
            "end_date": row.get("end_date"),
            "exit_date": row.get("exit_date"),
            "reason": row.get("reason"),
        })

    return {
        "data_date": (disposal.get("date_check") or {}).get("page_says_applies_to"),
        "source": disposal.get("source"),
        "items": items,
        "releases": releases,
        "active_count": len(disposal.get("currently_in_disposal") or []),
    }


def _candidate_package(pressplay: dict[str, Any], chengwaye_daily: dict[str, Any]) -> dict[str, Any]:
    rows = []
    seen: set[str] = set()
    for group_name, key in (("個別動能", "not_found_group"), ("族群聚焦", "found_group")):
        group = pressplay.get(key) or {}
        for source in group.get("matched") or []:
            row = dict(source)
            code = _clean_code(row.get("code"))
            if not code or code in seen:
                continue
            seen.add(code)
            rows.append({
                "market": row.get("market"),
                "code": code,
                "name": row.get("name") or code,
                "close": _number(row.get("close")),
                "volume": _number(row.get("volume")),
                "volume_display": row.get("volume"),
                "foreign": _number(row.get("foreign")),
                "trust": _number(row.get("trust")),
                "dealer": _number(row.get("dealer")),
                "foreign_display": row.get("foreign"),
                "trust_display": row.get("trust"),
                "dealer_display": row.get("dealer"),
                "ai_reason": row.get("ai_reason"),
                "group": row.get("group") or group_name,
                "source_group": group_name,
                "match_type": row.get("match_type"),
            })
    max_volume = max((row["volume"] or 0 for row in rows), default=0)
    for row in rows:
        row["volume_max"] = max_volume
    return {
        "source_article": pressplay.get("source_article") or {},
        "chengwaye_date": pressplay.get("chengwaye_date"),
        "items": rows,
        "matched_count": len(rows),
        "daily_codes": len((chengwaye_daily or {}).get("codes") or {}),
    }


def _financial_row(source: dict[str, Any], block: str) -> dict[str, Any]:
    parsed = source.get("parsed") or {}
    eps = _number(parsed.get("EPS"))
    prev_eps = _number(parsed.get("上季EPS"))
    gm = _number(parsed.get("毛利率"))
    if gm is None:
        gm = _number(parsed.get("Q2_毛利率")) or _number(parsed.get("本季毛利率"))
    prev_gm = _number(parsed.get("上季毛利率")) or _number(parsed.get("Q1_毛利率"))
    om = _number(parsed.get("營益率"))
    if om is None:
        om = _number(parsed.get("Q2_營益率")) or _number(parsed.get("本季營益率"))
    prev_om = _number(parsed.get("上季營益率")) or _number(parsed.get("Q1_營益率"))

    def delta(current: float | None, previous: float | None, explicit: Any) -> float | None:
        return _number(explicit) if explicit is not None else (round(current - previous, 2) if current is not None and previous is not None else None)

    return {
        "uid": source.get("uid"),
        "block": block,
        "code": _clean_code(source.get("code")),
        "name": source.get("name") or _clean_code(source.get("code")),
        "date": source.get("date"),
        "time": source.get("time"),
        "subject": source.get("subject"),
        "raw": source.get("raw"),
        "period": parsed.get("上季") or parsed.get("季度") or source.get("date"),
        "ai_score": _number(source.get("ai_score")),
        "ai_reason": source.get("ai_reason"),
        "eps": eps,
        "prev_eps": prev_eps,
        "d_eps": delta(eps, prev_eps, source.get("d_eps")),
        "gm": gm,
        "prev_gm": prev_gm,
        "d_gm": delta(gm, prev_gm, source.get("d_gm")),
        "om": om,
        "prev_om": prev_om,
        "d_om": delta(om, prev_om, source.get("d_om")),
        "parsed": parsed,
    }


def _announcements_package(financials: dict[str, Any]) -> dict[str, Any]:
    blocks = {}
    for key in ("att", "fin", "rev"):
        blocks[key] = {
            "ok": True,
            "rows": [_financial_row(row, key) for row in (financials.get(key) or [])],
        }
    return {"cutoff_str": financials.get("cutoff_str"), "blocks": blocks}


def _news_package(news: Any) -> dict[str, Any]:
    if isinstance(news, dict):
        return news
    return {"items": news or []}


def _opening_forecast_package(forecast: Any) -> dict[str, Any]:
    """Keep the new forecast optional so legacy builds remain publishable."""
    if isinstance(forecast, dict) and forecast.get("status"):
        return forecast
    return {
        "schema_version": "opening-forecast.v1",
        "prediction_id": None,
        "market_date": None,
        "status": "not_generated",
        "locked_at": None,
        "model_version": None,
        "previous_close": None,
        "predicted_change_points": None,
        "predicted_open": None,
        "direction": "unknown",
        "gap_label": "unknown",
        "confidence": "unknown",
        "confidence_reasons": ["今日尚未產生預測"],
        "evidence": [],
        "data_quality": {"missing_factors": [], "conflicts": [], "conflict_directions": [], "cache_used": False},
        "formula": {"threshold_points": 100.0, "available_weight": 0.0, "features": []},
    }


def _opening_result_package(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("status"):
        return result
    return {
        "schema_version": "opening-result.v1",
        "prediction_id": None,
        "market_date": None,
        "status": "not_applicable",
        "target_time": "09:00:00+08:00",
        "verified_at": None,
        "attempts": 0,
        "attempt_log": [],
        "actual_open": None,
        "actual_change_points": None,
        "actual_direction": "unknown",
        "direction_correct": None,
        "signed_error_points": None,
        "absolute_error_points": None,
        "source": {"name": "TWSE MIS TAIEX", "url": "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0", "observed_at": None, "fetched_at": None, "official": True},
        "error": "今日尚未完成實際開盤驗證",
    }


def _learning_status_package(status: Any, forecast: dict[str, Any]) -> dict[str, Any]:
    if isinstance(status, dict) and status.get("schema_version"):
        return status
    return {
        "schema_version": "learning-status.v1",
        "status": "warmup",
        "model_version": forecast.get("model_version"),
        "verified_days": 0,
        "required_days": 20,
        "stats": None,
        "confidence_breakdown": {},
        "pending_proposal": None,
        "manual_pause_remaining_days": 0,
        "last_change": None,
        "message": "學習資料累積中，滿 20 個已驗證交易日後才顯示正式統計",
    }


def _write_json(path: Path, payload: Any) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def write_packages(
    docs_dir: str | Path,
    *,
    indices: dict[str, Any],
    night: dict[str, Any],
    disposal: dict[str, Any],
    pressplay: dict[str, Any],
    chengwaye_daily: dict[str, Any],
    calendar: dict[str, Any],
    financials: dict[str, Any],
    news: Any,
    ai_summary: dict[str, Any] | None = None,
    twse: dict[str, Any],
    meta: dict[str, Any],
    stock_history: dict[str, Any] | None = None,
    opening_forecast: dict[str, Any] | None = None,
    opening_result: dict[str, Any] | None = None,
    learning_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the package files and return the final meta payload."""
    docs_path = Path(docs_dir)
    data_path = docs_path / "data"
    data_path.mkdir(parents=True, exist_ok=True)
    packages = {
        "disposition": _disposition_package(disposal),
        "candidates": _candidate_package(pressplay, chengwaye_daily),
        "stock_history": stock_history or {"source": "https://chengwaye.com/stock/", "codes": {}, "failed_codes": [], "_status": "fetch_failed"},
        "announcements": _announcements_package(financials),
        "macro": {"indices": indices, "night": night, "twse": twse},
        "calendar": {"today": calendar.get("today"), "range_end": calendar.get("range_end"), "events": calendar.get("events") or []},
        "news": _news_package(news),
        "ai_summary": ai_summary or {"status": "fallback", "provider": "deterministic fallback"},
        "opening_forecast": _opening_forecast_package(opening_forecast),
        "opening_result": _opening_result_package(opening_result),
        "learning_status": _learning_status_package(learning_status, _opening_forecast_package(opening_forecast)),
    }
    hashes = {}
    for key, payload in packages.items():
        encoded = _write_json(data_path / f"{key}.json", payload)
        hashes[key] = hashlib.sha256(encoded).hexdigest()[:12]

    data_revision = hashlib.sha256(
        json.dumps(hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    final_meta = dict(meta)
    final_meta.update({
        "schema_version": 1,
        "data_revision": data_revision,
        "built_at": datetime.now().astimezone().isoformat(),
        "hash": hashes,
        "packages": {key: f"data/{key}.json" for key in packages},
        "show_banner": any(
            bool(source.get("is_required")) and (_number(source.get("age_minutes")) or 0) > 720
            for source in (meta.get("sources") or [])
        ) or any(
            event.get("date") == calendar.get("today") and event.get("importance") == 3
            for event in (calendar.get("events") or [])
        ),
    })
    _write_json(data_path / "meta.json", final_meta)
    # Backward-compatible copy for existing diagnostics and integrations.
    _write_json(docs_path / "data_meta.json", final_meta)
    return final_meta
