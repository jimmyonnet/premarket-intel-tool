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
      body { background: transparent !important; padding: 0 !important; }
      nav, .header, .ai-warn, .ai-warn-bottom, .search-container, #load-archive-btn, footer { display: none !important; }
      .container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
      #app { margin-top: 0 !important; min-height: 0 !important; }
      table { border-radius: 6px !important; }
      th { font-size: 13px !important; background: #1a1a1a !important; border-bottom: 1px solid #333333 !important; }
      td { font-size: 13px !important; border-bottom: 1px solid #333333 !important; }
      .section-divider { background: transparent !important; font-size: 13px !important; padding: 0 4px 8px !important; border-bottom: none !important; }
      .clickable-row:hover td { background: #1a1a1a !important; }
      .detail-row td { background: #0a0a0a !important; border-bottom: 1px solid #1a2132 !important; }
      .detail-content { background: #0a0a0a !important; padding: 12px !important; }
      .raw-text { background: #141414 !important; border: 1px solid #253046 !important; }
      ::-webkit-scrollbar { width: 6px; height: 6px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
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
