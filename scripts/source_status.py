"""Source reliability metadata and page-health evaluation.

The fetch runner and the rendered health panel share this catalog.  Keeping
reliability, freshness, fallback and notification policy in one module avoids
source-specific magic numbers drifting between jobs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_STATUS_PATH = Path(__file__).parent.parent / "data" / "latest" / "source_status.json"

RELIABILITY_TIERS: dict[str, dict[str, Any]] = {
    "core_stable": {
        "label": "核心穩定",
        "default_ttl_minutes": 720,
        "default_hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning",
        "notification_level": "critical",
    },
    "important_short_stale": {
        "label": "重要但可短暫過期",
        "default_ttl_minutes": 360,
        "default_hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning",
        "notification_level": "warning",
    },
    "high_risk": {
        "label": "高風險來源",
        "default_ttl_minutes": 180,
        "default_hard_expiry_minutes": 720,
        "fallback_policy": "fixture_or_previous_snapshot_with_warning",
        "notification_level": "notice",
    },
}

# Source definition catalog.  ``is_required`` remains the page-readiness
# compatibility flag; reliability tier independently controls freshness policy.
SOURCES_METADATA: dict[str, dict[str, Any]] = {
    "indices": {
        "name": "指數行情 (美股/亞股/ADR)", "is_required": True,
        "reliability_tier": "core_stable", "ttl_minutes": 720, "hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "critical", "dependencies": [],
        "impact_desc": "無法掌握美股收盤與日韓開盤走勢，難以評估早盤開盤連動方向",
    },
    "disposal": {
        "name": "處置股與出關預警", "is_required": True,
        "reliability_tier": "core_stable", "ttl_minutes": 720, "hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "critical", "dependencies": [],
        "impact_desc": "無法取得即時處置管制標準與出關名單，無法進行風險避險",
    },
    "twse_summary": {
        "name": "大盤昨收與三大法人", "is_required": False,
        "reliability_tier": "core_stable", "ttl_minutes": 720, "hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "warning", "dependencies": [],
        "impact_desc": "缺少昨日加權指數與外資/投信買賣超金額彙整",
    },
    "night_session": {
        "name": "台指期夜盤走勢", "is_required": False,
        "reliability_tier": "important_short_stale", "ttl_minutes": 180, "hard_expiry_minutes": 720,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "warning", "dependencies": [],
        "impact_desc": "缺少期貨夜盤行情與點位走向，可改參考美股指數",
    },
    "pressplay": {
        "name": "PressPlay 盤前族群與標的", "is_required": False,
        "reliability_tier": "high_risk", "ttl_minutes": 360, "hard_expiry_minutes": 720,
        "fallback_policy": "fixture_or_previous_snapshot_with_warning", "notification_level": "notice", "dependencies": [],
        "impact_desc": "缺少每日專欄族群整理，候選股清單將呈現空白",
    },
    "chengwaye_daily": {
        "name": "主力券商與當沖籌碼明細", "is_required": False,
        "reliability_tier": "high_risk", "ttl_minutes": 360, "hard_expiry_minutes": 720,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "notice", "dependencies": ["pressplay"],
        "impact_desc": "缺少重點個股之分點買賣與當沖籌碼排行",
    },
    "chengwaye_stock_history": {
        "name": "Chengwaye 個股漲停履歷", "is_required": False,
        "reliability_tier": "high_risk", "ttl_minutes": 1440, "hard_expiry_minutes": 2880,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "notice", "dependencies": ["pressplay", "chengwaye_daily"],
        "impact_desc": "缺少候選股漲停次數、最近漲停與隔日表現履歷",
    },
    "calendar": {
        "name": "總經財經行事曆", "is_required": False,
        "reliability_tier": "important_short_stale", "ttl_minutes": 720, "hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "warning", "dependencies": [],
        "impact_desc": "缺少今日重磅總經數據與事件日程倒數",
    },
    "financials": {
        "name": "市場未反映重大公告 (財報/營收/處分)", "is_required": False,
        "reliability_tier": "important_short_stale", "ttl_minutes": 720, "hard_expiry_minutes": 1440,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "warning", "dependencies": [],
        "impact_desc": "缺少昨日盤後自結損益與營收公告統計",
    },
    "news": {
        "name": "盤前即時新聞聚合", "is_required": False,
        "reliability_tier": "high_risk", "ttl_minutes": 180, "hard_expiry_minutes": 720,
        "fallback_policy": "previous_snapshot_with_warning", "notification_level": "notice", "dependencies": [],
        "impact_desc": "缺少隔夜美股與產業焦點新聞快訊",
    },
}


@dataclass
class SourceItem:
    source_id: str
    name: str
    is_required: bool
    status: str
    fetched_at: str
    data_date: Optional[str]
    age_minutes: float
    error_summary: Optional[str]
    fallback_used: bool
    impact_desc: str
    retry_attempts: int = 0
    fetch_status: str = "ok"
    freshness: str = "fresh"
    combined_status_label: str = "抓取正常・資料新鮮"
    status_badge_class: str = "is-ok"
    reliability_tier: str = "important_short_stale"
    reliability_label: str = "重要但可短暫過期"
    ttl_minutes: int = 720
    hard_expiry_minutes: int = 1440
    fallback_policy: str = "previous_snapshot_with_warning"
    notification_level: str = "warning"
    dependencies: list[str] = field(default_factory=list)
    notification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageHealthEvaluation:
    overall_status: str
    status_label: str
    status_badge_class: str
    summary_reasons: list[str]
    sources: list[dict[str, Any]]
    evaluated_at: str
    is_fallback_page: bool = False
    notifications: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_policy(source_id: str) -> dict[str, Any]:
    meta = SOURCES_METADATA.get(source_id)
    if meta:
        return meta
    tier = RELIABILITY_TIERS["important_short_stale"]
    return {
        "name": source_id,
        "is_required": False,
        "reliability_tier": "important_short_stale",
        "ttl_minutes": tier["default_ttl_minutes"],
        "hard_expiry_minutes": tier["default_hard_expiry_minutes"],
        "fallback_policy": tier["fallback_policy"],
        "notification_level": tier["notification_level"],
        "dependencies": [],
        "impact_desc": "無特定影響說明",
    }


def determine_source_dimensions(
    status: str,
    fallback_used: bool,
    age_minutes: float,
    is_required: bool,
    ttl_minutes: int = 720,
    hard_expiry_minutes: int = 1440,
) -> tuple[str, str, str, str]:
    """Return fetch status, freshness, human label and CSS badge class."""
    ttl = max(1, int(ttl_minutes))
    hard_expiry = max(ttl, int(hard_expiry_minutes))
    if status in ("failed", "error"):
        freshness = "expired" if age_minutes > hard_expiry else ("stale" if age_minutes > ttl else "fresh")
        return ("failed", freshness, "抓取失敗", "is-danger")
    if status == "missing":
        return ("missing", "expired", "資料缺失", "is-danger")
    if fallback_used:
        freshness = "expired" if age_minutes > hard_expiry else ("stale" if age_minutes > ttl else "fresh")
        return ("fallback", freshness, "使用備援資料", "is-caution")

    if age_minutes > hard_expiry:
        freshness = "expired"
        label = "必要・資料嚴重過期" if is_required else "抓取正常・嚴重過期"
        badge = "is-danger"
    elif age_minutes > ttl:
        freshness = "stale"
        label = "必要・資料過期" if is_required else "抓取正常・資料過期"
        badge = "is-caution"
    else:
        freshness = "fresh"
        label = "抓取正常・資料新鮮"
        badge = "is-ok"
    return ("ok", freshness, label, badge)


def _item_from_raw(source_id: str, src_dict: dict[str, Any], now_iso: str) -> SourceItem:
    meta = source_policy(source_id)
    age_min = float(src_dict.get("age_minutes", 0.0) or 0.0)
    raw_status = str(src_dict.get("status", "ok"))
    fallback_used = bool(src_dict.get("fallback_used", False))
    ttl = int(src_dict.get("ttl_minutes", meta["ttl_minutes"]) or meta["ttl_minutes"])
    hard_expiry = int(src_dict.get("hard_expiry_minutes", meta["hard_expiry_minutes"]) or meta["hard_expiry_minutes"])
    fetch_status, freshness, label, badge = determine_source_dimensions(
        raw_status, fallback_used, age_min, bool(meta["is_required"]), ttl, hard_expiry
    )
    notification = src_dict.get("notification")
    if not notification and (fetch_status in ("failed", "missing") or freshness in ("stale", "expired") or fallback_used):
        notification = f"{meta['notification_level']}: {src_dict.get('error_summary') or label}"
    return SourceItem(
        source_id=source_id,
        name=src_dict.get("name") or meta["name"],
        is_required=bool(meta["is_required"]),
        status=raw_status,
        fetched_at=src_dict.get("fetched_at") or now_iso,
        data_date=src_dict.get("data_date"),
        age_minutes=age_min,
        error_summary=src_dict.get("error_summary"),
        fallback_used=fallback_used,
        impact_desc=meta["impact_desc"],
        retry_attempts=int(src_dict.get("retry_attempts", 0) or 0),
        fetch_status=fetch_status,
        freshness=freshness,
        combined_status_label=label,
        status_badge_class=badge,
        reliability_tier=meta["reliability_tier"],
        reliability_label=RELIABILITY_TIERS[meta["reliability_tier"]]["label"],
        ttl_minutes=ttl,
        hard_expiry_minutes=hard_expiry,
        fallback_policy=meta["fallback_policy"],
        notification_level=meta["notification_level"],
        dependencies=list(meta.get("dependencies", [])),
        notification=notification,
    )


def create_empty_source_item(
    source_id: str,
    status: str = "missing",
    error_summary: Optional[str] = None,
    fetched_at: Optional[str] = None,
    fallback_used: bool = False,
    data_date: Optional[str] = None,
) -> SourceItem:
    now_iso = fetched_at or datetime.now(TAIPEI).isoformat()
    meta = source_policy(source_id)
    return _item_from_raw(source_id, {
        "status": status, "error_summary": error_summary, "fetched_at": now_iso,
        "fallback_used": fallback_used, "data_date": data_date,
        "age_minutes": 9999.0 if status == "missing" else 0.0,
    }, now_iso)


def evaluate_source_health(
    status_data: Optional[dict[str, Any]],
    date_check_eval: Optional[dict[str, Any]] = None,
) -> PageHealthEvaluation:
    """Evaluate readiness and produce machine-readable notification metadata."""
    now_iso = datetime.now(TAIPEI).isoformat()
    if not status_data or not isinstance(status_data, dict) or not status_data.get("sources"):
        return PageHealthEvaluation(
            overall_status="caution", status_label="請先確認資料", status_badge_class="is-caution",
            summary_reasons=["缺少來源狀態紀錄，未能完整稽核健康度"],
            sources=[create_empty_source_item(k).to_dict() for k in SOURCES_METADATA],
            evaluated_at=now_iso, is_fallback_page=True,
            notifications=[{"level": "critical", "source_id": "source_status", "message": "缺少來源狀態紀錄"}],
        )

    raw_sources = status_data.get("sources", {})
    source_list: list[dict[str, Any]] = []
    reasons: list[str] = []
    notifications: list[dict[str, Any]] = []
    has_unsafe_issue = False
    has_caution_issue = False

    if date_check_eval:
        dc_status = date_check_eval.get("status")
        if dc_status == "warning":
            has_unsafe_issue = True
            reasons.append(f"處置資料日期不符：{date_check_eval.get('tooltip', '日期待確認')}")
            notifications.append({"level": "critical", "source_id": "disposal", "message": reasons[-1]})
        elif dc_status == "unknown":
            has_caution_issue = True
            reasons.append("處置資料日期無法完全核對")
            notifications.append({"level": "warning", "source_id": "disposal", "message": reasons[-1]})

    for sid, meta in SOURCES_METADATA.items():
        src_dict = raw_sources.get(sid)
        if not isinstance(src_dict, dict):
            item = create_empty_source_item(sid, status="missing", error_summary="無此來源資料檔")
        else:
            item = _item_from_raw(sid, src_dict, now_iso)
        source_list.append(item.to_dict())

        issue: str | None = None
        if item.is_required:
            if item.fetch_status in ("failed", "missing"):
                has_unsafe_issue = True
                issue = f"必要來源【{item.name}】抓取失敗或遺失 ({item.error_summary or '無資料'})"
            elif item.freshness == "expired":
                has_unsafe_issue = True
                issue = f"必要來源【{item.name}】嚴重過期 (距今 {item.age_minutes/60:.1f} 小時)"
            elif item.fallback_used:
                has_caution_issue = True
                issue = f"必要來源【{item.name}】已降級使用近期快取"
            elif item.freshness == "stale":
                has_caution_issue = True
                issue = f"必要來源【{item.name}】資料已逾 TTL {item.ttl_minutes} 分鐘"
        else:
            if item.fetch_status in ("failed", "missing"):
                has_caution_issue = True
                issue = f"次要來源【{item.name}】{item.status} ({item.error_summary or '已使用備援/空資料'})"
            elif item.fallback_used:
                has_caution_issue = True
                issue = f"次要來源【{item.name}】已降級使用本機快照"
            elif item.freshness in ("stale", "expired"):
                has_caution_issue = True
                issue = f"次要來源【{item.name}】資料已超過 TTL {item.ttl_minutes} 分鐘"
        if issue:
            reasons.append(issue)
            notifications.append({"level": item.notification_level, "source_id": sid, "message": issue})

    if has_unsafe_issue:
        overall_status, label, badge = "unsafe", "不建議依此頁判讀", "is-unsafe"
    elif has_caution_issue:
        overall_status, label, badge = "caution", "請先確認資料", "is-caution"
    else:
        overall_status, label, badge = "ready", "可用", "is-ready"
    return PageHealthEvaluation(
        overall_status=overall_status,
        status_label=label,
        status_badge_class=badge,
        summary_reasons=reasons or ["所有必要與次要資料來源均正常取得且在時限內"],
        sources=source_list,
        evaluated_at=now_iso,
        notifications=notifications,
    )


def save_source_status(status_map: dict[str, Any], path: Path | str | None = None) -> None:
    target_path = Path(path) if path else DEFAULT_STATUS_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps({
        "schema_version": "source-status.v2",
        "updated_at": datetime.now(TAIPEI).isoformat(),
        "reliability_tiers": RELIABILITY_TIERS,
        "sources": status_map,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
