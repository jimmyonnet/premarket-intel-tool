#!/usr/bin/env python3
"""Evaluate prior-day signals against close/high prices.

The script is deliberately data-source agnostic: CI can supply a normalized
prices JSON file, while local tests can exercise the calculation offline.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def _pct(start: Any, end: Any) -> float | None:
    try:
        start_f, end_f = float(start), float(end)
        if start_f == 0:
            return None
        return round((end_f / start_f - 1) * 100, 2)
    except (TypeError, ValueError):
        return None


def build_review(signals: dict[str, list[dict[str, Any]]], prices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    detail = []
    for signal, rows in (signals or {}).items():
        for row in rows or []:
            code = str(row.get("code") or "").replace("⏸", "").strip()
            price = prices.get(code) or prices.get(str(code).zfill(4))
            if not price:
                continue
            ret = _pct(row.get("close"), price.get("close"))
            high_ret = _pct(row.get("close"), price.get("high"))
            if ret is None:
                continue
            detail.append({
                "sig": signal,
                "code": code,
                "name": row.get("name"),
                "ret": ret,
                "high_ret": high_ret,
            })

    stats: dict[str, dict[str, Any]] = {}
    for signal in sorted({item["sig"] for item in detail}):
        group = [item for item in detail if item["sig"] == signal]
        highs = [item["high_ret"] for item in group if item["high_ret"] is not None]
        stats[signal] = {
            "n": len(group),
            "win_rate": round(sum(item["ret"] > 0 for item in group) / len(group) * 100, 1),
            "avg_ret": round(sum(item["ret"] for item in group) / len(group), 2),
            "avg_high": round(sum(highs) / len(highs), 2) if highs else None,
        }
    return {"detail": detail, "stats": stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate previous-day signal effectiveness")
    parser.add_argument("--signals", required=True, help="JSON object keyed by signal name")
    parser.add_argument("--prices", required=True, help="JSON object keyed by stock code")
    parser.add_argument("--out", required=True, help="Output review.json")
    args = parser.parse_args()
    signals = json.loads(Path(args.signals).read_text(encoding="utf-8"))
    prices = json.loads(Path(args.prices).read_text(encoding="utf-8"))
    output = build_review(signals, prices)
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: {len(output['detail'])} observations, {len(output['stats'])} signals")


if __name__ == "__main__":
    main()
