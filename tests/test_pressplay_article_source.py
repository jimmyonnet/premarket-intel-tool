from datetime import datetime, timezone, timedelta
from pathlib import Path

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
