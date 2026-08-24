from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"


def test_candidate_section_precedes_alert_section_in_navigation_and_content():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.index('href="#watchlist"') < source.index('href="#alerts"')
    assert source.index('<section id="watchlist" class="content-section">') < source.index(
        '<section id="alerts" class="content-section">'
    )
