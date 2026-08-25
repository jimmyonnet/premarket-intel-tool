"""Build the public learning-status package from opening ledgers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .evaluate_opening import evaluate
except ImportError:  # Allow direct script execution.
    from evaluate_opening import evaluate


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def load_records(directory: str | Path = "data/opening_history") -> list[dict[str, Any]]:
    root = Path(directory)
    records: list[dict[str, Any]] = []
    if not root.exists():
        return records
    for path in sorted(root.glob("????-??-??.json")):
        payload = _load(path)
        forecast = payload.get("forecast") if isinstance(payload.get("forecast"), dict) else {}
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        if result:
            records.append({**result, "confidence": forecast.get("confidence"), "model_version": forecast.get("model_version")})
    return records


def build_status(
    *,
    directory: str | Path = "data/opening_history",
    model_version: str | None = "opening-v1",
) -> dict[str, Any]:
    return evaluate(load_records(directory), model_version=model_version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build opening model learning status")
    parser.add_argument("--directory", default="data/opening_history")
    parser.add_argument("--model-version", default="opening-v1")
    parser.add_argument("--out", default="data/latest/learning_status.json")
    args = parser.parse_args(argv)
    payload = build_status(directory=args.directory, model_version=args.model_version)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
