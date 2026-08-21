import os
import json
import requests
from datetime import datetime, timedelta, timezone

def is_trading_day(date_obj):
    if date_obj.weekday() >= 5: # 5=Sat, 6=Sun
        return False
    # Simplistic holidays
    holidays_2026 = [
        "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
        "2026-02-27", "2026-04-03", "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25",
        "2026-10-09"
    ]
    if date_obj.strftime("%Y-%m-%d") in holidays_2026:
        return False
    return True

def get_cutoff():
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    
    # If today is trading day and after 13:30
    if is_trading_day(now) and (now.hour > 13 or (now.hour == 13 and now.minute >= 30)):
        return now.replace(hour=13, minute=30, second=0, microsecond=0)
    
    # Otherwise, find the previous trading day
    d = now
    for _ in range(15):
        d -= timedelta(days=1)
        if is_trading_day(d):
            return d.replace(hour=13, minute=30, second=0, microsecond=0)
    return now.replace(hour=13, minute=30, second=0, microsecond=0)

def is_unreflected(item, cutoff):
    date_str = item.get('date', '') 
    time_str = item.get('time', '') 
    if not date_str or not time_str:
        return False
    try:
        parts = date_str.split('/')
        if len(parts) != 3: return False
        y = int(parts[0]) + 1911
        m = int(parts[1])
        d = int(parts[2])
        
        t_parts = time_str.split(':')
        hh = int(t_parts[0])
        mm = int(t_parts[1])
        ss = int(t_parts[2]) if len(t_parts) > 2 else 0
        
        tz = timezone(timedelta(hours=8))
        item_dt = datetime(y, m, d, hh, mm, ss, tzinfo=tz)
        return item_dt > cutoff
    except:
        return False

def main():
    cutoff = get_cutoff()
    print(f"Cutoff: {cutoff}")
    
    results = {
        'cutoff_str': cutoff.strftime('%m/%d %H:%M'),
        'att': [],
        'fin': [],
        'rev': []
    }
    
    urls = {
        'att': 'https://chengwaye-data.pages.dev/realtime_att.json',
        'fin': 'https://chengwaye-data.pages.dev/realtime_fin.json',
        'rev': 'https://chengwaye-data.pages.dev/realtime_revenue.json'
    }
    
    for key, url in urls.items():
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                entries = data.get('entries', [])
                unreflected = [e for e in entries if is_unreflected(e, cutoff)]
                results[key] = unreflected
                print(f"{key}: {len(entries)} total, {len(unreflected)} unreflected")
            else:
                print(f"Failed to fetch {key}: {r.status_code}")
        except Exception as e:
            print(f"Error fetching {key}: {e}")
            
    out_dir = 'data/latest'
    os.makedirs(out_dir, exist_ok=True)
    with open(f'{out_dir}/financials.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
