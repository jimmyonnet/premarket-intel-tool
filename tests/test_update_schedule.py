from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-premarket-page.yml"
RUNNER = ROOT / "scripts" / "run_fetchers.py"


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


def test_candidate_and_announcement_modes_refresh_the_complete_section_sources():
    runner = RUNNER.read_text(encoding="utf-8")

    assert 'if args.mode in ("full", "candidates", "morning-core"):' in runner
    assert 'status_map["pressplay"] = fetch_source(' in runner
    assert 'status_map["chengwaye_daily"] = fetch_source(' in runner
    assert 'if args.mode in ("full", "financials"):' in runner
    assert 'status_map["financials"] = fetch_source(' in runner
