const state = {
  meta: null,
  packages: new Map(),
  store: loadStore(),
  selectedCommand: 0,
  commands: [],
};

const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const num = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').replace(/%|億/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
};
const fmt = (value, digits = 2) => {
  const n = num(value);
  return n === null ? '—' : n.toLocaleString('zh-TW', {minimumFractionDigits: digits, maximumFractionDigits: digits});
};
const signed = (value, digits = 2, suffix = '') => {
  const n = num(value);
  return n === null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(digits)}${suffix}`;
};
const metricClass = (value) => num(value) > 0 ? 'up' : num(value) < 0 ? 'down' : 'flat';
const idle = window.requestIdleCallback || ((callback) => window.setTimeout(callback, 80));

function loadStore() {
  const fallbacks = ['pmit.store', 'pmit_watchlist', 'premarket.watchlist'];
  for (const key of fallbacks) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      if (key === 'pmit.store' && parsed && typeof parsed === 'object') {
        return {watchlist: Array.isArray(parsed.watchlist) ? parsed.watchlist.map(String) : [], theme: parsed.theme || 'light', density: parsed.density || 'comfortable', watchOnly: Boolean(parsed.watchOnly)};
      }
      const list = Array.isArray(parsed) ? parsed : parsed?.watchlist;
      if (Array.isArray(list)) return {watchlist: list.map(String), theme: localStorage.getItem('pmit_theme') || 'light', density: 'comfortable', watchOnly: localStorage.getItem('pmit_watch_only') === '1'};
    } catch (_) {}
  }
  return {watchlist: [], theme: 'light', density: 'comfortable', watchOnly: false};
}

function saveStore(patch) {
  state.store = {...state.store, ...patch};
  try { localStorage.setItem('pmit.store', JSON.stringify(state.store)); } catch (_) {}
}

async function fetchJson(key) {
  const source = state.meta?.packages?.[key] || `data/${key}.json`;
  const hash = state.meta?.hash?.[key];
  const url = `${source}${source.includes('?') ? '&' : '?'}h=${encodeURIComponent(hash || '')}`;
  const response = await fetch(url, {cache: key === 'meta' ? 'no-cache' : 'force-cache'});
  if (!response.ok) throw new Error(`${key}: HTTP ${response.status}`);
  return response.json();
}

async function loadPackage(key, render) {
  if (state.packages.has(key)) return state.packages.get(key);
  const promise = fetchJson(key).then((payload) => {
    state.packages.set(key, payload);
    render?.(payload);
    updatePackageStatus();
    return payload;
  }).catch((error) => {
    const panel = document.querySelector(`[data-package="${key}"]`);
    if (panel) panel.innerHTML = `<div class="empty">資料暫時無法載入：${esc(error.message)}</div>`;
    showToast(`${key} 資料載入失敗`);
    throw error;
  });
  state.packages.set(key, promise);
  return promise;
}

function updatePackageStatus() {
  const el = $('#package-status');
  if (!el) return;
  const loaded = [...state.packages.keys()].join('、') || '尚無';
  el.textContent = `已載入分包：${loaded}；建置 ${document.body.dataset.buildVersion || '—'}`;
}

function stockHref(code, market = '') {
  const venue = /櫃|OTC|TPEX/i.test(market) ? 'TPEX' : 'TWSE';
  return `https://tw.tradingview.com/chart/?symbol=${venue}:${encodeURIComponent(code)}`;
}

function focusStock(code) {
  const row = [...document.querySelectorAll('[data-code]')].find((node) => node.dataset.code === String(code));
  if (!row) { showToast(`${code} 尚未出現在目前區塊`); return; }
  row.scrollIntoView({behavior:'smooth', block:'center'});
  row.classList.add('is-highlight');
  window.setTimeout(() => row.classList.remove('is-highlight'), 1800);
}
window.focusStock = focusStock;

function dispositionRow(item, compact = false) {
  const rule = item.primary_rule;
  const progress = rule ? Math.min(100, Math.max(0, (rule.hit / rule.need) * 100)) : 0;
  const trigger = item.trigger;
  const triggerText = trigger ? `${fmt(trigger.price, 2)} ${trigger.direction === 'down' ? '跌破' : '突破'}${trigger.pct === null ? '' : ` (${signed(trigger.pct, 1, '%')})`}` : '門檻待確認';
  return `<div class="${compact ? 'deck-row' : 'list-row'}" data-code="${esc(item.code)}" role="button" tabindex="0">
    <div class="deck-main"><span class="deck-title">${esc(item.code)} ${esc(item.name)} ${item.locked ? '<span class="badge locked">⚑ 鎖定</span>' : ''}</span>
      <span class="deck-sub">${esc(triggerText)} · ${esc(item.eta || '日期待確認')}</span></div>
    ${rule ? `<span class="badge ${rule.remain <= 1 ? 'warn' : ''}">${esc(rule.id)} ${rule.hit}/${rule.need}</span>` : '<span class="badge">—</span>'}
  </div>`;
}

function releaseRow(item, compact = false) {
  const seconds = item.match_seconds ? `${Math.round(item.match_seconds / 60)}分` : (item.matching || '撮合待確認');
  return `<div class="${compact ? 'deck-row' : 'list-row'}" data-code="${esc(item.code)}" role="button" tabindex="0">
    <div class="deck-main"><span class="deck-title">${esc(item.code)} ${esc(item.name)}</span><span class="deck-sub">${esc(item.exit_date || '今日')} · 原撮合 ${esc(seconds)}</span></div><span class="badge release">🔓 出關</span>
  </div>`;
}

function bindStockRows(root = document) {
  root.querySelectorAll('[data-code]').forEach((row) => {
    if (row.dataset.bound) return;
    row.dataset.bound = '1';
    row.addEventListener('click', () => focusStock(row.dataset.code));
    row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); focusStock(row.dataset.code); } });
  });
}

function renderActionDeck(pkg) {
  const items = pkg.items || [];
  const releases = pkg.releases || [];
  $('#disposition-count').textContent = items.length;
  $('#release-count').textContent = releases.length;
  const disp = items.slice(0, 5).map((item) => dispositionRow(item, true)).join('');
  const rel = releases.slice(0, 5).map((item) => releaseRow(item, true)).join('');
  $('#disposition-deck').innerHTML = disp || '<div class="empty">今日無處置倒數</div>';
  $('#release-deck').innerHTML = rel || '<div class="empty">今日無出關</div>';
  if (items.length > 5) $('#disposition-deck').insertAdjacentHTML('beforeend', `<button class="more-row" data-goto="alerts">+${items.length - 5} 檔 ▾</button>`);
  if (releases.length > 5) $('#release-deck').insertAdjacentHTML('beforeend', `<button class="more-row" data-goto="alerts">+${releases.length - 5} 檔 ▾</button>`);
  bindStockRows($('#action-deck'));
  $('#action-deck').querySelectorAll('[data-goto]').forEach((button) => button.addEventListener('click', () => document.getElementById(button.dataset.goto)?.scrollIntoView({behavior:'smooth'})));
  renderDispositionPanel(pkg);
  refreshCommands();
}

function targetMarkup(item) {
  const target = item.trigger;
  if (!target) return '<span class="flat">—</span>';
  const delta = target.pct === null ? '' : `${signed(target.pct, 1, '%')} 即觸發`;
  return `<div class="target-axis"><span class="target-now">昨收 ${esc(fmt(item.close, 2))}</span><span class="target-trip">${esc(fmt(target.price, 2))}</span></div><small class="target-delta ${target.direction === 'down' ? 'down' : 'up'}">${esc(delta || target.type)}</small>`;
}

function renderDispositionPanel(pkg) {
  const panel = $('#disposition-panel');
  const items = pkg.items || [];
  if (!items.length) { panel.innerHTML = '<div class="empty">今日無差 1 次即處置的標的。</div>'; return; }
  panel.innerHTML = `<div class="panel-toolbar"><strong>差 1 次即處置 · ${items.length} 檔</strong><span class="section-note">按最短剩餘次數排序</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>市場</th><th>代號 / 名稱</th><th class="rule">最短路徑</th><th>觸發價靶心</th><th>最快處置</th></tr></thead><tbody>${items.map((item) => {
    const rule = item.primary_rule;
    const progress = rule ? Math.min(100, Math.max(0, (rule.hit / rule.need) * 100)) : 0;
    return `<tr data-code="${esc(item.code)}"><td data-label="市場">${esc(item.market)}</td><td data-label="代號 / 名稱" class="code"><a href="${stockHref(item.code, item.market)}" target="_blank" rel="noopener noreferrer">${esc(item.code)}</a><br><span>${esc(item.name)}</span>${item.locked ? ' <span class="badge locked">⚑ 鎖定</span>' : ''}</td><td data-label="最短路徑" class="rule">${rule ? `<div class="rule-bar ${rule.remain <= 1 ? 'is-near' : ''}" style="--progress:${progress}%"><span>${esc(rule.label || rule.id)} · ${rule.hit}/${rule.need} · ${rule.remain ? `再 ${rule.remain} 次` : '已達標'}</span></div>` : '<span class="flat">規則待確認</span>'}</td><td data-label="觸發價靶心">${targetMarkup(item)}</td><td data-label="最快處置" class="font-mono">${esc(item.earliest_disposal || '—')}</td></tr>`;
  }).join('')}</tbody></table></div>`;
  bindStockRows(panel);
}

function renderWatchDeck(pkg) {
  const codes = new Set((state.store.watchlist || []).map(String));
  const hits = (pkg.items || []).filter((item) => codes.has(String(item.code)));
  $('#watch-count').textContent = hits.length;
  $('#watch-deck').innerHTML = hits.length ? hits.slice(0, 5).map((item) => `<div class="deck-row" data-code="${esc(item.code)}"><div class="deck-main"><span class="deck-title"><span class="deck-mark">★</span> ${esc(item.code)} ${esc(item.name)}</span><span class="deck-sub">${esc(item.group || '籌碼命中')} · 外資 ${esc(item.foreign_display ?? signed(item.foreign, 0))}</span></div><span class="badge">籌碼</span></div>`).join('') : '<div class="empty">尚未設定自選股，或今日無命中。</div>';
  if (hits.length > 5) $('#watch-deck').insertAdjacentHTML('beforeend', `<button class="more-row" data-goto="watchlist">+${hits.length - 5} 檔 ▾</button>`);
  bindStockRows($('#watch-deck'));
}

function renderCandidatePanel(pkg) {
  const items = pkg.items || [];
  $('#candidate-source').textContent = `PressPlay · ${pkg.chengwaye_date || '日期待確認'}`;
  const panel = $('#candidate-panel');
  if (!items.length) { panel.innerHTML = '<div class="empty">尚無籌碼股資料。</div>'; return; }
  panel.innerHTML = `<div class="panel-toolbar"><input class="filter-input" id="candidate-filter" type="search" placeholder="搜尋代號 / 名稱 / 族群…" aria-label="搜尋籌碼股"><span class="section-note">${items.length} 檔 · 量能以背景長條表示</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>市場</th><th>代號 / 名稱</th><th class="num">收盤</th><th class="num">量(張)</th><th class="num">外資</th><th class="num">投信</th><th class="num">自營</th><th>訊號</th></tr></thead><tbody id="candidate-body">${items.map(candidateRow).join('')}</tbody></table></div>`;
  $('#candidate-filter').addEventListener('input', (event) => filterCandidateRows(event.target.value));
  bindStockRows(panel);
  renderWatchDeck(pkg);
  renderCrossMatch();
  refreshCommands();
}

function renderCrossMatch() {
  const panel = $('#crossmatch-panel');
  if (!panel) return;
  const watchlist = (state.store.watchlist || []).map(String);
  if (!watchlist.length) { panel.hidden = true; return; }
  const byCode = new Map();
  const add = (signal, item) => {
    const code = String(item?.code || '').replace('⏸', '').trim();
    if (!code) return;
    if (!byCode.has(code)) byCode.set(code, []);
    byCode.get(code).push({signal, item});
  };
  const disposition = state.packages.get('disposition');
  if (disposition?.items) disposition.items.forEach((item) => add('處置預警', item));
  if (disposition?.releases) disposition.releases.forEach((item) => add('今日出關', item));
  const candidates = state.packages.get('candidates');
  if (candidates?.items) candidates.items.forEach((item) => add('籌碼股', item));
  const announcements = state.packages.get('announcements');
  Object.values(announcements?.blocks || {}).forEach((block) => (block.rows || []).forEach((item) => add('財報未反映', item)));
  const matches = watchlist.map((code) => ({code, hits: byCode.get(code) || []})).filter((entry) => entry.hits.length).sort((a, b) => b.hits.length - a.hits.length);
  if (!matches.length) { panel.hidden = false; panel.innerHTML = '<div class="panel-toolbar"><strong>自選股 × 全訊號</strong></div><div class="empty">今日沒有自選股訊號命中。</div>'; return; }
  panel.hidden = false;
  panel.innerHTML = `<div class="panel-toolbar"><strong>自選股 × 全訊號</strong><span class="section-note">只顯示命中列 · 多重命中優先</span></div><div class="table-wrap"><table><thead><tr><th>代號</th><th>命中數</th><th>訊號</th><th>摘要</th></tr></thead><tbody>${matches.map((entry) => {
    const first = entry.hits[0].item;
    return `<tr data-code="${esc(entry.code)}"><td class="code">${esc(entry.code)} ${esc(first.name || '')}</td><td class="num font-mono">${entry.hits.length}</td><td>${entry.hits.map((hit) => `<span class="badge ${hit.signal === '處置預警' ? 'halt' : hit.signal === '今日出關' ? 'release' : 'warn'}">${esc(hit.signal)}</span>`).join(' ')}</td><td>${esc(first.ai_reason || first.condition || first.earliest_disposal || first.group || '已命中')}</td></tr>`;
  }).join('')}</tbody></table></div>`;
  bindStockRows(panel);
}

function candidateRow(item) {
  const max = num(item.volume_max) || 1;
  const volume = num(item.volume) || 0;
  const score = num(item.ai_score);
  const tier = score === null ? 'b' : score >= 6 ? 's' : score >= 3 ? 'a' : score >= -2 ? 'b' : score >= -5 ? 'c' : 'd';
  return `<tr data-code="${esc(item.code)}" data-search="${esc(`${item.code} ${item.name} ${item.group || ''}`.toLowerCase())}"><td data-label="市場">${esc(item.market)}</td><td data-label="代號 / 名稱" class="code"><a href="${stockHref(item.code, item.market)}" target="_blank" rel="noopener noreferrer">${esc(item.code)}</a><br><span>${esc(item.name)}</span></td><td data-label="收盤" class="num font-mono">${esc(fmt(item.close, 2))}</td><td data-label="量(張)" class="num font-mono vol-cell" style="--volume-p:${Math.round(volume / max * 100)}%">${esc(item.volume_display ?? fmt(item.volume, 0))}</td><td data-label="外資" class="num font-mono ${metricClass(item.foreign)}">${esc(item.foreign_display ?? signed(item.foreign, 0))}</td><td data-label="投信" class="num font-mono ${metricClass(item.trust)}">${esc(item.trust_display ?? signed(item.trust, 0))}</td><td data-label="自營" class="num font-mono ${metricClass(item.dealer)}">${esc(item.dealer_display ?? signed(item.dealer, 0))}</td><td data-label="訊號"><span class="badge">${esc(item.group || '籌碼')}</span></td></tr>`;
}

function filterCandidateRows(query) {
  const needle = String(query || '').trim().toLowerCase();
  document.querySelectorAll('#candidate-body tr').forEach((row) => { row.hidden = Boolean(needle && !row.dataset.search.includes(needle)); });
}

function deltaMarkup(value, previous, explicit = null, suffix = '') {
  const delta = explicit !== null && explicit !== undefined ? num(explicit) : (num(value) !== null && num(previous) !== null ? num(value) - num(previous) : null);
  return `<span class="metric__v">${esc(fmt(value))}${suffix}</span><span class="metric__d ${metricClass(delta)}">${delta === null ? '—' : `${delta > 0 ? '▲+' : delta < 0 ? '▼' : '—'}${delta === 0 ? '0.00' : Math.abs(delta).toFixed(2)}${suffix}`}</span>`;
}

function renderFinancialRow(row) {
  const ai = num(row.ai_score);
  return `<tr class="financial-main" data-code="${esc(row.code)}"><td data-label="時間" class="font-mono">${esc(row.time || '—')}</td><td data-label="代號 / 名稱" class="code">${esc(row.code)}<br><span>${esc(row.name)}</span></td><td data-label="AI"><span class="ai-chip" data-tier="${ai === null ? 'b' : ai >= 6 ? 's' : ai >= 3 ? 'a' : ai >= -2 ? 'b' : ai >= -5 ? 'c' : 'd'}">${ai === null ? '—' : esc(ai.toFixed(0))}</span></td><td data-label="季度" class="font-mono">${esc(row.period || '—')}</td><td data-label="EPS" class="metric">${deltaMarkup(row.eps, row.prev_eps, row.d_eps)}</td><td data-label="毛利率" class="metric">${deltaMarkup(row.gm, row.prev_gm, row.d_gm, '%')}</td><td data-label="營益率" class="metric">${deltaMarkup(row.om, row.prev_om, row.d_om, '%')}</td></tr><tr class="detail-row" hidden><td colspan="7"><div class="detail-grid"><div><strong>公告主旨</strong>${esc(row.subject || '—')}</div><div><strong>AI 理由</strong>${esc(row.ai_reason || '—')}</div><div><strong>公告時間</strong>${esc(row.date || '—')} ${esc(row.time || '')}</div></div></td></tr>`;
}

function renderAnnouncements(pkg) {
  const panel = $('#announcements-panel');
  const blocks = pkg.blocks || {};
  const labels = {att:'即時自結', fin:'即時季報', rev:'即時營收'};
  const html = Object.entries(labels).map(([key, label]) => {
    const rows = blocks[key]?.rows || [];
    return `<details class="native-details" ${rows.length ? '' : ''}><summary>${label}<span class="badge">${rows.length} 筆</span></summary>${rows.length ? `<div class="table-wrap"><table class="data-table financial-table"><thead><tr><th>時間</th><th>代號 / 名稱</th><th>AI</th><th>季度</th><th class="num">EPS (Δ)</th><th class="num">毛利率 (Δ)</th><th class="num">營益率 (Δ)</th></tr></thead><tbody>${rows.map(renderFinancialRow).join('')}</tbody></table></div>` : '<div class="empty">此區塊今日無資料。</div>'}</details>`;
  }).join('');
  panel.innerHTML = html || '<div class="empty">尚無公告資料。</div>';
  panel.querySelectorAll('.financial-main').forEach((row) => row.addEventListener('click', () => { const detail = row.nextElementSibling; if (detail) detail.hidden = !detail.hidden; }));
}

function renderFlow(name, value, max) {
  const n = num(value) || 0;
  const width = max ? Math.min(100, Math.abs(n) / max * 100) : 0;
  return `<div class="flow-row"><span>${esc(name)}</span><div class="flow-bar ${n < 0 ? 'is-negative' : ''}" style="--flow-p:${width}%"></div><b class="flow-value ${metricClass(n)}">${esc(signed(n, 2, '億'))}</b></div>`;
}

function renderQuoteCard(item, fallbackLabel, kind) {
  const quote = item || {};
  const value = quote.value ?? quote.price;
  const pct = num(quote.change_pct);
  const trend = pct > 0 ? 'is-up' : pct < 0 ? 'is-down' : 'is-flat';
  const arrow = pct > 0 ? '▲' : pct < 0 ? '▼' : '—';
  return `<article class="quote-card ${trend}" data-market-kind="${esc(kind)}"><div class="quote-head"><strong>${esc(quote.name || fallbackLabel)}</strong><span>${esc(quote.ticker || '')}</span></div><div class="quote-value">${esc(fmt(value, value !== null && Math.abs(value) < 100 ? 2 : 2))}</div><div class="quote-change">${arrow} ${esc(pct === null ? '—' : signed(pct, 2, '%'))}</div></article>`;
}

function renderMacro(pkg) {
  const twse = pkg.twse || {};
  const indices = pkg.indices || {};
  const us = indices.us_indices || {};
  const night = pkg.night?.latest || {};
  const inst = twse.inst || {};
  const maxInst = Math.max(Math.abs(num(inst.foreign) || 0), Math.abs(num(inst.trust) || 0), Math.abs(num(inst.dealer) || 0), 1);
  const strip = `<span class="market-item">加權 <b class="${metricClass(twse.twii?.change)}">${esc(fmt(twse.twii?.price))} ${esc(signed(twse.twii?.change_pct, 2, '%'))}</b></span><span class="market-item">外資 ${esc(signed(inst.foreign, 2, '億'))} · 投信 ${esc(signed(inst.trust, 2, '億'))} · 自營 ${esc(signed(inst.dealer, 2, '億'))}</span><span class="market-item">夜盤 <b class="${metricClass(night.change)}">${esc(fmt(night.price, 0))} ${esc(signed(night.change_pct, 2, '%'))}</b></span>`;
  $('#market-strip').innerHTML = strip;
  const indexKeys = [['dow', '道瓊工業指數'], ['sp500', 'S&P 500指數'], ['nasdaq', 'NASDAQ指數'], ['sox', '費城半導體指數']];
  const adrKeys = [['tsmc', '台積電 ADR'], ['nvda', '輝達 (NVDA)'], ['aapl', '蘋果 (AAPL)'], ['umc', '聯電 ADR'], ['ase', '日月光 ADR'], ['tsmc_tw', '台積電 現貨']];
  const adrSource = indices.adrs || indices.key_stocks || {};
  const indexCards = indexKeys.map(([key, label]) => renderQuoteCard(us[key], label, 'us-index')).join('');
  const adrCards = adrKeys.map(([key, label]) => renderQuoteCard(adrSource[key], label, 'adr')).join('');
  $('#macro-panel').innerHTML = `<div class="market-strip"><span class="market-item">加權 <b class="${metricClass(twse.twii?.change)}">${esc(fmt(twse.twii?.price))} ${esc(signed(twse.twii?.change_pct, 2, '%'))}</b></span><span class="market-item">夜盤 <b class="${metricClass(night.change)}">${esc(fmt(night.price, 0))} ${esc(signed(night.change_pct, 2, '%'))}</b></span></div><h3>三大法人對稱橫條</h3><div>${renderFlow('外資', inst.foreign, maxInst)}${renderFlow('投信', inst.trust, maxInst)}${renderFlow('自營商', inst.dealer, maxInst)}</div><h3>美股收盤</h3><div class="quote-grid">${indexCards || '<span class="flat">尚無美股資料</span>'}</div><h3>ADR / 關聯股</h3><div class="quote-grid quote-grid--adr">${adrCards || '<span class="flat">尚無 ADR 資料</span>'}</div>`;
}

function renderCalendar(pkg) {
  const events = (pkg.events || []).slice(0, 12);
  $('#calendar-panel').innerHTML = `<div class="panel-toolbar"><strong>今日與近期事件</strong><span class="section-note">${esc(pkg.today || '—')}</span></div>${events.map((event) => `<div class="calendar-event"><span class="badge ${event.importance === 3 ? 'warn' : ''}">${event.importance === 3 ? '★★★' : '事件'}</span> <strong>${esc(event.time_tpe_str || event.time || '—')}</strong> ${esc(event.title || '')}</div>`).join('') || '<div class="empty">今日無事件。</div>'}`;
}

function renderNews(pkg) {
  const items = Array.isArray(pkg) ? pkg : (pkg.items || pkg.news || []);
  $('#news-panel').innerHTML = `<div class="panel-toolbar"><strong>盤前新聞</strong><span class="section-note">${items.length} 則</span></div>${items.slice(0, 12).map((item) => `<div class="news-item"><a href="${esc(item.url || '#')}" target="_blank" rel="noopener noreferrer">${esc(item.title || item.headline || '未命名新聞')}</a><span class="section-note">${esc(item.source || '')}</span></div>`).join('') || '<div class="empty">尚無新聞資料。</div>'}`;
}

function refreshCommands() {
  const commands = [
    {title:'跳至：今日摘要', hint:'區塊', run:() => gotoSection('summary')},
    {title:'跳至：⚠️ 處置股', hint:'區塊', run:() => gotoSection('alerts')},
    {title:'跳至：🎯 籌碼股', hint:'區塊', run:() => gotoSection('watchlist')},
    {title:'跳至：財報 alpha', hint:'區塊', run:() => gotoSection('announcements')},
    {title:'切換深色模式', hint:'主題', run:toggleTheme},
    {title:'密度：緊湊', hint:'顯示', run:() => setDensity('compact')},
    {title:'密度：研究', hint:'顯示', run:() => setDensity('research')},
    {title:'密度：舒適', hint:'顯示', run:() => setDensity('comfortable')},
    {title:'匯出作戰卡', hint:'剪貼簿', run:exportCard},
  ];
  for (const pkg of state.packages.values()) {
    if (pkg?.items) for (const item of pkg.items.slice(0, 100)) commands.push({title:`${item.code} ${item.name}`, hint:item.group || '股票', run:() => focusStock(item.code)});
  }
  state.commands = commands;
  renderCommandList();
}

function renderCommandList(query = '') {
  const list = $('#command-list');
  if (!list) return;
  const needle = String(query).trim().toLowerCase();
  const filtered = state.commands.filter((command) => command.title.toLowerCase().includes(needle) || command.hint.toLowerCase().includes(needle));
  state.selectedCommand = Math.min(state.selectedCommand, Math.max(0, filtered.length - 1));
  list.innerHTML = filtered.slice(0, 40).map((command, index) => `<button class="command-item ${index === state.selectedCommand ? 'is-selected' : ''}" data-command-index="${index}" type="button"><span>${esc(command.title)}</span><small>${esc(command.hint)}</small></button>`).join('') || '<div class="empty">找不到符合的命令。</div>';
  list.querySelectorAll('[data-command-index]').forEach((button) => button.addEventListener('click', () => { filtered[Number(button.dataset.commandIndex)]?.run(); closeCommandDialog(); }));
}

function openCommandDialog() { const dialog = $('#command-dialog'); if (!dialog) return; if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open',''); const input = $('#command-input'); input.value = ''; state.selectedCommand = 0; renderCommandList(); input.focus(); }
function closeCommandDialog() { const dialog = $('#command-dialog'); if (dialog?.open) dialog.close(); }
function gotoSection(id) { document.getElementById(id)?.scrollIntoView({behavior:'smooth'}); }
function toggleTheme() { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; saveStore({theme}); }
function setDensity(density) { document.documentElement.dataset.density = density; saveStore({density}); showToast(`顯示密度：${density}`); }
function exportCard() {
  const text = [...document.querySelectorAll('.deck')].map((deck) => `${deck.querySelector('h2')?.textContent}\n${deck.querySelector('.deck-body')?.innerText || '—'}`).join('\n\n');
  navigator.clipboard?.writeText(text).then(() => showToast('作戰卡已複製')).catch(() => showToast('瀏覽器未允許剪貼簿存取'));
}
function showToast(message) { const toast = $('#toast'); if (!toast) return; toast.textContent = message; toast.classList.add('is-visible'); window.clearTimeout(showToast.timer); showToast.timer = window.setTimeout(() => toast.classList.remove('is-visible'), 2200); }

function renderHealth() {
  const sources = state.meta?.sources || [];
  $('#health-list').innerHTML = sources.map((source) => `<div class="health-row"><span>${esc(source.name || source.source_id)}</span><span class="badge ${source.status === 'ok' ? 'release' : 'warn'}">${esc(source.status || 'unknown')}</span></div>`).join('') || '<div class="empty">尚無來源狀態。</div>';
}
function toggleHealth() { const popover = $('#health-popover'); const isHidden = popover.hidden; popover.hidden = !isHidden; $('#source-status-btn').setAttribute('aria-expanded', String(isHidden)); if (isHidden) renderHealth(); }

function observeLazyBlocks() {
  const blocks = document.querySelectorAll('.lazy-block');
  const observer = new IntersectionObserver((entries, obs) => {
    for (const entry of entries) if (entry.isIntersecting) {
      const key = entry.target.dataset.package;
      const renderers = {announcements:renderAnnouncements, macro:renderMacro, calendar:renderCalendar, news:renderNews};
      loadPackage(key, renderers[key]).catch(() => {});
      obs.unobserve(entry.target);
    }
  }, {rootMargin:'240px'});
  blocks.forEach((block) => observer.observe(block));
}

async function boot() {
  try {
    state.meta = await fetchJson('meta');
    document.documentElement.dataset.theme = state.store.theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.density = state.store.density || 'comfortable';
    renderHealth();
    const [disposition, macro] = await Promise.all([loadPackage('disposition'), loadPackage('macro')]);
    renderActionDeck(disposition);
    renderMacro(macro);
    idle(() => {
      loadPackage('candidates', (payload) => { renderCandidatePanel(payload); renderCrossMatch(); }).catch(() => {});
      loadPackage('announcements', (payload) => { renderAnnouncements(payload); renderCrossMatch(); }).catch(() => {});
    });
    observeLazyBlocks();
    refreshCommands();
  } catch (error) {
    showToast(`首屏資料載入失敗：${error.message}`);
  }
}

$('#cmdk-button')?.addEventListener('click', openCommandDialog);
$('#source-status-btn')?.addEventListener('click', toggleHealth);
$('[data-close-health]')?.addEventListener('click', () => { $('#health-popover').hidden = true; $('#source-status-modal').hidden = true; });
$('#command-input')?.addEventListener('input', (event) => { state.selectedCommand = 0; renderCommandList(event.target.value); });
$('#command-input')?.addEventListener('keydown', (event) => {
  const query = event.target.value.toLowerCase();
  const filtered = state.commands.filter((command) => command.title.toLowerCase().includes(query) || command.hint.toLowerCase().includes(query));
  if (event.key === 'ArrowDown') { event.preventDefault(); state.selectedCommand = Math.min(state.selectedCommand + 1, filtered.length - 1); renderCommandList(query); }
  if (event.key === 'ArrowUp') { event.preventDefault(); state.selectedCommand = Math.max(state.selectedCommand - 1, 0); renderCommandList(query); }
  if (event.key === 'Enter') { event.preventDefault(); filtered[state.selectedCommand]?.run(); closeCommandDialog(); }
});
$('#command-dialog')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) closeCommandDialog(); });
document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openCommandDialog(); }
  if (event.key === 'Escape') { $('#health-popover').hidden = true; }
});

document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => { document.querySelectorAll('.tab').forEach((item) => item.classList.remove('is-active')); tab.classList.add('is-active'); }));
window.addEventListener('beforeunload', () => saveStore({}));
boot();
