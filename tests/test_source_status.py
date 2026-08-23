from datetime import datetime, timezone, timedelta
import pytest

from scripts.source_status import (
    evaluate_source_health,
    create_empty_source_item,
    PageHealthEvaluation,
    SOURCES_METADATA,
)

TAIPEI = timezone(timedelta(hours=8))


def test_source_health_all_ok_is_ready():
    """When all required and optional sources are ok and recent, overall status is 'ready'."""
    now_iso = datetime.now(TAIPEI).isoformat()
    sources = {}
    for sid, meta in SOURCES_METADATA.items():
        sources[sid] = {
            "source_id": sid,
            "name": meta["name"],
            "is_required": meta["is_required"],
            "status": "ok",
            "fetched_at": now_iso,
            "data_date": "08/24",
            "age_minutes": 5.0,
            "error_summary": None,
            "fallback_used": False,
            "impact_desc": meta["impact_desc"],
        }

    date_check_eval = {
        "status": "aligned_next",
        "label": "已對齊次日",
        "class_name": "is-ok",
        "tooltip": "資料日期已對齊",
    }

    eval_res = evaluate_source_health({"sources": sources}, date_check_eval)
    assert eval_res.overall_status == "ready"
    assert eval_res.status_label == "可用"
    assert eval_res.status_badge_class == "is-ready"
    assert len(eval_res.sources) == len(SOURCES_METADATA)


def test_source_health_optional_failure_is_caution():
    """When optional sources fail or use fallback, overall status is 'caution'."""
    now_iso = datetime.now(TAIPEI).isoformat()
    sources = {}
    for sid, meta in SOURCES_METADATA.items():
        sources[sid] = {
            "source_id": sid,
            "name": meta["name"],
            "is_required": meta["is_required"],
            "status": "ok",
            "fetched_at": now_iso,
            "data_date": "08/24",
            "age_minutes": 5.0,
            "error_summary": None,
            "fallback_used": False,
            "impact_desc": meta["impact_desc"],
        }

    # Non-required source failure (e.g. pressplay login failed)
    sources["pressplay"]["status"] = "failed"
    sources["pressplay"]["fallback_used"] = True
    sources["pressplay"]["error_summary"] = "登入失敗"

    eval_res = evaluate_source_health({"sources": sources})
    assert eval_res.overall_status == "caution"
    assert eval_res.status_label == "請先確認資料"
    assert eval_res.status_badge_class == "is-caution"
    assert any("PressPlay" in r for r in eval_res.summary_reasons)


def test_source_health_required_failure_is_unsafe():
    """When a required source fails (e.g. indices or disposal), overall status is 'unsafe'."""
    now_iso = datetime.now(TAIPEI).isoformat()
    sources = {}
    for sid, meta in SOURCES_METADATA.items():
        sources[sid] = {
            "source_id": sid,
            "name": meta["name"],
            "is_required": meta["is_required"],
            "status": "ok",
            "fetched_at": now_iso,
            "data_date": "08/24",
            "age_minutes": 5.0,
            "error_summary": None,
            "fallback_used": False,
            "impact_desc": meta["impact_desc"],
        }

    # Required source indices fails
    sources["indices"]["status"] = "failed"
    sources["indices"]["error_summary"] = "Yahoo Finance 連線逾時"

    eval_res = evaluate_source_health({"sources": sources})
    assert eval_res.overall_status == "unsafe"
    assert eval_res.status_label == "不建議依此頁判讀"
    assert eval_res.status_badge_class == "is-unsafe"
    assert any("必要來源" in r and "指數行情" in r for r in eval_res.summary_reasons)


def test_source_health_date_mismatch_is_unsafe():
    """When disposal date check is warning/mismatched, overall status is 'unsafe'."""
    now_iso = datetime.now(TAIPEI).isoformat()
    sources = {
        sid: {
            "source_id": sid,
            "name": meta["name"],
            "is_required": meta["is_required"],
            "status": "ok",
            "fetched_at": now_iso,
            "data_date": "08/20",
            "age_minutes": 5.0,
            "error_summary": None,
            "fallback_used": False,
            "impact_desc": meta["impact_desc"],
        }
        for sid, meta in SOURCES_METADATA.items()
    }

    date_check_eval = {
        "status": "warning",
        "label": "日期異常",
        "class_name": "is-danger",
        "tooltip": "處置資料日期與目標交易日不符",
    }

    eval_res = evaluate_source_health({"sources": sources}, date_check_eval)
    assert eval_res.overall_status == "unsafe"
    assert any("處置資料日期不符" in r for r in eval_res.summary_reasons)


def test_source_health_missing_file_degrades_to_caution():
    """When source_status.json is missing, degrades gracefully to caution."""
    eval_res = evaluate_source_health(None)
    assert eval_res.overall_status == "caution"
    assert eval_res.is_fallback_page is True
    assert any("缺少來源狀態紀錄" in r for r in eval_res.summary_reasons)


def test_source_health_dual_dimensions_stale():
    """Test dual-dimension status fields (fetch_status=ok, freshness=stale)."""
    now_iso = datetime.now(TAIPEI).isoformat()
    sources = {
        sid: {
            "source_id": sid,
            "name": meta["name"],
            "is_required": meta["is_required"],
            "status": "ok",
            "fetched_at": now_iso,
            "data_date": "08/24",
            "age_minutes": 800.0,  # > 12 hours (stale)
            "error_summary": None,
            "fallback_used": False,
            "impact_desc": meta["impact_desc"],
        }
        for sid, meta in SOURCES_METADATA.items()
    }

    eval_res = evaluate_source_health({"sources": sources})
    assert eval_res.overall_status == "caution"
    indices_item = next(s for s in eval_res.sources if s["source_id"] == "indices")
    assert indices_item["fetch_status"] == "ok"
    assert indices_item["freshness"] == "stale"
    assert indices_item["combined_status_label"] == "必要・資料過期"
    assert indices_item["status_badge_class"] == "is-caution"

