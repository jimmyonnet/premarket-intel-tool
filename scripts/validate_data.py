"""Validate fetched JSON snapshots before page generation.

This validator has two explicit layers:

* ``DATA_CONTRACT_SCHEMAS`` documents the supported top-level contracts and
  validates required structure without adding a runtime dependency.
* semantic checks compare dates, market ranges, identifiers and duplicates
  across the actual source payloads.

Empty source payloads remain warnings so the site can render a diagnostic page;
structural or semantic contradictions are errors and fail CI/build validation.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from trading_calendar import TradingCalendarError, get_current_trading_day
except ModuleNotFoundError:
    from scripts.trading_calendar import TradingCalendarError, get_current_trading_day

TAIPEI = timezone(timedelta(hours=8))

EXPECTED_TOP_LEVEL: dict[str, tuple[type[Any], ...]] = {
    "indices": (dict,), "night_session": (dict,), "disposal": (dict,),
    "pressplay": (dict,), "chengwaye_daily": (dict,), "stock_history": (dict,),
    "calendar": (dict,), "financials": (dict,), "news": (dict, list),
    "ai_summary": (dict,), "twse_summary": (dict,), "source_status": (dict,),
}

# A small JSON-Schema-like contract is intentional: the validator can run in a
# clean scheduled job without installing jsonschema, while new sources still
# have an explicit place to declare top-level and required-field changes.
DATA_CONTRACT_SCHEMAS: dict[str, dict[str, Any]] = {
    "indices": {"type": "object"},
    "night_session": {"type": "object", "required": ["date", "latest"]},
    "disposal": {"type": "object", "required": ["date_check"]},
    "pressplay": {"type": "object"},
    "chengwaye_daily": {"type": "object"},
    "stock_history": {"type": "object", "required": ["codes", "failed_codes"]},
    "calendar": {"type": "object"},
    "financials": {"type": "object", "required": ["att", "fin", "rev"]},
    "news": {"type": ["object", "array"]},
    "ai_summary": {"type": "object"},
    "twse_summary": {"type": "object"},
    "source_status": {"type": "object", "required": ["sources"]},
}

REQUIRED_OBJECT_KEYS = {
    name: tuple(schema.get("required", ())) for name, schema in DATA_CONTRACT_SCHEMAS.items()
}

MARKET_ROW_GROUPS = {
    "pressplay": (("found_group", "matched"), ("not_found_group", "matched")),
    "disposal": (("one_flag_from_disposal",), ("two_flags_from_disposal",), ("currently_in_disposal",)),
}
MARKET_NUMERIC_KEYS = ("close", "volume", "foreign", "trust", "dealer")
DATE_KEYS = ("date", "today", "page_date", "data_date", "chengwaye_date", "effective_market_day")
# A deliberately conservative bound: TWSE index limit-up/limit-down is usually
# much narrower, but 50% avoids rejecting special no-price-limit sessions.
INDEX_CHANGE_WARNING_PCT = 30.0
INDEX_CHANGE_ERROR_PCT = 50.0


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


def _code_key(value: Any) -> str | None:
    code = _normalize_code(value)
    if not code:
        return None
    return code.removeprefix("⏸").strip().upper()


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        raw = value.replace(",", "").strip()
        if not raw or raw in {"—", "-"}:
            return False
        try:
            return math.isfinite(float(raw.replace("%", "")))
        except ValueError:
            return False
    return False


def _number(value: Any) -> float | None:
    if not _is_finite_number(value):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _parse_date(value: Any, reference_year: int | None = None) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    for fmt in ("%m/%d", "%m-%d"):
        try:
            if reference_year is not None:
                return datetime.strptime(f"{reference_year}/{text.replace('-', '/')}", "%Y/%m/%d").date()
        except ValueError:
            pass
    # ROC dates in financial announcements, e.g. 115/08/24.
    match = re.fullmatch(r"(\d{2,3})[/.](\d{1,2})[/.](\d{1,2})", text)
    if match:
        try:
            return date(int(match.group(1)) + 1911, int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def normalize_market_rows(name: str, payload: Any, warnings: list[str]) -> bool:
    """Normalize stock rows in-place before static package generation."""
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


def _schema_type_matches(value: Any, expected: str | list[str]) -> bool:
    expected_types = [expected] if isinstance(expected, str) else expected
    return any(
        (kind == "object" and isinstance(value, dict))
        or (kind == "array" and isinstance(value, list))
        for kind in expected_types
    )


def validate_explicit_schema(name: str, payload: Any, errors: list[str]) -> None:
    # Empty payloads are intentional source fallbacks; preserve the existing
    # diagnostic-page contract and report them as warnings at the caller.
    if _is_empty(payload) and name != "source_status":
        return
    schema = DATA_CONTRACT_SCHEMAS[name]
    if not _schema_type_matches(payload, schema["type"]):
        errors.append(f"schema violation in {name}: expected {schema['type']}")
        return
    if isinstance(payload, dict):
        for key in schema.get("required", ()):
            if key not in payload:
                # Older disposal fixtures may contain only parsed market lists.
                if name == "disposal" and key == "date_check" and any(group in payload for group in ("one_flag_from_disposal", "two_flags_from_disposal", "currently_in_disposal")):
                    continue
                if name == "source_status":
                    errors.append(f"missing key '{key}' in {name} (schema violation)")
                else:
                    errors.append(f"schema violation in {name}: missing required key '{key}'")
    if name == "source_status" and isinstance(payload.get("sources"), dict):
        for source_id, source in payload["sources"].items():
            if not isinstance(source, dict):
                errors.append(f"schema violation in source_status.sources.{source_id}: expected object")
            elif "status" not in source:
                errors.append(f"schema violation in source_status.sources.{source_id}: missing status")


def _walk_lists(value: Any, path: str = "") -> Iterable[tuple[str, list[Any]]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(child, list):
                yield child_path, child
            else:
                yield from _walk_lists(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_lists(child, f"{path}[{index}]")


def _walk_mappings(value: Any, path: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_mappings(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_mappings(child, f"{path}[{index}]")


def _collect_date_candidates(name: str, payload: Any, reference_year: int | None) -> list[tuple[str, date]]:
    found: list[tuple[str, date]] = []
    for path, mapping in _walk_mappings(payload):
        for key in DATE_KEYS:
            parsed = _parse_date(mapping.get(key), reference_year)
            if parsed:
                prefix = f"{name}.{path}." if path else f"{name}."
                found.append((f"{prefix}{key}", parsed))
    return found


def _validate_date_consistency(payloads: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    reference: date | None = None
    reference_source: str | None = None
    for name, payload in payloads.items():
        candidates = _collect_date_candidates(name, payload, reference.year if reference else None)
        # Only compare explicit report/source dates. Event calendars and news
        # naturally contain many dates and are excluded from this cross-source check.
        if name in {"calendar", "news", "stock_history", "financials", "chengwaye_daily"}:
            continue
        for path, value in candidates:
            if reference is None:
                reference, reference_source = value, path
            elif value != reference:
                warnings.append(f"資料日期不一致：{path}={value.isoformat()}，基準 {reference_source}={reference.isoformat()}")


def _validate_disposal_previous_trading_day(
    payloads: dict[str, Any], data_dir: Path, errors: list[str], warnings: list[str]
) -> None:
    disposal = payloads.get("disposal")
    if not isinstance(disposal, dict):
        return
    check = disposal.get("date_check")
    if not isinstance(check, dict):
        return
    raw_page = check.get("page_says_applies_to")
    raw_market = check.get("effective_market_day") or check.get("today")
    market_day = _parse_date(raw_market)
    page_date = _parse_date(raw_page, market_day.year if market_day else None)
    if not market_day or not page_date:
        warnings.append("disposal 日期無法解析，未執行上一交易日語意檢查")
        return
    try:
        calendar_path = data_dir.parent / "trading_calendar" / "twse_holidays.json"
        expected = get_current_trading_day(market_day - timedelta(days=1), config_path=calendar_path)
    except TradingCalendarError as exc:
        errors.append(f"disposal 上一交易日無法由權威日曆計算：{exc}")
        return
    if page_date != expected:
        warnings.append(
            f"disposal page_says_applies_to={page_date.isoformat()}，來源上一交易日基準為 {expected.isoformat()}（effective_market_day={market_day.isoformat()}）"
        )


def _validate_index_ranges(payloads: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    indices = payloads.get("indices")
    if not isinstance(indices, dict):
        return
    for path, values in _walk_lists(indices):
        for index, row in enumerate(values):
            if not isinstance(row, dict):
                continue
            if "change_pct" not in row:
                continue
            value = _number(row.get("change_pct"))
            if value is None:
                errors.append(f"indices.{path}[{index}].change_pct 不是有限數值")
            elif abs(value) > INDEX_CHANGE_ERROR_PCT:
                errors.append(f"indices.{path}[{index}].change_pct={value:g}% 超過 {INDEX_CHANGE_ERROR_PCT}% 語意上限")
            elif abs(value) > INDEX_CHANGE_WARNING_PCT:
                warnings.append(f"indices.{path}[{index}].change_pct={value:g}% 超過一般警戒值 {INDEX_CHANGE_WARNING_PCT}%")
    def inspect_object(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if "change_pct" in value:
                change = _number(value["change_pct"])
                if change is not None and abs(change) > INDEX_CHANGE_ERROR_PCT:
                    errors.append(f"indices.{path}.change_pct={change:g}% 超過 {INDEX_CHANGE_ERROR_PCT}% 語意上限")
            for key, child in value.items():
                if isinstance(child, dict):
                    inspect_object(child, f"{path}.{key}")
    inspect_object(indices, "root")


def _validate_duplicate_codes(payloads: dict[str, Any], errors: list[str]) -> None:
    # These are candidate/market lists where a duplicate code is ambiguous.
    # Financial announcements may legitimately contain several rows for one
    # company and are validated by their (code, type, title) key below.
    for name, payload in payloads.items():
        if name not in {"pressplay", "disposal", "chengwaye_daily"}:
            continue
        for path, rows in _walk_lists(payload):
            codes: dict[str, int] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                code = _code_key(row.get("code"))
                if not code:
                    continue
                codes[code] = codes.get(code, 0) + 1
            for code, count in codes.items():
                if count > 1:
                    errors.append(f"{name}.{path} 股票代號 {code} 重複 {count} 次")


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _validate_news_duplicates(payload: Any, errors: list[str]) -> None:
    rows = payload if isinstance(payload, list) else payload.get("items", payload.get("news", [])) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return
    titles: dict[str, int] = {}
    links: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _normalize_text(row.get("title") or row.get("headline"))
        link = _normalize_text(row.get("link") or row.get("url"))
        if title:
            titles[title] = titles.get(title, 0) + 1
        if link:
            links[link] = links.get(link, 0) + 1
    for title, count in titles.items():
        if count > 1:
            errors.append(f"news normalized title 重複 {count} 次：{title[:80]}")
    for link, count in links.items():
        if count > 1:
            errors.append(f"news normalized link 重複 {count} 次：{link[:120]}")


def _validate_announcement_duplicates(payload: Any, errors: list[str]) -> None:
    if not isinstance(payload, dict):
        return
    seen: dict[tuple[str, str, str], int] = {}
    for kind in ("att", "fin", "rev"):
        rows = payload.get(kind, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = (_code_key(row.get("code")) or "", kind, _normalize_text(row.get("subject") or row.get("title")))
            if any(key):
                seen[key] = seen.get(key, 0) + 1
    for (code, kind, title), count in seen.items():
        if count > 1:
            errors.append(f"financials announcement 重複 {count} 次：{code}/{kind}/{title[:80]}")


def validate_data_dir(data_dir: str | Path, normalize: bool = False) -> dict[str, Any]:
    """Return a structured contract and semantic validation report."""
    root = Path(data_dir)
    errors: list[str] = []
    warnings: list[str] = []
    files: dict[str, dict[str, Any]] = {}
    payloads: dict[str, Any] = {}
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
        payloads[name] = payload
        if _is_empty(payload):
            warnings.append(f"empty fallback payload: {path}")
        validate_explicit_schema(name, payload, errors)
        if normalize and normalize_market_rows(name, payload, warnings):
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            normalized_files.append(name)
        files[name] = {"path": str(path), "bytes": path.stat().st_size, "top_level_type": type(payload).__name__, "empty": _is_empty(payload)}

    _validate_date_consistency(payloads, errors, warnings)
    _validate_disposal_previous_trading_day(payloads, root, errors, warnings)
    _validate_index_ranges(payloads, errors, warnings)
    _validate_duplicate_codes(payloads, errors)
    _validate_news_duplicates(payloads.get("news"), errors)
    _validate_announcement_duplicates(payloads.get("financials"), errors)

    if files.get("source_status", {}).get("empty"):
        warnings.append("source_status is empty; page health will remain in caution state")
    return {
        "ok": not errors,
        "data_dir": str(root),
        "files": files,
        "errors": errors,
        "warnings": warnings,
        "normalized_files": normalized_files,
        "semantic_checks": {
            "date_consistency": "checked",
            "disposal_previous_trading_day": "checked",
            "index_change_pct_bounds": {"warning": INDEX_CHANGE_WARNING_PCT, "error": INDEX_CHANGE_ERROR_PCT},
            "duplicate_codes": "checked",
            "news_title_link_duplicates": "checked",
            "announcement_duplicates": "checked",
        },
        "schema_version": "premarket-data-contract.v2",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate premarket JSON snapshots")
    parser.add_argument("--data-dir", default="data/latest", help="Directory containing source JSON snapshots")
    parser.add_argument("--json-out", help="Optional path for machine-readable validation report")
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
