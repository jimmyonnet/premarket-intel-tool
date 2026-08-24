from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "templates" / "premarket.html.j2"
DEPLOYED = ROOT / "docs" / "index.html"


def _watchlist_block(text: str) -> str:
    marker = '<section id="self-watchlist" class="content-section">'
    start = text.index(marker)
    end = text.index('    </section>', start) + len('    </section>')
    return text[start:end]


def test_watchlist_uses_collapsed_summary_with_hit_placeholder():
    source = TEMPLATE.read_text(encoding="utf-8")
    block = _watchlist_block(source)

    assert '<details class="card watchlist-card watchlist-details">' in block
    assert '<h2 class="card-title"><span class="title-icon">⭐</span> 我在看</h2>' in block
    assert '我在看（自選關注標的）' not in block
    assert 'id="watch-summary-hits"' in block
    assert 'class="watch-summary-info"' in block
    assert 'title="即時比對今日處置、出關與候選清單 · 本機自動儲存"' in block
    assert '>即時比對今日處置、出關與候選清單 · 本機自動儲存<' not in block
    assert '<details class="card watchlist-card watchlist-details" open>' not in block
    assert 'summaryItems = hitAlerts.concat(hitCandidates)' in source
    assert 'summaryItems = hitAlerts.concat(hitCandidates, otherStocks)' not in source
    assert "totalBadge.textContent = summaryItems.length + ' 檔';" in source
    assert "var summaryChip = document.createElement('button');" in source
    assert 'summaryChip.onclick = function(event)' in source
    assert 'focusWatchTarget(item.code);' in source
    assert "item.code + (item.hit && item.hit.label" in source
    assert 'watch-summary-more' not in source
    assert 'watch-summary-chip.is-amber' in source
    assert 'watch-summary-chip.is-other' not in source
    assert '.watch-summary-chip.is-amber,\n  .watch-chip.amber' in source
    assert '.watch-summary-chip.is-candidate,\n  .watch-chip.blue' in source
    assert 'button.watch-summary-chip.is-amber { color: var(--amber) !important; }' in source
    assert 'button.watch-summary-chip.is-candidate { color: var(--blue) !important; }' in source
    assert 'function focusWatchTarget(c)' in source
    assert 'chip.onclick = function() { focusWatchTarget(c); };' in source
    assert "hit.type === 'blue' || hit.type === 'normal'" in source


def test_deployed_watchlist_is_collapsed_by_default_and_keeps_management_controls():
    block = _watchlist_block(DEPLOYED.read_text(encoding="utf-8"))

    assert '<details class="card watchlist-card watchlist-details">' in block
    assert '<details class="card watchlist-card watchlist-details" open>' not in block
    assert 'id="watch-summary-hits"' in block
    assert 'id="watch-edit-toggle-btn"' in block
    assert 'id="watch-chips"' in block
