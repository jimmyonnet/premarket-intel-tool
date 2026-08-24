from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "scripts" / "templates" / "premarket.html.j2"


def test_news_section_uses_existing_package_for_lazy_hydration():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'id="news-lazy-block"' in source
    assert 'data-news-src="data/news.json"' in source
    assert 'id="news-list"' in source
    assert "window.pm.hydrateNews" in source
    assert "IntersectionObserver" in source
    assert "{% for a in news %}" not in source
    assert "隔夜重大新聞 Top 10" in source
