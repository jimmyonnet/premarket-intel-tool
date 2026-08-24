#!/usr/bin/env python3
"""
Data health and credibility evaluation module for Premarket Intel Tool.
Provides schema definitions and status evaluation logic for all data sources.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_STATUS_PATH = Path(__file__).parent.parent / "data" / "latest" / "source_status.json"

# Source definition catalog
SOURCES_METADATA: dict[str, dict[str, Any]] = {
    "indices": {
        "name": "指數行情 (美股/亞股/ADR)",
        "is_required": True,
        "impact_desc": "無法掌握美股收盤與日韓開盤走勢，難以評估早盤開盤連動方向",
    },
    "disposal": {
        "name": "處置股與出關預警",
        "is_required": True,
        "impact_desc": "無法取得即時處置管制標準與出關名單，無法進行風險避險",
    },
    "twse_summary": {
        "name": "大盤昨收與三大法人",
        "is_required": False,
        "impact_desc": "缺少昨日加權指數與外資/投信買賣超金額彙整",
    },
    "night_session": {
        "name": "台指期夜盤走勢",
        "is_required": False,
        "impact_desc": "缺少期貨夜盤行情與點位走向，可改參考美股指數",
    },
    "pressplay": {
        "name": "PressPlay 盤前族群與標的",
        "is_required": False,
        "impact_desc": "缺少每日專欄族群整理，候選股清單將呈現空白",
    },
    "chengwaye_daily": {
        "name": "主力券商與當沖籌碼明細",
        "is_required": False,
        "impact_desc": "缺少重點個股之分點買賣與當沖籌碼排行",
    },
    "chengwaye_stock_history": {
        "name": "Chengwaye 個股漲停履歷",
        "is_required": False,
        "impact_desc": "缺少候選股漲停次數、最近漲停與隔日表現履歷",
    },
    "calendar": {
        "name": "總經財經行事曆",
        "is_required": False,
        "impact_desc": "缺少今日重磅總經數據與事件日程倒數",
    },
    "financials": {
        "name": "市場未反映重大公告 (財報/營收/處分)",
        "is_required": False,
        "impact_desc": "缺少昨日盤後自結損益與營收公告統計",
    },
    "news": {
        "name": "盤前即時新聞聚合",
        "is_required": False,
        "impact_desc": "缺少隔夜美股與產業焦點新聞快訊",
    },
}


@dataclass
class SourceItem:
    source_id: str
    name: str
    is_required: bool
    status: str  # legacy status: "ok", "stale", "failed", "missing"
    fetched_at: str
    data_date: Optional[str]
    age_minutes: float
    error_summary: Optional[str]
    fallback_used: bool
    impact_desc: str
    retry_attempts: int = 0
    fetch_status: str = "ok"  # "ok", "failed", "fallback", "missing"
    freshness: str = "fresh"  # "fresh", "stale", "expired"
    combined_status_label: str = "抓取正常・資料新鮮"
    status_badge_class: str = "is-ok"  # "is-ok", "is-caution", "is-danger"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageHealthEvaluation:
    overall_status: str  # "ready", "caution", "unsafe"
    status_label: str  # "可用", "請先確認資料", "不建議依此頁判讀"
    status_badge_class: str  # "is-ready", "is-caution", "is-unsafe"
    summary_reasons: list[str]
    sources: list[dict[str, Any]]
    evaluated_at: str
    is_fallback_page: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def determine_source_dimensions(
    status: str,
    fallback_used: bool,
    age_minutes: float,
    is_required: bool,
) -> tuple[str, str, str, str]:
    """
    Returns (fetch_status, freshness, combined_status_label, status_badge_class)
    """
    if status in ("failed", "error"):
        fetch_status = "failed"
        freshness = "expired" if age_minutes > 1440 else ("stale" if age_minutes > 720 else "fresh")
        return ("failed", freshness, "抓取失敗", "is-danger")
    elif status == "missing":
        return ("missing", "expired", "資料缺失", "is-danger")
    elif fallback_used:
        freshness = "stale" if age_minutes > 720 else "fresh"
        return ("fallback", freshness, "使用備援資料", "is-caution")
    
    # fetch_status is ok
    fetch_status = "ok"
    if age_minutes > 1440:
        freshness = "expired"
        label = "必要・資料嚴重過期" if is_required else "抓取正常・嚴重過期"
        badge = "is-danger"
    elif age_minutes > 720:
        freshness = "stale"
        label = "必要・資料過期" if is_required else "抓取正常・資料過期"
        badge = "is-caution"
    else:
        freshness = "fresh"
        label = "抓取正常・資料新鮮"
        badge = "is-ok"

    return (fetch_status, freshness, label, badge)


def create_empty_source_item(
    source_id: str,
    status: str = "missing",
    error_summary: Optional[str] = None,
    fetched_at: Optional[str] = None,
    fallback_used: bool = False,
    data_date: Optional[str] = None,
) -> SourceItem:
    meta = SOURCES_METADATA.get(source_id, {
        "name": source_id,
        "is_required": False,
        "impact_desc": "無特定影響說明",
    })
    now_iso = fetched_at or datetime.now(TAIPEI).isoformat()
    f_status, freshness, label, badge = determine_source_dimensions(
        status=status,
        fallback_used=fallback_used,
        age_minutes=9999.0 if status == "missing" else 0.0,
        is_required=meta["is_required"],
    )
    return SourceItem(
        source_id=source_id,
        name=meta["name"],
        is_required=meta["is_required"],
        status=status,
        fetched_at=now_iso,
        data_date=data_date,
        age_minutes=0.0,
        error_summary=error_summary,
        fallback_used=fallback_used,
        impact_desc=meta["impact_desc"],
        retry_attempts=0,
        fetch_status=f_status,
        freshness=freshness,
        combined_status_label=label,
        status_badge_class=badge,
    )


def evaluate_source_health(
    status_data: Optional[dict[str, Any]],
    date_check_eval: Optional[dict[str, Any]] = None,
) -> PageHealthEvaluation:
    """
    Evaluates the overall page readiness status given source status data and date check.
    """
    now = datetime.now(TAIPEI)
    now_iso = now.isoformat()

    if not status_data or not isinstance(status_data, dict) or not status_data.get("sources"):
        return PageHealthEvaluation(
            overall_status="caution",
            status_label="請先確認資料",
            status_badge_class="is-caution",
            summary_reasons=["缺少來源狀態紀錄，未能完整稽核健康度"],
            sources=[create_empty_source_item(k).to_dict() for k in SOURCES_METADATA.keys()],
            evaluated_at=now_iso,
            is_fallback_page=True,
        )

    raw_sources = status_data.get("sources", {})
    source_list: list[dict[str, Any]] = []
    reasons: list[str] = []
    has_unsafe_issue = False
    has_caution_issue = False

    # Check date check eval
    if date_check_eval:
        dc_status = date_check_eval.get("status")
        if dc_status == "warning":
            has_unsafe_issue = True
            reasons.append(f"處置資料日期不符：{date_check_eval.get('tooltip', '日期待確認')}")
        elif dc_status == "unknown":
            has_caution_issue = True
            reasons.append("處置資料日期無法完全核對")

    for sid, meta in SOURCES_METADATA.items():
        src_dict = raw_sources.get(sid)
        if not src_dict:
            item = create_empty_source_item(sid, status="missing", error_summary="無此來源資料檔")
        else:
            age_min = float(src_dict.get("age_minutes", 0.0))
            raw_st = src_dict.get("status", "ok")
            fb_used = bool(src_dict.get("fallback_used", False))
            f_status, freshness, label, badge = determine_source_dimensions(
                status=raw_st,
                fallback_used=fb_used,
                age_minutes=age_min,
                is_required=meta["is_required"],
            )
            item = SourceItem(
                source_id=sid,
                name=src_dict.get("name") or meta["name"],
                is_required=meta["is_required"],
                status=raw_st,
                fetched_at=src_dict.get("fetched_at") or now_iso,
                data_date=src_dict.get("data_date"),
                age_minutes=age_min,
                error_summary=src_dict.get("error_summary"),
                fallback_used=fb_used,
                impact_desc=meta["impact_desc"],
                retry_attempts=int(src_dict.get("retry_attempts", 0) or 0),
                fetch_status=f_status,
                freshness=freshness,
                combined_status_label=label,
                status_badge_class=badge,
            )

        source_list.append(item.to_dict())

        # Evaluate criticality
        if item.is_required:
            if item.fetch_status in ("failed", "missing"):
                has_unsafe_issue = True
                reasons.append(f"必要來源【{item.name}】抓取失敗或遺失 ({item.error_summary or '無資料'})")
            elif item.freshness == "expired":
                has_unsafe_issue = True
                reasons.append(f"必要來源【{item.name}】嚴重過期 (距今 {item.age_minutes/60:.1f} 小時)")
            elif item.fallback_used:
                has_caution_issue = True
                reasons.append(f"必要來源【{item.name}】已降級使用近期快取")
            elif item.freshness == "stale":
                has_caution_issue = True
                reasons.append(f"必要來源【{item.name}】資料已逾 12 小時")
        else:
            if item.fetch_status in ("failed", "missing"):
                has_caution_issue = True
                reasons.append(f"次要來源【{item.name}】{item.status} ({item.error_summary or '已使用備援/空資料'})")
            elif item.fallback_used:
                has_caution_issue = True
                reasons.append(f"次要來源【{item.name}】已降級使用本機快照")
            elif item.freshness in ("stale", "expired"):
                has_caution_issue = True
                reasons.append(f"次要來源【{item.name}】資料可能過期")

    if has_unsafe_issue:
        return PageHealthEvaluation(
            overall_status="unsafe",
            status_label="不建議依此頁判讀",
            status_badge_class="is-unsafe",
            summary_reasons=reasons or ["關鍵資料缺失或日期嚴重不符"],
            sources=source_list,
            evaluated_at=now_iso,
        )
    elif has_caution_issue:
        return PageHealthEvaluation(
            overall_status="caution",
            status_label="請先確認資料",
            status_badge_class="is-caution",
            summary_reasons=reasons or ["部分次要資料來源使用備援或已過期"],
            sources=source_list,
            evaluated_at=now_iso,
        )
    else:
        return PageHealthEvaluation(
            overall_status="ready",
            status_label="可用",
            status_badge_class="is-ready",
            summary_reasons=["所有必要與次要資料來源均正常取得且在時限內"],
            sources=source_list,
            evaluated_at=now_iso,
        )


def save_source_status(status_map: dict[str, Any], path: Path | str | None = None) -> None:
    target_path = Path(path) if path else DEFAULT_STATUS_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(TAIPEI).isoformat(),
        "sources": status_map,
    }
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
