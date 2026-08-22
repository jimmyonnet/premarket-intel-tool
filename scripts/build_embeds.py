import os
import requests

def build_embeds():
    urls = {
        'att': 'https://chengwaye.com/realtime-att',
        'fin': 'https://chengwaye.com/realtime-fin',
        'rev': 'https://chengwaye.com/realtime-rev'
    }
    
    hide_css = """
    <style>
      body { background: #FFFFFF !important; color: #0F172A !important; padding: 0 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }
      nav, .header, .ai-warn, .ai-warn-bottom, .search-container, #load-archive-btn, footer { display: none !important; }
      .container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
      #app { margin-top: 0 !important; min-height: 0 !important; }
      table { background: #FFFFFF !important; border-radius: 8px !important; border: 1px solid #E2E8F0 !important; overflow: hidden !important; }
      th { font-size: 11px !important; background: #F8FAFC !important; color: #64748B !important; border-bottom: 1px solid #E2E8F0 !important; font-weight: 600 !important; text-transform: uppercase !important; }
      td { font-size: 13px !important; color: #0F172A !important; border-bottom: 1px solid #F1F5F9 !important; }
      .time-col { color: #64748B !important; }
      .code-col { color: #2563EB !important; font-weight: 600 !important; }
      .name-col { color: #0F172A !important; font-weight: 600 !important; }
      .hist-col { color: #94A3B8 !important; }
      .hist-first { border-left: 2px solid #E2E8F0 !important; }
      .section-divider { background: #F8FAFC !important; color: #475569 !important; font-size: 12px !important; padding: 8px 10px !important; border-bottom: 1px solid #E2E8F0 !important; font-weight: 700 !important; text-transform: uppercase !important; }
      .clickable-row:hover td { background: #F8FAFC !important; }
      .detail-row td { background: #F8FAFC !important; border-bottom: 1px solid #E2E8F0 !important; }
      .detail-content { background: #F8FAFC !important; padding: 14px !important; }
      .detail-context-title { color: #0F172A !important; }
      .detail-context-title .ctx-code { color: #2563EB !important; }
      .detail-context-title .ctx-name { color: #0F172A !important; }
      .detail-context-title .ctx-meta { color: #64748B !important; }
      .raw-text { background: #FFFFFF !important; color: #334155 !important; border: 1px solid #CBD5E1 !important; border-radius: 6px !important; }
      .btn-link { border: 1px solid #CBD5E1 !important; color: #475569 !important; background: #FFFFFF !important; }
      .btn-link:hover { background: #F1F5F9 !important; color: #0F172A !important; border-color: #94A3B8 !important; }
      ::-webkit-scrollbar { width: 6px; height: 6px; }
      ::-webkit-scrollbar-track { background: #F1F5F9; }
      ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
    </style>
    """
    
    out_dir = 'docs/embed'
    os.makedirs(out_dir, exist_ok=True)
    
    for name, url in urls.items():
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                html = r.text
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
