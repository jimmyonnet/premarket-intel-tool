#!/usr/bin/env python3
"""Validate fetched JSON snapshots before page generation.

The validator intentionally checks only the data contract. It does not change
any rendered HTML and treats empty fallback payloads as warnings so the
existing diagnostic-page behavior remains available when a source is down.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


EXPECTED_TOP_LEVEL: dict[str, tuple[type[Any], ...]] = {
    "indices": (dict,),
    "night_session": (dict,),
    "disposal": (dict,),
    "pressplay": (dict,),
    "chengwaye_daily": (dict,),
    "calendar": (dict,),
    "financials": (dict,),
    "news": (dict, list),
    "twse_summary": (dict,),
    "source_status": (dict,),
}

REQUIRED_OBJECT_KEYS = {
    "source_status": ("sources",),
    "financials": ("att", "fin", "rev"),
}

MARKET_ROW_GROUPS = {
    "pressplay": (
        ("found_group", "matched"),
        ("not_found_group", "matched"),
    ),
    "disposal": (
        ("one_flag_from_disposal",),
        ("two_flags_from_disposal",),
        ("currently_in_disposal",),
    ),
}

MARKET_NUMERIC_KEYS = ("close", "volume", "foreign", "trust", "dealer")


def _is_empty(payload: Any) -> bool:
    return payload == {} or payload == [] or payload is None


def _normalize_code(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        value = int(value) if value.is_integer() else value
    text = str(value).strip()
    marker = "⏸" if text.startswith("⏸") else ""
    clean = text.replace("⏸", "").strip()
    return f"{marker}{clean}" if clean else None


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        raw = value.replace(",", "").strip()
        if not raw or raw == "—":
            return False
        try:
            return math.isfinite(float(raw))
        except ValueError:
            return False
    return False


def normalize_market_rows(name: str, payload: Any, warnings: list[str]) -> bool:
    """Normalize stock rows in-place before static package generation.

    Invalid identifiers are removed from list-based market tables. Invalid numeric
    display values are converted to the existing safe placeholder rather than
    allowing NaN/undefined values to reach the rendered page.
    """
    changed = False
    for path_parts in MARKET_ROW_GROUPS.get(name, ()):
        container: Any = payload
        for key in path_parts[:-1]:
            container = container.get(key, {}) if isinstance(container, dict) else {}
        final_key = path_parts[-1]
        rows = container.get(final_key) if isinstance(container, dict) else None
        if not isinstance(rows, list):
            continue
        normalized_rows = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                warnings.append(f"{name}.{'.'.join(path_parts)}[{index}] 正規化：略過非物件資料列")
                changed = True
                continue
            normalized_code = _normalize_code(row.get("code"))
            if normalized_code is None:
                warnings.append(f"{name}.{'.'.join(path_parts)}[{index}] 正規化：略過無效代號")
                changed = True
                continue
            if row.get("code") != normalized_code:
                row["code"] = normalized_code
                changed = True
            for field in MARKET_NUMERIC_KEYS:
                if field in row and not _is_finite_number(row[field]):
                    row[field] = "—"
                    warnings.append(f"{name}.{'.'.join(path_parts)}[{index}].{field} 正規化為安全空值")
                    changed = True
            normalized_rows.append(row)
        if normalized_rows != rows:
            container[final_key] = normalized_rows
    return changed


def validate_data_dir(data_dir: str | Path, normalize: bool = False) -> dict[str, Any]:
    """Return a structured validation report for ``data/latest`` snapshots."""
    root = Path(data_dir)
    errors: list[str] = []
    warnings: list[str] = []
    files: dict[str, dict[str, Any]] = {}
    normalized_files: list[str] = []

    for name, expected_types in EXPECTED_TOP_LEVEL.items():
        path = root / f"{name}.json"
        if not path.exists():
            errors.append(f"missing file: {path}")
            continue
        if path.stat().st_size == 0:
            errors.append(f"empty file: {path}")
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON in {path}: {exc}")
            continue

        if not isinstance(payload, expected_types):
            type_names = ", ".join(t.__name__ for t in expected_types)
            errors.append(f"wrong top-level type in {path}: expected {type_names}, got {type(payload).__name__}")
            continue

        if _is_empty(payload):
            warnings.append(f"empty fallback payload: {path}")

        for key in REQUIRED_OBJECT_KEYS.get(name, ()):
            if not isinstance(payload, dict) or key not in payload:
                errors.append(f"missing key '{key}' in {path}")

        if normalize and normalize_market_rows(name, payload, warnings):
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            normalized_files.append(name)

        files[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "top_level_type": type(payload).__name__,
            "empty": _is_empty(payload),
        }

    source_status = files.get("source_status")
    if source_status and source_status.get("empty"):
        warnings.append("source_status is empty; page health will remain in caution state")

    return {
        "ok": not errors,
        "data_dir": str(root),
        "files": files,
        "errors": errors,
        "warnings": warnings,
        "normalized_files": normalized_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate premarket JSON snapshots")
    parser.add_argument("--data-dir", default="data/latest", help="Directory containing source JSON snapshots")
    parser.add_argument("--json-out", help="Optional path for the machine-readable validation report")
    parser.add_argument("--normalize", action="store_true", help="Normalize candidate/disposal rows before static package generation")
    args = parser.parse_args()

    report = validate_data_dir(args.data_dir, normalize=args.normalize)
    if args.json_out:
        output = Path(args.json_out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    print(f"Validated {len(report['files'])}/{len(EXPECTED_TOP_LEVEL)} data files")
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
