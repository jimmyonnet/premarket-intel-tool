from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def test_news_section_uses_existing_package_for_lazy_hydration():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'id="news-lazy-block"' in source
    assert 'data-news-src="data/news.json"' in source
    assert 'id="news-list"' in source
    assert "window.pm.hydrateNews" in source
    assert "IntersectionObserver" in source
    assert "{% for a in news %}" not in source
    assert "隔夜重大新聞 Top 10" in source
    assert '<details class="unref-accordion news-items-collapsible" id="news-items-disclosure">' in source
    assert '<summary class="unref-summary">展開新聞 10 則</summary>' in source
    assert '📰 新聞摘要' in source
    assert '<div class="card news-card">' in source
    assert '#news-calendar .news-card .news-items-collapsible' in source
    assert 'newsDisclosure.addEventListener(\'toggle\'' in source
    assert '<details class="unref-accordion news-items-collapsible" id="news-items-disclosure" open>' not in source


def test_deployed_news_list_stays_collapsed():
    source = DEPLOYED.read_text(encoding="utf-8")
    assert '<details class="unref-accordion news-items-collapsible" id="news-items-disclosure">' in source
    assert '<summary class="unref-summary">展開新聞 10 則</summary>' in source
    assert '<details class="unref-accordion news-items-collapsible" id="news-items-disclosure" open>' not in source
