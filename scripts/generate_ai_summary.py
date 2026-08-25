#!/usr/bin/env python3
"""Generate optional AI briefing data for the static Premarket Intel page.

The script is deliberately best-effort. Deterministic market/news facts and
quality checks are always generated locally; Gemini only writes narrative text
and topic summaries. If GEMINI_API_KEY is absent, the output remains useful and
marked as a deterministic fallback instead of failing the page build.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_MODEL = "gemini-2.5-flash"
TOPIC_LABELS = {
    "geopolitics_trade": "地緣政治／貿易",
    "currency_commodities": "美元／債券／商品",
    "macro_policy": "總經／央行政策",
    "global_market": "美股／全球市場",
    "taiwan_market": "台股市場",
    "asia_market": "亞股市場",
    "sector_technology": "科技／產業",
    "company_earnings": "公司／財報",
    "market_structure": "市場結構／資金",
    "other": "其他",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "news_summary": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "topic_summary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "count": {"type": "integer", "minimum": 0},
                            "summary": {"type": "string"},
                        },
                        "required": ["topic", "count", "summary"],
                        "additionalProperties": False,
                    },
                    "maxItems": 8,
                },
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
            },
            "required": ["headline", "topic_summary", "key_points"],
            "additionalProperties": False,
        },
        "market_summary": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "bullets": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "risks": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
            },
            "required": ["headline", "bullets", "risks"],
            "additionalProperties": False,
        },
        "quality_note": {"type": "string"},
    },
    "required": ["news_summary", "market_summary", "quality_note"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """你是繁體中文的盤前研究助理。只能根據使用者提供的 INPUT JSON 撰寫整理，不能補造不存在的價格、漲跌幅、時間、公司、政策或新聞事實。\n\n規則：\n1. 新聞重點只能引用 INPUT 的新聞標題與欄位；不要把推測寫成已發生的事。\n2. 市場總結只能引用 INPUT 的行情數字與時間；若資料缺失，明確寫「資料未提供」。\n3. 不要提供買賣指令、目標價或投資保證。\n4. 以簡潔的繁體中文輸出；headline 一句，bullets 與 risks 各不超過 4 點。\n5. topic_summary 的 topic 必須使用 INPUT 已提供的 primary_topic 名稱，count 必須符合新聞筆數。\n6. 輸出必須符合指定 JSON schema。"""


def load_json(path: str | Path, default: Any) -> Any:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def now_iso() -> str:
    return datetime.now(TAIPEI).isoformat()


def finite_number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(str(value).replace(",", "").strip())
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def quote_rows(indices: dict[str, Any], night: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = (
        ("us_indices", "美股指數"),
        ("adrs", "ADR／跨海標的"),
        ("asia_open", "亞股"),
    )
    for key, group_label in groups:
        group = indices.get(key) if isinstance(indices, dict) else {}
        if not isinstance(group, dict):
            continue
        for item_key, raw in group.items():
            if not isinstance(raw, dict):
                continue
            value = raw.get("value", raw.get("price"))
            change_pct = raw.get("change_pct")
            if value is None and raw.get("change") is None:
                continue
            rows.append({
                "group": group_label,
                "name": clean_text(raw.get("name"), str(item_key)),
                "ticker": clean_text(raw.get("ticker"), str(item_key)),
                "value": value,
                "change": raw.get("change"),
                "change_pct": change_pct,
                "updated_at": raw.get("updated_at") or raw.get("updated_taipei"),
            })
    latest = night.get("latest") if isinstance(night, dict) else {}
    if isinstance(latest, dict) and latest.get("price") is not None:
        rows.append({
            "group": "台指期夜盤",
            "name": "台指期夜盤",
            "ticker": "TXF",
            "value": latest.get("price"),
            "change": latest.get("change"),
            "change_pct": latest.get("change_pct"),
            "updated_at": latest.get("collected_at") or night.get("date"),
        })
    return rows


def news_rows(news: Any) -> list[dict[str, Any]]:
    items = news.get("items", []) if isinstance(news, dict) else news
    if not isinstance(items, list):
        return []
    rows = []
    for index, item in enumerate(items[:10], 1):
        if not isinstance(item, dict):
            continue
        rows.append({
            "index": index,
            "title": clean_text(item.get("title"), "未提供標題"),
            "source": clean_text(item.get("source"), "來源未提供"),
            "time": clean_text(item.get("time"), "時間未提供"),
            "primary_topic": clean_text(item.get("primary_topic"), "other"),
            "topic_groups": item.get("topic_groups") if isinstance(item.get("topic_groups"), list) else [],
            "named_entities": item.get("named_entities") if isinstance(item.get("named_entities"), list) else [],
            "score": item.get("score"),
        })
    return rows


def deterministic_quality(news: list[dict[str, Any]], quotes: list[dict[str, Any]], source_status: Any) -> dict[str, Any]:
    topics = Counter(item["primary_topic"] for item in news)
    entities = Counter(entity for item in news for entity in item.get("named_entities", []))
    sources = Counter(item["source"] for item in news)
    issues: list[dict[str, str]] = []
    if len(news) < 5:
        issues.append({"severity": "warning", "message": f"合格新聞僅 {len(news)} 則，摘要覆蓋面有限"})
    if len(topics) < 3 and news:
        issues.append({"severity": "warning", "message": f"新聞主題只有 {len(topics)} 類，需留意題材集中"})
    if len(sources) < 2 and news:
        issues.append({"severity": "warning", "message": f"新聞來源只有 {len(sources)} 家，需留意單一來源偏誤"})
    if entities.get("nvidia", 0) > 3:
        issues.append({"severity": "warning", "message": "輝達相關新聞超過 3 則，需檢查多樣性上限"})
    if not quotes:
        issues.append({"severity": "warning", "message": "目前沒有可供比對的市場行情"})

    status_sources = source_status.get("sources", []) if isinstance(source_status, dict) else []
    if isinstance(status_sources, list):
        for source in status_sources:
            if not isinstance(source, dict):
                continue
            source_name = clean_text(source.get("name"), source.get("source_id", "資料來源"))
            if source.get("status") in ("failed", "missing"):
                issues.append({"severity": "error", "message": f"{source_name} 抓取失敗或缺失"})
            elif source.get("fallback_used") or source.get("status") == "warning":
                issues.append({"severity": "warning", "message": f"{source_name} 使用備援資料或有警告"})

    checks = [
        {"name": "新聞數量", "status": "ok" if len(news) >= 5 else "attention", "detail": f"{len(news)} 則"},
        {"name": "主題分布", "status": "ok" if len(topics) >= 3 else "attention", "detail": f"{len(topics)} 類"},
        {"name": "公司／事件集中度", "status": "ok" if entities.get("nvidia", 0) <= 3 else "attention", "detail": f"輝達 {entities.get('nvidia', 0)} 則"},
        {"name": "行情可用性", "status": "ok" if quotes else "attention", "detail": f"{len(quotes)} 筆可比對行情"},
        {"name": "來源健康度", "status": "ok" if not any(i["severity"] == "error" for i in issues) else "attention", "detail": f"{len(issues)} 項提醒"},
    ]
    return {
        "status": "attention" if issues else "ok",
        "label": "需要留意" if issues else "資料正常",
        "checks": checks,
        "issues": issues[:8],
        "news_count": len(news),
        "unique_topics": len(topics),
        "unique_sources": len(sources),
        "nvidia_count": entities.get("nvidia", 0),
        "topic_counts": dict(topics),
        "source_counts": dict(sources),
    }


def fallback_news_summary(news: list[dict[str, Any]], quality: dict[str, Any]) -> dict[str, Any]:
    topics = quality.get("topic_counts", {})
    topic_summary = [
        {"topic": TOPIC_LABELS.get(topic, topic), "count": count, "summary": TOPIC_LABELS.get(topic, topic)}
        for topic, count in sorted(topics.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    ]
    key_points = [
        f"{item['title']}（{item['source']}，{item['time']}）"
        for item in news[:5]
    ]
    if not news:
        headline = "目前沒有可用的合格新聞摘要。"
    else:
        headline = f"目前整理 {len(news)} 則新聞，涵蓋 {len(topics)} 類主題；同一公司或事件不應主導全部清單。"
    return {"headline": headline, "topic_summary": topic_summary, "key_points": key_points}


def fallback_market_summary(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in quotes if finite_number(row.get("change_pct")) is not None]
    down = [row for row in valid if finite_number(row.get("change_pct")) < 0]
    up = [row for row in valid if finite_number(row.get("change_pct")) > 0]
    if down and len(down) > len(up):
        headline = f"隔夜行情偏弱，可比對行情中下跌 {len(down)} 筆、上漲 {len(up)} 筆。"
    elif up and len(up) > len(down):
        headline = f"隔夜行情偏強，可比對行情中上漲 {len(up)} 筆、下跌 {len(down)} 筆。"
    else:
        headline = "隔夜行情漲跌互見，需搭配各市場與新聞題材判讀。"
    ordered = sorted(valid, key=lambda row: abs(finite_number(row.get("change_pct")) or 0), reverse=True)
    bullets = []
    for row in ordered[:4]:
        pct = finite_number(row.get("change_pct"))
        if pct is None:
            continue
        bullets.append(f"{row['name']}：{pct:+.2f}%（資料時間 {row.get('updated_at') or '未提供'}）")
    if not bullets:
        bullets = ["沒有足夠的行情漲跌幅可供比較。"]
    return {
        "headline": headline,
        "bullets": bullets,
        "risks": ["行情時間與資料延遲請以各卡片標示為準。", "以上為快照整理，不代表價格方向預測。"],
    }


def build_input(indices: Any, night: Any, news: Any, source_status: Any) -> dict[str, Any]:
    indices = indices if isinstance(indices, dict) else {}
    night = night if isinstance(night, dict) else {}
    rows = news_rows(news)
    quotes = quote_rows(indices, night)
    return {
        "market_quotes": quotes[:32],
        "night_session": {
            "date": night.get("date"),
            "latest": night.get("latest") if isinstance(night.get("latest"), dict) else {},
        },
        "news": rows,
        "source_status": source_status if isinstance(source_status, dict) else {},
    }


def call_gemini(api_key: str, model: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "temperature": 0.2,
            "maxOutputTokens": 2200,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    parts = (((result.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text:
        raise ValueError("Gemini response did not contain text")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response was not an object")
    return parsed


def normalize_ai_response(
    raw: dict[str, Any],
    fallback_news: dict[str, Any],
    fallback_market: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    news = raw.get("news_summary") if isinstance(raw.get("news_summary"), dict) else {}
    market = raw.get("market_summary") if isinstance(raw.get("market_summary"), dict) else {}
    topic_summary = news.get("topic_summary") if isinstance(news.get("topic_summary"), list) else []
    expected_topics = quality.get("topic_counts", {}) if isinstance(quality, dict) else {}
    label_to_key = {label: key for key, label in TOPIC_LABELS.items()}
    normalized_topics = []
    for item in topic_summary[:8]:
        if not isinstance(item, dict):
            continue
        raw_topic = clean_text(item.get("topic"), "other")
        topic_key = raw_topic if raw_topic in expected_topics else label_to_key.get(raw_topic)
        if topic_key not in expected_topics:
            continue
        normalized_topics.append({
            "topic": TOPIC_LABELS.get(topic_key, topic_key),
            "count": int(expected_topics[topic_key]),
            "summary": clean_text(item.get("summary"), TOPIC_LABELS.get(topic_key, topic_key)),
        })
    normalized = {
        "news_summary": {
            "headline": clean_text(news.get("headline"), fallback_news["headline"]),
            "topic_summary": normalized_topics or fallback_news["topic_summary"],
            "key_points": [clean_text(item) for item in (news.get("key_points") or []) if clean_text(item)][:5] or fallback_news["key_points"],
        },
        "market_summary": {
            "headline": clean_text(market.get("headline"), fallback_market["headline"]),
            "bullets": [clean_text(item) for item in (market.get("bullets") or []) if clean_text(item)][:4] or fallback_market["bullets"],
            "risks": [clean_text(item) for item in (market.get("risks") or []) if clean_text(item)][:4] or fallback_market["risks"],
        },
        "quality_note": clean_text(raw.get("quality_note"), "資料品質請以右側檢查結果與各來源時間為準。"),
    }
    return normalized


def generate_summary(indices: Any, night: Any, news: Any, source_status: Any, api_key: str | None = None, model: str | None = None) -> dict[str, Any]:
    payload = build_input(indices, night, news, source_status)
    news_items = payload["news"]
    quotes = payload["market_quotes"]
    quality = deterministic_quality(news_items, quotes, source_status)
    fallback_news = fallback_news_summary(news_items, quality)
    fallback_market = fallback_market_summary(quotes)
    key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    selected_model = (model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    status = "fallback"
    fallback_reason = "未設定 Gemini API 金鑰"
    narrative = {
        "news_summary": fallback_news,
        "market_summary": fallback_market,
        "quality_note": "目前使用確定性整理；完成 AI 服務設定後，會補上語意摘要。",
    }
    if key:
        try:
            narrative = normalize_ai_response(call_gemini(key, selected_model, payload), fallback_news, fallback_market, quality)
            status = "ok"
            fallback_reason = None
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            fallback_reason = f"Gemini 摘要暫時失敗：{str(exc)[:160]}"
            print(f"WARNING: {fallback_reason}", file=sys.stderr)
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "status": status,
        "provider": "Gemini API" if status == "ok" else "確定性降級整理",
        "model": selected_model if status == "ok" else None,
        "fallback_reason": fallback_reason,
        "news_stats": {
            "count": quality["news_count"],
            "unique_topics": quality["unique_topics"],
            "unique_sources": quality["unique_sources"],
            "nvidia_count": quality["nvidia_count"],
        },
        "data_quality": quality,
        **narrative,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate optional Gemini AI briefing")
    parser.add_argument("--indices", default="data/latest/indices.json")
    parser.add_argument("--night-session", default="data/latest/night_session.json")
    parser.add_argument("--news", default="data/latest/news.json")
    parser.add_argument("--source-status", default="data/latest/source_status.json")
    parser.add_argument("--out", default="data/latest/ai_summary.json")
    args = parser.parse_args()

    result = generate_summary(
        load_json(args.indices, {}),
        load_json(args.night_session, {}),
        load_json(args.news, []),
        load_json(args.source_status, {}),
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"AI briefing status: {result['status']} ({result['provider']}); wrote {output}")


if __name__ == "__main__":
    main()
