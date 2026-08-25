from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-premarket-page.yml"
RUNNER = ROOT / "scripts" / "run_fetchers.py"
NIGHT_WORKFLOW = ROOT / ".github" / "workflows" / "collect-night-session.yml"
REQUIREMENTS = ROOT / "requirements.txt"


def test_scheduled_section_modes_and_manual_full_refresh_are_explicit():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    # 19:35 Taipei: allow five minutes after Chengwaye's 19:30 disposal update.
    assert '"35 11 * * 1-5") mode="disposal"' in workflow

    # 21:00 and 23:00 Taipei candidate / PressPlay refreshes.
    assert 'mode="candidates"' in workflow
    assert '"0 13 * * 0-4"' in workflow
    assert '"0 15 * * 0-4"' in workflow

    # 07:30 Taipei morning-core refresh.
    assert '"30 23 * * 0-4"' in workflow
    assert 'mode="morning-core"' in workflow

    # Manual workflow_dispatch retains complete-page refresh behavior.
    assert 'mode="full"' in workflow
    for mode in ("morning-core", "asia-open-update", "disposal", "candidates"):
        assert f'"{mode}"' in runner


def test_candidate_and_announcement_modes_are_present_in_the_task_catalog():
    runner = RUNNER.read_text(encoding="utf-8")

    assert '"pressplay": FetchTask(' in runner
    assert 'modes=("full", "candidates", "morning-core")' in runner
    assert '"chengwaye_daily": FetchTask(' in runner
    assert 'dependencies=("pressplay",)' in runner
    assert '"chengwaye_stock_history": FetchTask(' in runner
    assert 'dependencies=("pressplay", "chengwaye_daily")' in runner
    assert '"financials": FetchTask(' in runner
    assert 'modes=("full", "financials")' in runner


def test_workflow_splits_full_quality_from_scheduled_smoke_and_caches_dependencies():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "full-quality:" in workflow
    assert "github.event_name == 'pull_request'" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "tests/test_smoke_contract.py" in workflow
    assert "python -m pytest tests/ -q" in workflow
    assert "cache: pip" in workflow
    assert "cache-dependency-path: requirements.txt" in workflow
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "actions/cache@v6" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow
    assert "actions/cache@v4" not in workflow
    assert "~/.cache/ms-playwright" in workflow
    assert "playwright-${{ runner.os }}-1.62.0-${{ hashFiles('requirements.txt') }}" in workflow
    assert "playwright-${{ runner.os }}-1.62.0-" in workflow
    assert "trading_calendar.py update" in workflow
    assert "--respect-ttl" in workflow
    assert "git pull --rebase origin main && git push" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "needs: [full-quality]" in workflow
    assert "always()" in workflow
    assert "needs.full-quality.result == 'success'" in workflow
    assert "needs.full-quality.result == 'skipped'" in workflow
    assert "notify-failure:" in workflow
    assert "needs: [full-quality, build]" in workflow
    assert "needs.full-quality.result == 'failure'" in workflow
    assert "needs.full-quality.result == 'cancelled'" in workflow
    assert "needs.build.result == 'failure'" in workflow
    assert "needs.build.result == 'cancelled'" in workflow
    assert "notify_summary.py --mode success || true" not in workflow
    assert "notify_summary.py --mode failure || true" not in workflow
    assert "npx --yes terser" not in workflow
    assert "cancel-in-progress: false" in workflow


def test_requirements_are_exactly_pinned():
    lines = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    assert lines
    assert all("==" in line and ">=" not in line and "<" not in line for line in lines)


def test_night_session_workflow_has_timeout_cache_and_push_retry():
    workflow = NIGHT_WORKFLOW.read_text(encoding="utf-8")
    assert "timeout-minutes: 5" in workflow
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "cache: pip" in workflow
    assert "cache-dependency-path: requirements.txt" in workflow
    assert "git pull --rebase origin main && git push" in workflow
    assert "after 3 attempts" in workflow
