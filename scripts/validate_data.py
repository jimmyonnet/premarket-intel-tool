#!/usr/bin/env python3
"""Validate fetched JSON snapshots before page generation.

The validator intentionally checks only the data contract. It does not change
any rendered HTML and treats empty fallback payloads as warnings so the
existing diagnostic-page behavior remains available when a source is down.
"""
from __future__ import annotations

import argparse
import json
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


def _is_empty(payload: Any) -> bool:
    return payload == {} or payload == [] or payload is None


def validate_data_dir(data_dir: str | Path) -> dict[str, Any]:
    """Return a structured validation report for ``data/latest`` snapshots."""
    root = Path(data_dir)
    errors: list[str] = []
    warnings: list[str] = []
    files: dict[str, dict[str, Any]] = {}

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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate premarket JSON snapshots")
    parser.add_argument("--data-dir", default="data/latest", help="Directory containing source JSON snapshots")
    parser.add_argument("--json-out", help="Optional path for the machine-readable validation report")
    args = parser.parse_args()

    report = validate_data_dir(args.data_dir)
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
