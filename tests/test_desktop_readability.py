from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"


def test_desktop_readability_rules_are_scoped_to_desktop_only():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "/* DESKTOP READABILITY" in source
    assert "@media (min-width: 769px)" in source
    assert ".data-table { font-size: 14px; line-height: 1.5; }" in source
    assert ".news-title { font-size: 14px !important; line-height: 1.55; }" in source
    assert ".news-meta { font-size: 12px !important; line-height: 1.5; color: var(--text-muted); }" in source


def test_desktop_readability_rules_keep_mobile_breakpoint_separate():
    source = TEMPLATE.read_text(encoding="utf-8")
    mobile_index = source.index("@media (max-width: 768px)")
    readability_index = source.index("/* DESKTOP READABILITY")

    assert mobile_index < readability_index
