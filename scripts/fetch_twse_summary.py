import urllib.request
import json
import os
import sys

def main():
    # 1. Fetch ^TWII from Yahoo Finance
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    twii_url = "https://query2.finance.yahoo.com/v8/finance/chart/^TWII?interval=1d&range=1d"
    twii_data = {}
    try:
        req = urllib.request.Request(twii_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            meta = data['chart']['result'][0]['meta']
            twii_data = {
                "price": round(meta['regularMarketPrice'], 2),
                "change": round(meta['regularMarketPrice'] - meta['chartPreviousClose'], 2),
                "change_pct": round((meta['regularMarketPrice'] - meta['chartPreviousClose']) / meta['chartPreviousClose'] * 100, 2),
                "volume": meta['regularMarketVolume'] # Volume is usually heavily underreported on Yahoo for TWII. But we'll try.
            }
    except Exception as e:
        print(f"Error fetching TWII: {e}", file=sys.stderr)
        
    # 2. Fetch Institutional Buy/Sell from TWSE API
    # URL: https://www.twse.com.tw/fund/BFI82U?response=json&dayDate=&type=day
    twse_data = {}
    twse_url = "https://www.twse.com.tw/fund/BFI82U?response=json&dayDate=&type=day"
    try:
        req = urllib.request.Request(twse_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data['stat'] == 'OK':
                # fields: ['單位名稱', '買進金額', '賣出金額', '買賣超金額']
                # row example: ['外資及陸資(不含外資自營商)', '131,235,951,335', '124,198,345,618', '7,037,605,717']
                # We want 外資及陸資, 投信, 自營商
                for row in data['data']:
                    name = row[0]
                    net_buy = int(row[3].replace(',', ''))
                    if '外資及陸資' in name and '不含外資自營商' in name:
                        twse_data['foreign'] = round(net_buy / 100000000, 2) # in 億
                    elif '投信' in name:
                        twse_data['trust'] = round(net_buy / 100000000, 2)
                    elif '自營商' in name and '自行買賣' in name:
                        # sum up all 自營商? usually they are split into 自行買賣 and 避險
                        twse_data['dealer'] = twse_data.get('dealer', 0) + net_buy
                    elif '自營商' in name and '避險' in name:
                        twse_data['dealer'] = twse_data.get('dealer', 0) + net_buy
                if 'dealer' in twse_data:
                    twse_data['dealer'] = round(twse_data['dealer'] / 100000000, 2)
    except Exception as e:
        print(f"Error fetching TWSE: {e}", file=sys.stderr)

    result = {
        "twii": twii_data,
        "inst": twse_data
    }
    
    out_dir = 'data/latest'
    os.makedirs(out_dir, exist_ok=True)
    with open(f'{out_dir}/twse_summary.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
