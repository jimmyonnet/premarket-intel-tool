"""Deterministic, evidence-first opening forecast model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
import json


TAIPEI = "+08:00"
DEFAULT_THRESHOLD = 100.0
DEFAULT_MODEL_VERSION = "opening-v1"
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "opening_model_v1.json"


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    value: float
    weight: float
    conversion: float
    unit: str
    observed_at: str | None
    fetched_at: str | None
    source_name: str
    source_url: str
    cache_used: bool = False

    @property
    def contribution(self) -> float:
        return self.value * self.weight * self.conversion

    @property
    def supports(self) -> str:
        if self.value > 0:
            return "up"
        if self.value < 0:
            return "down"
        return "neutral"


def load_json(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def direction_for_change(change_points: float | None, threshold: float = DEFAULT_THRESHOLD) -> str:
    """Classify a change; exactly +/- threshold remains flat by product rule."""
    if change_points is None:
        return "unknown"
    if change_points > threshold:
        return "up"
    if change_points < -threshold:
        return "down"
    return "flat"


def gap_label(change_points: float | None, threshold: float = DEFAULT_THRESHOLD) -> str:
    direction = direction_for_change(change_points, threshold)
    return {"up": "gap_up", "down": "gap_down", "flat": "flat"}.get(direction, "unknown")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _item(indices: dict[str, Any], group: str, key: str) -> dict[str, Any]:
    return (indices.get(group) or {}).get(key) or {}


def _make_feature(
    *,
    key: str,
    label: str,
    value: Any,
    weight: Any,
    conversion: Any,
    unit: str,
    observed_at: Any,
    fetched_at: Any,
    source_name: str,
    source_url: str,
    cache_used: bool = False,
) -> Feature | None:
    number = parse_float(value)
    w = parse_float(weight)
    c = parse_float(conversion)
    if number is None or w is None or c is None or w <= 0:
        return None
    return Feature(
        key=key,
        label=label,
        value=number,
        weight=w,
        conversion=c,
        unit=unit,
        observed_at=_iso(observed_at),
        fetched_at=_iso(fetched_at),
        source_name=source_name,
        source_url=source_url,
        cache_used=bool(cache_used),
    )


def extract_features(
    *,
    indices: dict[str, Any],
    night: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[Feature], list[str]]:
    configured = config.get("features") or {}
    missing: list[str] = []
    features: list[Feature] = []

    night_latest = night.get("latest") or {}
    night_value = night_latest.get("change")
    if night_value is None:
        night_value = parse_float(night.get("latest_change"))
    night_source = str(night.get("provider_name") or night_latest.get("provider_name") or "TAIFEX/Wantgoo")
    night_time = night_latest.get("collected_at") or night.get("collected_at")
    feature = _make_feature(
        key="night_session_points",
        label=str((configured.get("night_session_points") or {}).get("label") or "台指期夜盤點數變化"),
        value=night_value,
        weight=(configured.get("night_session_points") or {}).get("weight"),
        conversion=(configured.get("night_session_points") or {}).get("conversion"),
        unit="points",
        observed_at=night_time,
        fetched_at=night_time,
        source_name=night_source,
        source_url="https://www.wantgoo.com/futures/wtxp",
        cache_used=bool(night.get("_fallback_used") or night_latest.get("fallback_used")),
    )
    if feature:
        features.append(feature)
    else:
        missing.append("night_session_points")

    index_specs = (
        ("nasdaq_pct", "nasdaq", "NASDAQ 漲跌幅", "https://finance.yahoo.com/quote/%5EIXIC/"),
        ("sp500_pct", "sp500", "S&P 500 漲跌幅", "https://finance.yahoo.com/quote/%5EGSPC/"),
        ("dow_pct", "dow", "道瓊漲跌幅", "https://finance.yahoo.com/quote/%5EDJI/"),
    )
    for config_key, item_key, fallback_label, url in index_specs:
        item = _item(indices, "us_indices", item_key)
        spec = configured.get(config_key) or {}
        feature = _make_feature(
            key=config_key,
            label=str(spec.get("label") or fallback_label),
            value=item.get("change_pct"),
            weight=spec.get("weight"),
            conversion=spec.get("conversion"),
            unit="percent",
            observed_at=item.get("updated_at") or item.get("updated_taipei"),
            fetched_at=item.get("updated_at") or item.get("updated_taipei"),
            source_name=str(item.get("source_label") or "Yahoo Finance Chart"),
            source_url=str(item.get("source_url") or url),
            cache_used=bool(item.get("cache_used") or item.get("fallback_used")),
        )
        if feature:
            features.append(feature)
        else:
            missing.append(config_key)
    return features, missing


def _evidence(feature: Feature, index: int) -> dict[str, Any]:
    return {
        "evidence_id": f"opening-{feature.key}-{index}",
        "kind": "market_data",
        "label": feature.label,
        "value": round(feature.value, 6),
        "unit": feature.unit,
        "observed_at": feature.observed_at,
        "fetched_at": feature.fetched_at,
        "source_name": feature.source_name,
        "source_url": feature.source_url,
        "cache_used": feature.cache_used,
        "conflict_group": "market-signal",
        "supports": feature.supports,
    }


def _previous_close(
    twse: dict[str, Any],
    taiex_reference: dict[str, Any] | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """Return the close and provenance used as the opening baseline.

    The official historical TWSE adapter is preferred.  The legacy snapshot
    remains a compatibility fallback so a missing official response does not
    crash the page, but the caller marks that forecast low-confidence.
    """
    reference = taiex_reference if isinstance(taiex_reference, dict) else {}
    if reference.get("status") == "ok":
        value = parse_float(reference.get("previous_close"))
        source = reference.get("source") if isinstance(reference.get("source"), dict) else {}
        if value is not None:
            return value, {
                "label": "前一交易日加權指數收盤（TWSE 官方歷史資料）",
                "source_name": source.get("name") or "TWSE TAIEX historical index",
                "source_url": source.get("url") or "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST",
                "observed_at": source.get("observed_at"),
                "fetched_at": source.get("fetched_at"),
                "official": True,
                "cache_used": False,
            }

    twii = twse.get("twii") or {}
    for key in ("previous_close", "prev_close", "chart_previous_close"):
        value = parse_float(twii.get(key))
        if value is not None:
            return value, {
                "label": "前一交易日加權指數收盤（既有快照欄位）",
                "source_name": "既有 TWII 快照（compatibility fallback）",
                "source_url": "https://query2.finance.yahoo.com/v8/finance/chart/^TWII?interval=1d&range=1d",
                "observed_at": twii.get("updated_at") or twse.get("collected_at"),
                "fetched_at": twse.get("collected_at"),
                "official": False,
                "cache_used": bool(twse.get("_fallback_used") or twii.get("fallback_used")),
            }
    value = parse_float(twii.get("price"))
    return value, {
        "label": "前一交易日加權指數收盤（既有快照欄位）",
        "source_name": "既有 TWII 快照（compatibility fallback）",
        "source_url": "https://query2.finance.yahoo.com/v8/finance/chart/^TWII?interval=1d&range=1d",
        "observed_at": twii.get("updated_at") or twse.get("collected_at"),
        "fetched_at": twse.get("collected_at"),
        "official": False,
        "cache_used": bool(twse.get("_fallback_used") or twii.get("fallback_used")),
    }


def build_forecast(
    *,
    market_date: str,
    locked_at: str,
    indices: dict[str, Any],
    night: dict[str, Any],
    twse: dict[str, Any],
    taiex_reference: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    prediction_id: str | None = None,
) -> dict[str, Any]:
    config = config or load_json(DEFAULT_CONFIG, {}) or {}
    model_version = str(config.get("model_version") or DEFAULT_MODEL_VERSION)
    threshold = float(config.get("direction_threshold_points") or DEFAULT_THRESHOLD)
    previous_close, previous_close_source = _previous_close(twse, taiex_reference)
    features, missing = extract_features(indices=indices, night=night, config=config)
    if previous_close is None:
        missing.append("previous_close")
    elif not previous_close_source.get("official"):
        missing.append("official_previous_close")
    total_weight = sum(feature.weight for feature in features)
    predicted_change = None
    if features and total_weight > 0:
        predicted_change = sum(feature.contribution for feature in features) / total_weight
        limit = float(config.get("max_abs_prediction_points") or 800)
        predicted_change = max(-limit, min(limit, predicted_change))
        predicted_change = round(predicted_change, 2)
    predicted_open = round(previous_close + predicted_change, 2) if previous_close is not None and predicted_change is not None else None

    signal_directions = {feature.supports for feature in features if feature.supports in {"up", "down"}}
    conflicts = ["market-signal:up_vs_down"] if len(signal_directions) > 1 else []
    cache_used = any(feature.cache_used for feature in features)
    if missing or conflicts or cache_used:
        confidence = "low"
    elif not features or previous_close is None:
        confidence = "low"
    elif len(signal_directions) == 1 and all(feature.supports in {"up", "down"} for feature in features):
        confidence = "high"
    else:
        confidence = "medium"

    direction = direction_for_change(predicted_change, threshold)
    evidence = [_evidence(feature, index) for index, feature in enumerate(features, start=1)]
    if previous_close is not None:
        evidence.insert(0, {
            "evidence_id": "opening-twse-previous-close",
            "kind": "market_data",
            "label": previous_close_source.get("label"),
            "value": round(previous_close, 2),
            "unit": "index_points",
            "observed_at": previous_close_source.get("observed_at"),
            "fetched_at": previous_close_source.get("fetched_at") or locked_at,
            "source_name": previous_close_source.get("source_name"),
            "source_url": previous_close_source.get("source_url"),
            "cache_used": bool(previous_close_source.get("cache_used")),
            "conflict_group": None,
            "supports": "neutral",
        })

    confidence_reasons: list[str] = []
    if missing:
        confidence_reasons.append("缺少：" + "、".join(missing))
    if conflicts:
        confidence_reasons.append("市場訊號互相矛盾：上漲與下跌訊號同時存在")
    if cache_used:
        confidence_reasons.append("部分資料沿用快取")
    if not confidence_reasons:
        confidence_reasons.append("關鍵市場資料均已取得，訊號一致性良好" if confidence == "high" else "資料可用，但市場訊號包含中性或混合方向")

    if predicted_change is None:
        status = "input_incomplete"
    else:
        status = "generated"
    return {
        "schema_version": "opening-forecast.v1",
        "prediction_id": prediction_id or f"{market_date}T08:30+08:00-{model_version}",
        "market_date": market_date,
        "status": status,
        "locked_at": locked_at,
        "model_version": model_version,
        "previous_close": previous_close,
        "predicted_change_points": predicted_change,
        "predicted_open": predicted_open,
        "direction": direction,
        "gap_label": gap_label(predicted_change, threshold),
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "evidence": evidence,
        "data_quality": {
            "missing_factors": missing,
            "conflicts": conflicts,
            "cache_used": cache_used,
        },
        "formula": {
            "threshold_points": threshold,
            "available_weight": round(total_weight, 6),
            "features": [
                {
                    "key": feature.key,
                    "weight": feature.weight,
                    "conversion": feature.conversion,
                    "input": feature.value,
                    "contribution": round(feature.contribution, 4),
                }
                for feature in features
            ],
        },
    }


def load_model_config(path: str | Path | None = None) -> dict[str, Any]:
    return load_json(path or DEFAULT_CONFIG, {}) or {}
