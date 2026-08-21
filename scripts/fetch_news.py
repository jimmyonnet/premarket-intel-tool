import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

def get_time_window():
    # Taipei timezone
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    
    # End time is now
    end_time = now
    
    # Start time is previous trading day 13:30
    # Simplified trading day logic
    def is_trading_day(d):
        if d.weekday() >= 5: return False
        holidays_2026 = [
            "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
            "2026-02-27", "2026-04-03", "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25",
            "2026-10-09"
        ]
        if d.strftime("%Y-%m-%d") in holidays_2026: return False
        return True

    start_time = now
    for _ in range(10):
        start_time -= timedelta(days=1)
        if is_trading_day(start_time):
            start_time = start_time.replace(hour=13, minute=30, second=0, microsecond=0)
            break
            
    # If today is a trading day and it's already after 13:30, 
    # then start_time should actually be today's 13:30.
    # But this script runs at 07:35 ~ 08:20, so today is definitely before 13:30.
    
    return start_time, end_time

def parse_pubdate(date_str):
    # e.g. "Thu, 20 Aug 2026 15:30:00 GMT"
    try:
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
    except:
        pass
    return None

def score_news(title):
    score = 0
    title_upper = title.upper()
    
    # 總經與美股 (+3)
    for kw in ["FED", "聯準會", "降息", "CPI", "非農", "美股", "輝達", "NVIDIA", "道瓊", "那斯達克", "納斯達克"]:
        if kw in title_upper: score += 3
        
    # 台股核心 (+3)
    for kw in ["台積電", "TSMC", "聯發科", "鴻海", "廣達", "外資", "大盤", "台股", "CoWoS", "CPO", "矽光子", "水冷", "散熱", "機器人", "FOPLP", "面板級封裝"]:
        if kw in title_upper: score += 3
        
    # 強烈情緒字眼 (+2)
    for kw in ["大漲", "創新高", "重挫", "崩盤", "跳水", "漲停", "跌停", "狂飆", "血洗"]:
        if kw in title_upper: score += 2
        
    # 重大事件 (+2)
    for kw in ["法說會", "財報", "營收", "處置", "爆量", "解禁", "分盤"]:
        if kw in title_upper: score += 2
        
    return score

def main():
    start_time, end_time = get_time_window()
    print(f"Time Window: {start_time} to {end_time}")
    
    # Google News RSS for Taiwan Finance
    # Using a broad search query to capture most market-moving events
    query = "台股 OR 美股 OR 台積電 OR 輝達 OR 降息 OR 財報"
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
    except Exception as e:
        print(f"Error fetching RSS: {e}")
        xml_data = b""

    articles = []
    if xml_data:
        root = ET.fromstring(xml_data)
        for item in root.findall(".//item"):
            title = item.findtext("title")
            link = item.findtext("link")
            pub_date_str = item.findtext("pubDate")
            source = item.findtext("source")
            
            pub_date = parse_pubdate(pub_date_str)
            if pub_date and start_time <= pub_date <= end_time:
                # Clean up title (Google News sometimes appends source to title like " - 鉅亨網")
                clean_title = title
                if source and clean_title.endswith(f" - {source}"):
                    clean_title = clean_title[:-(len(source)+3)]
                
                score = score_news(clean_title)
                articles.append({
                    "title": clean_title,
                    "link": link,
                    "source": source,
                    "time": pub_date.strftime("%m/%d %H:%M"),
                    "score": score,
                    "timestamp": pub_date.timestamp()
                })
                
    # Sort by score (desc) then by time (desc)
    articles.sort(key=lambda x: (x["score"], x["timestamp"]), reverse=True)
    
    top_5 = articles[:5]
    print(f"Found {len(articles)} articles in window. Top 5:")
    for a in top_5:
        print(f"[{a['score']}] {a['title']}")
        
    out_dir = 'data/latest'
    os.makedirs(out_dir, exist_ok=True)
    with open(f'{out_dir}/news.json', 'w', encoding='utf-8') as f:
        json.dump(top_5, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
