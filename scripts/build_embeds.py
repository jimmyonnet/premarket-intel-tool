import os
import re
import requests

def build_embeds():
    urls = {
        'att': 'https://chengwaye.com/realtime-att',
        'fin': 'https://chengwaye.com/realtime-fin',
        'rev': 'https://chengwaye.com/realtime-rev'
    }

    hide_css = """
    <style>
      :root {
        --bg-page: #FFFFFF;
        --bg-card: #FFFFFF;
        --bg-sub: #F8FAFC;
        --text-main: #0F172A;
        --text-muted: #64748B;
        --border: #E2E8F0;
        --border-light: #F1F5F9;
        --blue: #2563EB;
      }
      :root[data-theme="dark"], body.dark, html[data-theme="dark"] {
        --bg-page: #111827;
        --bg-card: #1E293B;
        --bg-sub: #0F172A;
        --text-main: #F8FAFC;
        --text-muted: #94A3B8;
        --border: #334155;
        --border-light: #1E293B;
        --blue: #60A5FA;
      }
      body { background: var(--bg-page) !important; color: var(--text-main) !important; padding: 0 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }
      nav, .header, .ai-warn, .ai-warn-bottom, .search-container, #load-archive-btn, footer { display: none !important; }
      .container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; background: transparent !important; }
      #app { margin-top: 0 !important; min-height: 0 !important; background: transparent !important; }
      table { background: var(--bg-card) !important; border-radius: 8px !important; border: 1px solid var(--border) !important; overflow: hidden !important; width: 100% !important; }
      th { font-size: 11px !important; background: var(--bg-sub) !important; color: var(--text-muted) !important; border-bottom: 1px solid var(--border) !important; font-weight: 600 !important; text-transform: uppercase !important; }
      td { font-size: 13px !important; color: var(--text-main) !important; border-bottom: 1px solid var(--border-light) !important; background: var(--bg-card) !important; }
      .time-col { color: var(--text-muted) !important; }
      .code-col { color: var(--blue) !important; font-weight: 600 !important; }
      .name-col { color: var(--text-main) !important; font-weight: 600 !important; }
      .hist-col { color: var(--text-muted) !important; }
      .hist-first { border-left: 2px solid var(--border) !important; }
      .section-divider { background: var(--bg-sub) !important; color: var(--text-muted) !important; font-size: 12px !important; padding: 8px 10px !important; border-bottom: 1px solid var(--border) !important; font-weight: 700 !important; text-transform: uppercase !important; }
      .clickable-row:hover td { background: var(--bg-sub) !important; }
      .detail-row td { background: var(--bg-sub) !important; border-bottom: 1px solid var(--border) !important; }
      .detail-content { background: var(--bg-sub) !important; padding: 14px !important; }
      .detail-context-title { color: var(--text-main) !important; }
      .detail-context-title .ctx-code { color: var(--blue) !important; }
      .detail-context-title .ctx-name { color: var(--text-main) !important; }
      .detail-context-title .ctx-meta { color: var(--text-muted) !important; }
      .raw-text { background: var(--bg-card) !important; color: var(--text-main) !important; border: 1px solid var(--border) !important; border-radius: 6px !important; }
      .btn-link { border: 1px solid var(--border) !important; color: var(--text-muted) !important; background: var(--bg-card) !important; }
      .btn-link:hover { background: var(--bg-sub) !important; color: var(--text-main) !important; border-color: var(--text-muted) !important; }
      .filter-bar { background: var(--bg-sub) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; color: var(--text-muted) !important; }
      .filter-bar span { color: var(--text-muted) !important; }
      .filter-bar .filter-label { color: var(--text-main) !important; }
      .filter-bar button { background: var(--bg-card) !important; border: 1px solid var(--border) !important; color: var(--text-main) !important; }
      .filter-bar button:hover { background: var(--bg-sub) !important; color: var(--text-main) !important; }
      .filter-bar input[type="text"], .filter-bar input[type="number"] { background: var(--bg-card) !important; border: 1px solid var(--border) !important; color: var(--text-main) !important; }
      .filter-bar input[type="checkbox"] { accent-color: var(--blue) !important; }
      .empty { padding: 24px 16px !important; color: var(--text-muted) !important; font-size: 12px !important; }
      ::-webkit-scrollbar { width: 6px; height: 6px; }
      ::-webkit-scrollbar-track { background: var(--bg-sub); }
      ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    </style>
    <script>
      (function(){
        function applyTheme(theme) {
          if (!theme) {
            try {
              theme = window.parent.document.documentElement.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            } catch(e) {
              theme = 'light';
            }
          }
          document.documentElement.setAttribute('data-theme', theme);
          if (theme === 'dark') {
            document.body.classList.add('dark');
          } else {
            document.body.classList.remove('dark');
          }
        }
        window.addEventListener('message', function(e) {
          if (e.data && e.data.type === 'theme-change') {
            applyTheme(e.data.theme);
          }
        });
        function send(){
          try {
            var h = document.body.scrollHeight;
            parent.postMessage({type:'embed-height', id: location.pathname.split('/').pop().replace('.html',''), height:h}, '*');
          } catch(e){}
        }
        new ResizeObserver(send).observe(document.body);
        document.addEventListener('DOMContentLoaded', function() {
          applyTheme();
          send();
        });
        window.addEventListener('load', function() {
          applyTheme();
          send();
        });
        // 3.5s timeout safety to avoid hanging on '載入中...'
        setTimeout(function() {
          var app = document.getElementById('app');
          if (app && app.innerHTML.indexOf('載入中') >= 0) {
            app.innerHTML = '<div class="empty">⚠️ 資料連線逾時（已沿用 build-time 快照）</div>';
            send();
          }
        }, 3500);
        setTimeout(function() { applyTheme(); send(); }, 300);
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
                # Remove ads, GA, trackers
                html = re.sub(r'<script[^>]+(?:adsbygoogle|googletagmanager|googlesyndication)[^>]*>.*?</script>', '', html, flags=re.DOTALL|re.IGNORECASE)
                html = re.sub(r'<ins[^>]+adsbygoogle[^>]*>.*?</ins>', '', html, flags=re.DOTALL|re.IGNORECASE)
                html = re.sub(r'<iframe[^>]+doubleclick[^>]*>.*?</iframe>', '', html, flags=re.DOTALL|re.IGNORECASE)

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
