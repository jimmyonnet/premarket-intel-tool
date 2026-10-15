import json
from datetime import date

from scripts.check_freshness import check_artifacts


def _write(docs_dir, name, payload):
    path = docs_dir / "data" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_fresh_artifacts_report_no_problem(tmp_path):
    _write(tmp_path, "opening_forecast.json", {"market_date": "2026-09-11"})
    _write(tmp_path, "opening_result.json", {"market_date": "2026-09-11"})

    assert check_artifacts(tmp_path, date(2026, 9, 11)) == []


def test_stale_artifact_is_reported_with_both_dates(tmp_path):
    _write(tmp_path, "opening_forecast.json", {"market_date": "2026-08-26"})
    _write(tmp_path, "opening_result.json", {"market_date": "2026-09-11"})

    problems = check_artifacts(tmp_path, date(2026, 9, 11))

    assert len(problems) == 1
    assert "opening_forecast.json" in problems[0]
    assert "2026-08-26" in problems[0]
    assert "2026-09-11" in problems[0]


def test_missing_artifact_is_reported(tmp_path):
    _write(tmp_path, "opening_result.json", {"market_date": "2026-09-11"})

    problems = check_artifacts(tmp_path, date(2026, 9, 11))

    assert len(problems) == 1
    assert "opening_forecast.json" in problems[0]


def test_malformed_artifact_is_reported_instead_of_raising(tmp_path):
    _write(tmp_path, "opening_result.json", {"market_date": "2026-09-11"})
    path = tmp_path / "data" / "opening_forecast.json"
    path.write_text("{not valid json", encoding="utf-8")

    problems = check_artifacts(tmp_path, date(2026, 9, 11))

    assert len(problems) == 1
    assert "opening_forecast.json" in problems[0]


def test_missing_date_field_is_reported(tmp_path):
    _write(tmp_path, "opening_forecast.json", {"status": "generated"})
    _write(tmp_path, "opening_result.json", {"market_date": "2026-09-11"})

    problems = check_artifacts(tmp_path, date(2026, 9, 11))

    assert len(problems) == 1
    assert "market_date" in problems[0]


def test_every_stale_artifact_is_reported_not_just_the_first(tmp_path):
    _write(tmp_path, "opening_forecast.json", {"market_date": "2026-08-26"})
    _write(tmp_path, "opening_result.json", {"market_date": "2026-08-26"})

    assert len(check_artifacts(tmp_path, date(2026, 9, 11))) == 2
