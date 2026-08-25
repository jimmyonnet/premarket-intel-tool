from pathlib import Path

from scripts.run_fetchers import _task_catalog
from scripts.source_status import RELIABILITY_TIERS, SOURCES_METADATA

ROOT = Path(__file__).resolve().parents[1]


def test_reliability_catalog_has_three_tiers_and_every_source_policy():
    assert set(RELIABILITY_TIERS) == {"core_stable", "important_short_stale", "high_risk"}
    assert SOURCES_METADATA
    for source_id, meta in SOURCES_METADATA.items():
        assert meta["reliability_tier"] in RELIABILITY_TIERS, source_id
        assert meta["ttl_minutes"] > 0
        assert meta["hard_expiry_minutes"] >= meta["ttl_minutes"]
        assert meta["notification_level"] in {"critical", "warning", "notice"}
        assert isinstance(meta["dependencies"], list)


def test_fetch_task_catalog_dependencies_are_known_and_acyclic():
    tasks = _task_catalog("python", ROOT / "data/latest", "2026-08-25")
    ids = set(tasks)
    for task in tasks.values():
        assert set(task.dependencies) <= ids
    assert tasks["chengwaye_daily"].dependencies == ("pressplay",)
    assert tasks["chengwaye_stock_history"].dependencies == ("pressplay", "chengwaye_daily")


def test_core_scripts_compile_as_schedule_smoke_contract():
    for path in (ROOT / "scripts/trading_calendar.py", ROOT / "scripts/run_fetchers.py", ROOT / "scripts/validate_data.py"):
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
