import json
from pathlib import Path

import pytest

from scripts.archive_history import archive_daily_data, prune_history


def test_prune_history_keeps_window_and_ignores_non_dated_json(tmp_path: Path):
    history = tmp_path / "history"
    history.mkdir()
    for name in ("2026-08-25.json", "2026-08-24.json", "2026-06-26.json", "not-a-date.json"):
        (history / name).write_text("{}", encoding="utf-8")

    removed = prune_history(history, today="2026-08-25", retain_days=60)

    assert str(history / "2026-06-26.json") in removed
    assert (history / "2026-08-25.json").exists()
    assert (history / "2026-08-24.json").exists()
    assert (history / "not-a-date.json").exists()


def test_archive_daily_data_writes_snapshot_then_prunes_old_archives(tmp_path: Path, monkeypatch):
    data = tmp_path / "latest"
    history = tmp_path / "history"
    data.mkdir()
    history.mkdir()
    (data / "indices.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (history / "2026-01-01.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    output = archive_daily_data(
        data_dir=str(data),
        history_dir=str(history),
        date_override="2026-08-25",
        retain_days=60,
    )

    assert Path(output).exists()
    snapshot = json.loads(Path(output).read_text(encoding="utf-8"))
    assert snapshot["data_date"] == "2026-08-25"
    assert snapshot["retention_days"] == 60
    assert snapshot["sources"]["indices"] == {"ok": True}
    assert not (history / "2026-01-01.json").exists()


def test_prune_history_rejects_invalid_retention_or_date(tmp_path: Path):
    with pytest.raises(ValueError):
        prune_history(tmp_path, today="2026-08-25", retain_days=0)
    with pytest.raises(ValueError):
        prune_history(tmp_path, today="2026/08/25", retain_days=60)


def test_prune_history_can_target_markdown_articles(tmp_path: Path):
    articles = tmp_path / "pressplay"
    articles.mkdir()
    for name in ("2026-09-11.md", "2026-09-10.md", "2026-09-09.md", "2026-09-08.md", "keep-me.md"):
        (articles / name).write_text("article", encoding="utf-8")

    removed = prune_history(articles, today="2026-09-11", retain_days=3, suffix=".md")

    assert str(articles / "2026-09-08.md") in removed
    assert (articles / "2026-09-11.md").exists()
    assert (articles / "2026-09-10.md").exists()
    assert (articles / "2026-09-09.md").exists()
    assert (articles / "keep-me.md").exists()


def test_prune_history_default_suffix_still_ignores_markdown(tmp_path: Path):
    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "2026-01-01.json").write_text("{}", encoding="utf-8")
    (mixed / "2026-01-01.md").write_text("article", encoding="utf-8")

    removed = prune_history(mixed, today="2026-09-11", retain_days=3)

    assert str(mixed / "2026-01-01.json") in removed
    assert (mixed / "2026-01-01.md").exists()


def test_archive_daily_data_prunes_old_pressplay_articles(tmp_path: Path, monkeypatch):
    data = tmp_path / "latest"
    history = tmp_path / "history"
    articles = tmp_path / "data" / "pressplay"
    data.mkdir()
    history.mkdir()
    articles.mkdir(parents=True)
    (articles / "2026-09-11.md").write_text("today", encoding="utf-8")
    (articles / "2026-08-23.md").write_text("old", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    archive_daily_data(
        data_dir=str(data),
        history_dir=str(history),
        date_override="2026-09-11",
        retain_days=60,
    )

    assert (articles / "2026-09-11.md").exists(), "today's article is the same-day fallback cache"
    assert not (articles / "2026-08-23.md").exists()
