"""Evaluate verified opening forecasts without changing model weights."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


MINIMUM_VERIFIED_DAYS = 20


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def verified_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only complete verified records; unverified days never enter metrics."""
    result = []
    for record in records:
        if record.get("status") != "verified":
            continue
        if record.get("direction_correct") is None:
            continue
        error = _number(record.get("absolute_error_points"))
        if error is None:
            continue
        result.append(record)
    return result


def _stats(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    correct = sum(bool(row.get("direction_correct")) for row in records)
    errors = [_number(row.get("absolute_error_points")) for row in records]
    errors = [value for value in errors if value is not None]
    return {
        "sample_days": len(records),
        "direction_correct": correct,
        "direction_accuracy": round(correct / len(records), 4),
        "mean_absolute_error_points": round(sum(errors) / len(errors), 2) if errors else None,
    }


def evaluate(records: Iterable[dict[str, Any]], *, model_version: str | None = None) -> dict[str, Any]:
    verified = verified_records(records)
    confidence_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in verified:
        confidence_groups[str(record.get("confidence") or "unknown")].append(record)
    status = "ready" if len(verified) >= MINIMUM_VERIFIED_DAYS else "warmup"
    return {
        "schema_version": "learning-status.v1",
        "status": status,
        "model_version": model_version,
        "verified_days": len(verified),
        "required_days": MINIMUM_VERIFIED_DAYS,
        "stats": _stats(verified) if status == "ready" else None,
        "confidence_breakdown": {
            key: _stats(value)
            for key, value in sorted(confidence_groups.items())
        },
        "pending_proposal": None,
        "manual_pause_remaining_days": 0,
        "last_change": None,
        "message": (
            "學習資料累積中，滿 20 個已驗證交易日後才顯示正式統計"
            if status == "warmup"
            else "已完成至少 20 個已驗證交易日，可進行模型版本比較"
        ),
    }
