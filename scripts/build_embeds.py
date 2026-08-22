import os
import re
import requests

def build_embeds():
    urls = {
        'att': 'https://chengwaye.com/realtime-att',
        'fin': 'https://chengwaye.com/realtime-fin',
        'rev': 'https://chengwaye.com/realtime-rev'
    }

    head_theme_init = """
    <script>
      (function() {
        var t = 'dark';
        try {
          t = window.parent.document.documentElement.getAttribute('data-theme') || localStorage.getItem('premarket.theme');
        } catch(e){}
        if (t !== 'light') t = 'dark';
        document.documentElement.setAttribute('data-theme', t);
        document.documentElement.className = t;
      })();
    </script>
    """

    hide_css = """
    <style>
      :root, :root[data-theme="dark"], html.dark, body.dark, html[data-theme="dark"], body[data-theme="dark"] {
        --bg-page: transparent !important;
        --bg-card: #111827 !important;
        --bg-sub: #1A2234 !important;
        --bg-hover: #242E44 !important;
        --text-main: #F8FAFC !important;
        --text-muted: #94A3B8 !important;
        --border: rgba(255, 255, 255, 0.08) !important;
        --border-light: rgba(255, 255, 255, 0.04) !important;
        --blue: #60A5FA !important;
        --btn-bg: #1A2234 !important;
        --btn-border: rgba(255, 255, 255, 0.1) !important;
        --btn-hover: #242E44 !important;
      }
      :root[data-theme="light"], html.light, body.light, html[data-theme="light"], body[data-theme="light"] {
        --bg-page: transparent !important;
        --bg-card: #FFFFFF !important;
        --bg-sub: #F8FAFC !important;
        --bg-hover: #F1F5F9 !important;
        --text-main: #0F172A !important;
        --text-muted: #64748B !important;
        --border: #E2E8F0 !important;
        --border-light: #F1F5F9 !important;
        --blue: #2563EB !important;
        --btn-bg: #FFFFFF !important;
        --btn-border: #E2E8F0 !important;
        --btn-hover: #F1F5F9 !important;
      }
      html, body { background: transparent !important; color: var(--text-main) !important; padding: 0 !important; margin: 0 !important; min-height: 0 !important; height: auto !important; overflow-y: hidden !important; font-family: -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Text", "Segoe UI", Roboto, "PingFang TC", "Noto Sans TC", sans-serif !important; }
      nav, .header, .ai-warn, .ai-warn-bottom, .search-container, #load-archive-btn, footer { display: none !important; margin: 0 !important; padding: 0 !important; height: 0 !important; }
      .container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; min-height: 0 !important; height: auto !important; background: transparent !important; }
      #app { margin-top: 0 !important; min-height: 0 !important; height: auto !important; background: transparent !important; }
      table { background: var(--bg-card) !important; border-radius: 8px !important; border: 1px solid var(--border) !important; overflow: hidden !important; width: 100% !important; border-collapse: separate !important; border-spacing: 0 !important; margin-bottom: 0 !important; }
      th { font-size: 11px !important; background: var(--bg-sub) !important; color: var(--text-muted) !important; border-bottom: 1px solid var(--border) !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.04em !important; padding: 8px 10px !important; }
      td { font-size: 13px !important; color: var(--text-main) !important; border-bottom: 1px solid var(--border-light) !important; background: var(--bg-card) !important; padding: 8px 10px !important; }
      .time-col { color: var(--text-muted) !important; font-size: 12px !important; }
      .code-col { color: var(--blue) !important; font-weight: 600 !important; }
      .name-col { color: var(--text-main) !important; font-weight: 600 !important; }
      .hist-col { color: var(--text-muted) !important; }
      .hist-first { border-left: 2px solid var(--border) !important; }
      .section-divider { background: var(--bg-sub) !important; color: var(--text-muted) !important; font-size: 12px !important; padding: 8px 12px !important; border-bottom: 1px solid var(--border) !important; font-weight: 700 !important; text-transform: uppercase !important; }
      .clickable-row:hover td { background: var(--bg-hover) !important; }
      .detail-row td { background: var(--bg-sub) !important; border-bottom: 1px solid var(--border) !important; }
      .detail-content { background: var(--bg-sub) !important; padding: 14px 16px !important; }
      .detail-context-title { color: var(--text-main) !important; font-size: 13px !important; }
      .detail-context-title .ctx-code { color: var(--blue) !important; }
      .detail-context-title .ctx-name { color: var(--text-main) !important; }
      .detail-context-title .ctx-meta { color: var(--text-muted) !important; font-size: 11px !important; }
      .raw-text { background: var(--bg-card) !important; color: var(--text-main) !important; border: 1px solid var(--border) !important; border-radius: 6px !important; padding: 12px !important; font-size: 12px !important; }
      .btn-link { border: 1px solid var(--btn-border) !important; color: var(--text-muted) !important; background: var(--btn-bg) !important; border-radius: 6px !important; padding: 4px 10px !important; font-size: 11px !important; font-weight: 600 !important; text-decoration: none !important; transition: all 0.15s ease !important; }
      .btn-link:hover { background: var(--btn-hover) !important; color: var(--text-main) !important; }
      .filter-bar { background: var(--bg-sub) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; color: var(--text-muted) !important; padding: 8px 12px !important; font-size: 12px !important; margin: 0 0 10px 0 !important; }
      .filter-bar span, .filter-bar label { color: var(--text-muted) !important; }
      .filter-bar .filter-label { color: var(--text-main) !important; font-size: 12px !important; margin-right: 14px !important; }
      .filter-bar button { background: var(--btn-bg) !important; border: 1px solid var(--btn-border) !important; color: var(--text-main) !important; border-radius: 6px !important; padding: 4px 10px !important; font-size: 11px !important; }
      .filter-bar button:hover { background: var(--btn-hover) !important; color: var(--text-main) !important; }
      .filter-bar input[type="text"], .filter-bar input[type="number"] { background: var(--btn-bg) !important; border: 1px solid var(--btn-border) !important; color: var(--text-main) !important; border-radius: 6px !important; padding: 4px 8px !important; }
      .filter-bar input[type="checkbox"] { accent-color: var(--blue) !important; margin-right: 6px !important; }
      .empty { padding: 24px 16px !important; color: var(--text-muted) !important; font-size: 12px !important; text-align: center !important; }
      ::-webkit-scrollbar { width: 6px; height: 6px; }
      ::-webkit-scrollbar-track { background: var(--bg-sub); }
      ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    </style>
    <script>
      (function(){
        function applyTheme(theme) {
          if (!theme) {
            try {
              var p = new URLSearchParams(location.search);
              theme = p.get('theme');
            } catch(e){}
            if (!theme) {
              try {
                theme = window.parent.document.documentElement.getAttribute('data-theme');
              } catch(e){}
            }
            if (!theme) {
              try {
                theme = localStorage.getItem('premarket.theme');
              } catch(e){}
            }
          }
          var isDark = (theme !== 'light');
          var mode = isDark ? 'dark' : 'light';
          document.documentElement.setAttribute('data-theme', mode);
          document.documentElement.className = mode;
          if (document.body) {
            document.body.className = mode;
            document.body.setAttribute('data-theme', mode);
          }
        }
        window.addEventListener('message', function(e) {
          if (e.data && e.data.type === 'theme-change') {
            applyTheme(e.data.theme);
          }
          if (e.data && e.data.type === 'request-height') {
            send();
          }
        });
        function send(){
          try {
            var app = document.getElementById('app');
            var tbl = app ? app.querySelector('table') : null;
            var filter = app ? app.querySelector('.filter-bar') : null;
            var totalH = 0;
            if (tbl) {
              totalH = (filter ? filter.offsetHeight + 10 : 0) + tbl.offsetHeight + 24;
            } else if (app) {
              totalH = app.scrollHeight + 16;
            } else {
              totalH = document.body.scrollHeight + 16;
            }
            var finalH = Math.max(120, Math.ceil(totalH));
            parent.postMessage({type:'embed-height', id: location.pathname.split('/').pop().replace('.html',''), height: finalH}, '*');
          } catch(e){}
        }

        // MutationObserver to catch when tables render, filters change, or details expand
        var mo = new MutationObserver(function() {
          send();
        });
        document.addEventListener('DOMContentLoaded', function() {
          applyTheme();
          send();
          if (document.body) mo.observe(document.body, { childList: true, subtree: true, attributes: true });
        });
        window.addEventListener('load', function() {
          applyTheme();
          send();
        });
        setTimeout(function() {
          var app = document.getElementById('app');
          if (app && app.innerHTML.indexOf('載入中') >= 0) {
            app.innerHTML = '<div class="empty">⚠️ 資料連線逾時（已沿用 build-time 快照）</div>';
            send();
          }
        }, 3500);
        setTimeout(function() { applyTheme(); send(); }, 100);
        setTimeout(function() { applyTheme(); send(); }, 300);
        setTimeout(function() { applyTheme(); send(); }, 800);
        setTimeout(function() { applyTheme(); send(); }, 1500);
      })();
    </script>
    """

    out_dir = 'docs/embed'
    os.makedirs(out_dir, exist_ok=True)

    for name, url in urls.items():
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                html = r.text
                # Remove ads, GA, trackers, and missing relative scripts/styles
                html = re.sub(r'<script[^>]+(?:adsbygoogle|googletagmanager|googlesyndication|visual-effects|cw-nav)[^>]*>.*?</script>', '', html, flags=re.DOTALL|re.IGNORECASE)
                html = re.sub(r'<link[^>]+(?:visual-effects|manifest)[^>]*>', '', html, flags=re.DOTALL|re.IGNORECASE)
                html = re.sub(r'<ins[^>]+adsbygoogle[^>]*>.*?</ins>', '', html, flags=re.DOTALL|re.IGNORECASE)
                html = re.sub(r'<iframe[^>]+doubleclick[^>]*>.*?</iframe>', '', html, flags=re.DOTALL|re.IGNORECASE)

                # Inject head script and CSS
                html = html.replace('<head>', '<head>' + head_theme_init)
                html = html.replace('</head>', hide_css + '</head>')

                # Disable historical rendering to only show unreflected
                if name in ['att', 'fin']:
                    html = html.replace("renderSection(historical,", "// renderSection(historical,")
                else:
                    html = html.replace("if (reflected.length) result += buildSection(reflected", "if (false) result += buildSection(reflected")

                with open(f'{out_dir}/{name}.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"Built {name}.html")
            else:
                print(f"Failed to fetch {url}: {r.status_code}")
        except Exception as e:
            print(f"Error fetching {url}: {e}")

if __name__ == '__main__':
    build_embeds()
