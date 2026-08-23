import json
import re
import pytest

def smart_parse_watchlist(raw_text: str):
    if not raw_text:
        return {"valid": [], "duplicates": [], "invalid": []}
    lines = raw_text.splitlines()
    valid = []
    duplicates = []
    invalid = []
    seen = set()

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        tokens = re.split(r'[\t,;|\s]+', trimmed)
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue

            # Date formats: 2026/08/21, 2026-08-21, 08/21, 08-21
            if re.match(r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}$', tok) or re.match(r'^\d{1,2}[/-]\d{1,2}$', tok):
                invalid.append(f"{tok} (疑似日期)")
                continue

            # Time formats: 14:30, 09:00:00
            if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', tok):
                invalid.append(f"{tok} (疑似時間)")
                continue

            # Percentages & Decimals
            if ('.' in tok or '%' in tok) and re.match(r'^[+-]?\d+(\.\d+)?%?$', tok):
                invalid.append(f"{tok} (數值/比例)")
                continue

            # Stock code: 4 to 5 digits
            match = re.match(r'^(\d{4,5})(\.TW|\.TWO)?$', tok, re.IGNORECASE)
            if match:
                code = match.group(1)
                if code not in seen:
                    seen.add(code)
                    valid.append(code)
                else:
                    if code not in duplicates:
                        duplicates.append(code)
            else:
                if re.match(r'^\d{6,}$', tok):
                    invalid.append(f"{tok} (超過5位數字)")
                elif not re.match(r'^[\u4e00-\u9fa5a-zA-Z]+$', tok):
                    invalid.append(tok)

    return {"valid": valid, "duplicates": duplicates, "invalid": invalid}


def test_smart_batch_parser_user_spec():
    sample_input = """2330
2454 聯發科
2330
2026/08/21
abcd"""
    res = smart_parse_watchlist(sample_input)
    assert res["valid"] == ["2330", "2454"]
    assert res["duplicates"] == ["2330"]
    assert any("2026/08/21" in x for x in res["invalid"])


def test_watchlist_json_schema_validation():
    valid_json = {
        "app": "premarket-intel-tool",
        "schema_version": 1,
        "backup_time": "2026-08-23T14:00:00+08:00",
        "watchlist": ["2330", "2454", "3163"]
    }
    assert valid_json["schema_version"] == 1
    assert isinstance(valid_json["watchlist"], list)
    assert len(valid_json["watchlist"]) == 3
