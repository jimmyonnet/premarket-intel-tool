import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from scripts import fetch_pressplay_groups as pressplay


TAIPEI = timezone(timedelta(hours=8))


def test_credentials_prioritize_live_article_over_same_day_cache(tmp_path, monkeypatch):
    now = datetime(2026, 8, 24, 23, 30, tzinfo=TAIPEI)
    local_md = tmp_path / "2026-08-24.md"
    local_md.write_text(
        "Title: 0824盤前\nURL: https://old.example/article\nCollected: old\n---\n舊文章內容",
        encoding="utf-8",
    )
    calls = []

    def fake_live_fetch():
        calls.append(True)
        return {"title": "0825盤前", "url": "https://new.example/article"}, "新文章內容"

    monkeypatch.setattr(pressplay, "fetch_article_via_browser", fake_live_fetch)

    source, text = pressplay.load_article_source(
        now,
        local_md=local_md,
        fixture_txt=tmp_path / "missing-fixture.txt",
        email="member@example.com",
        password="secret",
    )

    assert calls == [True]
    assert source["title"] == "0825盤前"
    assert source["url"] == "https://new.example/article"
    assert source["fetch_mode"] == "live_browser"
    assert text == "新文章內容"
    assert "Title: 0825盤前" in local_md.read_text(encoding="utf-8")


def test_manual_override_is_explicit_and_wins_over_live_credentials(tmp_path, monkeypatch):
    now = datetime(2026, 8, 24, 23, 30, tzinfo=TAIPEI)
    manual = tmp_path / "manual.md"
    manual.write_text(
        "Title: 手動提供文章\nURL: https://manual.example/article\n---\n手動文章內容",
        encoding="utf-8",
    )

    def fail_if_live_called():
        raise AssertionError("manual override must not call live fetch")

    monkeypatch.setattr(pressplay, "fetch_article_via_browser", fail_if_live_called)

    source, text = pressplay.load_article_source(
        now,
        manual_override_path=manual,
        local_md=tmp_path / "cache.md",
        fixture_txt=tmp_path / "missing-fixture.txt",
        email="member@example.com",
        password="secret",
    )

    assert source["fetch_mode"] == "manual_override"
    assert source["title"] == "手動提供文章"
    assert text == "手動文章內容"


def test_live_failure_marks_same_day_cache_as_fallback(tmp_path, monkeypatch):
    now = datetime(2026, 8, 24, 23, 30, tzinfo=TAIPEI)
    local_md = tmp_path / "2026-08-24.md"
    local_md.write_text("Title: 舊文章\n---\n快取內容", encoding="utf-8")

    monkeypatch.setattr(
        pressplay,
        "fetch_article_via_browser",
        lambda: (_ for _ in ()).throw(RuntimeError("login blocked")),
    )

    source, text = pressplay.load_article_source(
        now,
        local_md=local_md,
        fixture_txt=tmp_path / "missing-fixture.txt",
        email="member@example.com",
        password="secret",
    )

    assert source["fetch_mode"] == "fallback_cache"
    assert "login blocked" in source["fallback_reason"]
    assert text == "快取內容"


@pytest.mark.parametrize(
    ("short_name", "canonical_name", "code"),
    [
        ("環宇", "環宇-KY", "4991"),
        ("聯德控股", "聯德控股-KY", "4912"),
        ("中租", "中租-KY", "5871"),
    ],
)
def test_ky_shorthand_matches_canonical_daily_name(short_name, canonical_name, code):
    rows = [{"code": code, "name": canonical_name}]

    result = pressplay.match_token(short_name, rows)

    assert result is not None
    assert result["code"] == code
    assert result["name"] == canonical_name
    assert result["match_type"] == "ky_alias"
    assert result["raw_token"] == short_name


def test_exact_name_remains_higher_priority_than_ky_alias():
    rows = [
        {"code": "2371", "name": "台南"},
        {"code": "5906", "name": "台南-KY"},
    ]

    result = pressplay.match_token("台南", rows)

    assert result["code"] == "2371"
    assert result["match_type"] == "name"


def test_every_unique_ky_stock_supports_shorthand_from_canonical_dictionary():
    repo_root = Path(__file__).parents[1]
    payload = json.loads((repo_root / "data/tw_stock_names.json").read_text(encoding="utf-8"))
    pairs = [
        (name, code)
        for name, code in payload["name_to_code"].items()
        if name.endswith("-KY")
    ]

    assert len(pairs) >= 100
    for canonical_name, code in pairs:
        result = pressplay.match_token(
            canonical_name[:-3],
            [{"code": code, "name": canonical_name}],
        )
        assert result is not None, canonical_name
        assert result["code"] == code
        assert result["name"] == canonical_name
        assert result["match_type"] == "ky_alias"


def test_ky_shorthand_uses_stock_dictionary_when_daily_row_is_missing():
    stock_dict = {
        "name_to_code": {"環宇-KY": "4991"},
        "code_to_name": {"4991": "環宇-KY"},
    }

    result = pressplay.match_token("環宇", [], stock_dict=stock_dict)

    assert result["code"] == "4991"
    assert result["name"] == "環宇-KY"
    assert result["match_type"] == "dict_ky_alias"
    assert result["raw_token"] == "環宇"
