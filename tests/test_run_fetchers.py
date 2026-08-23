import json

from scripts.run_fetchers import fetch_source


def test_fetch_source_marks_unchanged_snapshot_as_fallback(tmp_path, monkeypatch):
    target = tmp_path / "news.json"
    target.write_text(json.dumps({"items": [{"title": "previous"}]}), encoding="utf-8")

    monkeypatch.setattr("scripts.run_fetchers.run_command", lambda *args, **kwargs: (0, "", ""))

    result = fetch_source("news", ["fake-fetcher"], target, "[]")

    assert result["status"] == "failed"
    assert result["fallback_used"] is True
    assert result["error_summary"] == "指令成功但未產生新資料，沿用前次快照"
    assert json.loads(target.read_text(encoding="utf-8"))["items"][0]["title"] == "previous"


def test_fetch_source_accepts_target_updated_by_command(tmp_path, monkeypatch):
    target = tmp_path / "news.json"

    def fake_run_command(*args, **kwargs):
        target.write_text(json.dumps({"items": [{"title": "fresh"}]}), encoding="utf-8")
        return 0, "", ""

    monkeypatch.setattr("scripts.run_fetchers.run_command", fake_run_command)

    result = fetch_source("news", ["fake-fetcher"], target, "[]")

    assert result["status"] == "ok"
    assert result["fallback_used"] is False
    assert json.loads(target.read_text(encoding="utf-8"))["items"][0]["title"] == "fresh"
