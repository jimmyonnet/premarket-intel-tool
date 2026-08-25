from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATE = ROOT / ".github/workflows/generate-opening-forecast.yml"
VERIFY = ROOT / ".github/workflows/verify-opening-result.yml"
MAIN = ROOT / ".github/workflows/build-premarket-page.yml"


def test_generation_workflow_has_safe_0830_schedule_and_contract_steps():
    text = GENERATE.read_text(encoding="utf-8")
    assert 'cron: "30 0 * * 1-5"' in text
    assert "fetch_taiex_reference.py" in text
    assert "generate_forecast.py" in text
    assert "verify_opening.py" in text
    assert "--initialize" in text
    assert "--opening-forecast data/latest/opening_forecast.json" in text
    assert "--opening-result data/latest/opening_result.json" in text
    assert "--learning-status data/latest/learning_status.json" in text
    assert "contents: write" in text
    assert "actions/checkout@v7" in text
    assert "actions/setup-python@v7" in text
    assert "GITHUB_TOKEN" not in text


def test_verification_workflow_has_all_retries_and_final_unverified_gate():
    text = VERIFY.read_text(encoding="utf-8")
    assert 'cron: "5 1 * * 1-5"' in text
    assert 'cron: "10 1 * * 1-5"' in text
    assert 'cron: "15 1 * * 1-5"' in text
    assert "verify_opening.py" in text
    assert "--attempted-at" in text
    assert "--final" in text
    assert "record_opening.py" in text
    assert "build_status.py" in text
    assert "stale or incomplete verification" in text.lower()
    assert '"status": "generated"' in text
    assert "contents: write" in text
    assert "GITHUB_TOKEN" not in text


def test_main_build_passes_opening_packages_without_removing_existing_build():
    text = MAIN.read_text(encoding="utf-8")
    assert "--opening-forecast data/latest/opening_forecast.json" in text
    assert "--opening-result data/latest/opening_result.json" in text
    assert "--learning-status data/latest/learning_status.json" in text
    assert "run_fetchers.py" in text
    assert "notify-failure:" in text
