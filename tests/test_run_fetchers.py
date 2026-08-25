import json

from scripts.run_fetchers import fetch_source, pressplay_fallback_info


def test_pressplay_fallback_info_distinguishes_live_and_cached_payloads():
    assert pressplay_fallback_info({"source_article": {"fetch_mode": "live_browser"}}) == (False, None)
    assert pressplay_fallback_info({"source_article": {"fetch_mode": "fallback_cache"}})[0] is True
    assert pressplay_fallback_info({"source_article": {"fetch_mode": "manual_override"}})[1] == "使用手動提供的 PressPlay 文章覆寫"
    assert pressplay_fallback_info({"source_article": {"fixture": "data/pressplay/old.md"}})[0] is True


def test_fetch_source_marks_unchanged_snapshot_as_fallback(tmp_path, monkeypatch):
    target = tmp_path / "news.json"
    target.write_text(json.dumps({"items": [{"title": "previous"}]}), encoding="utf-8")

    monkeypatch.setattr("scripts.run_fetchers.run_command", lambda *args, **kwargs: (0, "", ""))

    result = fetch_source("news", ["fake-fetcher"], target, "[]")

    assert result["status"] == "warning"
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


def test_fetch_source_keeps_file_json_when_fetcher_only_reports_progress_on_stderr(tmp_path, monkeypatch):
    target = tmp_path / "financials.json"

    def fake_run_command(*args, **kwargs):
        target.write_text(json.dumps({"att": [{"code": "2615"}], "fin": [], "rev": []}), encoding="utf-8")
        return 0, "", "att: 22 total, 4 unreflected"

    monkeypatch.setattr("scripts.run_fetchers.run_command", fake_run_command)

    result = fetch_source("financials", ["fake-fetcher"], target, '{"att":[],"fin":[],"rev":[]}')

    assert result["status"] == "ok"
    assert json.loads(target.read_text(encoding="utf-8"))["att"][0]["code"] == "2615"


def test_fetch_source_retries_transient_failure_then_accepts_fresh_snapshot(tmp_path, monkeypatch):
    target = tmp_path / "news.json"
    outcomes = [(1, "", "temporary timeout"), (1, "", "temporary timeout"), (0, "", "")]
    sleeps = []

    def fake_run_command(*args, **kwargs):
        exit_code, stdout, stderr = outcomes.pop(0)
        if exit_code == 0:
            target.write_text(json.dumps({"items": [{"title": "fresh"}]}), encoding="utf-8")
        return exit_code, stdout, stderr

    monkeypatch.setattr("scripts.run_fetchers.run_command", fake_run_command)

    result = fetch_source(
        "news", ["fake-fetcher"], target, "[]", sleep_fn=sleeps.append
    )

    assert result["status"] == "ok"
    assert result["retry_attempts"] == 2
    assert sleeps == [30, 30]
    assert json.loads(target.read_text(encoding="utf-8"))["items"][0]["title"] == "fresh"


def test_fetch_source_restores_previous_snapshot_after_all_retries_fail(tmp_path, monkeypatch):
    target = tmp_path / "news.json"
    target.write_text(json.dumps({"items": [{"title": "cached"}]}), encoding="utf-8")
    sleeps = []

    def fake_run_command(*args, **kwargs):
        target.write_text("partial response", encoding="utf-8")
        return 1, "", "temporary timeout"

    monkeypatch.setattr("scripts.run_fetchers.run_command", fake_run_command)

    result = fetch_source(
        "news", ["fake-fetcher"], target, "[]", sleep_fn=sleeps.append
    )

    assert result["status"] == "warning"
    assert result["fallback_used"] is True
    assert result["retry_attempts"] == 2
    assert json.loads(target.read_text(encoding="utf-8"))["items"][0]["title"] == "cached"
    assert sleeps == [30, 30]


def test_fetch_source_does_not_restore_corrupt_previous_snapshot(tmp_path, monkeypatch):
    target = tmp_path / "news.json"
    target.write_text("not valid json", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.run_fetchers.run_command",
        lambda *args, **kwargs: (1, "", "temporary timeout"),
    )

    result = fetch_source(
        "news", ["fake-fetcher"], target, "[]", sleep_fn=lambda _delay: None
    )

    assert result["status"] == "failed"
    assert result["fallback_used"] is True
    assert json.loads(target.read_text(encoding="utf-8")) == []



def _graph_task(source_id, target_file, dependencies=()):
    from scripts.run_fetchers import FetchTask

    return FetchTask(
        source_id=source_id,
        command=["fake", source_id],
        target_file=target_file,
        fallback_content="{}",
        dependencies=tuple(dependencies),
        modes=("full",),
        max_attempts=1,
        retry_delay_seconds=0,
    )


def test_task_graph_runs_independent_nodes_in_parallel_and_dependants_after_inputs(tmp_path):
    import threading
    import time
    from scripts.run_fetchers import run_task_graph

    active = 0
    peak = 0
    lock = threading.Lock()
    started = []
    finished = []

    def fake_fetch(source_id, _cmd, target_file, _fallback, *args):
        nonlocal active, peak
        with lock:
            started.append(source_id)
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        target_file.write_text("{}", encoding="utf-8")
        with lock:
            active -= 1
            finished.append(source_id)
        return {"source_id": source_id, "status": "ok", "fallback_used": False}

    result = run_task_graph(
        [_graph_task("alpha", tmp_path / "alpha.json"), _graph_task("beta", tmp_path / "beta.json"), _graph_task("child", tmp_path / "child.json", ("alpha",))],
        "full", max_workers=2, fetch_fn=fake_fetch,
    )
    assert peak == 2
    assert started.index("child") > started.index("alpha")
    assert result.order.index("alpha") < result.order.index("child")
    assert result.order == ["alpha", "beta", "child"]
    assert result.statuses["child"]["status"] == "ok"


def test_task_graph_isolates_independent_failure_and_blocks_only_dependants(tmp_path):
    from scripts.run_fetchers import run_task_graph

    def fake_fetch(source_id, _cmd, target_file, _fallback, *args):
        if source_id == "alpha":
            return {"source_id": source_id, "status": "failed", "fallback_used": True}
        target_file.write_text("{}", encoding="utf-8")
        return {"source_id": source_id, "status": "ok", "fallback_used": False}

    result = run_task_graph(
        [_graph_task("alpha", tmp_path / "alpha.json"), _graph_task("beta", tmp_path / "beta.json"), _graph_task("child", tmp_path / "child.json", ("alpha",))],
        "full", max_workers=2, fetch_fn=fake_fetch,
    )
    assert result.statuses["beta"]["status"] == "ok"
    assert result.statuses["child"]["status"] == "blocked"
    assert "alpha" in result.statuses["child"]["error_summary"]


def test_task_graph_respects_source_ttl_and_emits_skip_metadata(tmp_path):
    from scripts.run_fetchers import run_task_graph

    target = tmp_path / "news.json"
    target.write_text(json.dumps({"items": [{"title": "cached"}]}), encoding="utf-8")
    called = []

    def fake_fetch(*args):
        called.append(args[0])
        raise AssertionError("TTL 內不應重抓")

    result = run_task_graph(
        [_graph_task("news", target)], "full", max_workers=1,
        fetch_fn=fake_fetch, respect_ttl=True,
    )
    assert called == []
    assert result.statuses["news"]["refresh_skipped"] is True
    assert "TTL" in result.statuses["news"]["skip_reason"]
