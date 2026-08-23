import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

MAX_NEWS = 10
MIN_TITLE_LENGTH = 12
MIN_TOTAL_SCORE = 8
TAIPEI = timezone(timedelta(hours=8))

# The RSS feed is an aggregator; this score reflects the publisher named in each item.
SOURCE_QUALITY = {
    "reuters": 5,
    "路透社": 5,
    "bloomberg": 5,
    "彭博": 5,
    "financial times": 5,
    "金融時報": 5,
    "wall street journal": 5,
    "華爾街日報": 5,
    "associated press": 5,
    "美聯社": 5,
    "cnbc": 4,
    "bbc": 4,
    "中央社": 4,
    "經濟日報": 4,
    "工商時報": 4,
    "鉅亨網": 4,
    "財訊": 4,
    "今周刊": 3,
    "yahoo財經": 3,
    "yahoo新聞": 3,
    "news.cnyes.com": 4,
    "cnyes": 4,
}

# Each group contributes once, preventing keyword-heavy clickbait from dominating.
IMPACT_GROUPS = {
    "macro_policy": (4, ["聯準會", "升息", "降息", "利率", "CPI", "PCE", "非農", "失業率", "央行", "關稅", "制裁"]),
    "market_benchmark": (3, ["台股", "大盤", "美股", "標普", "道瓊", "那斯達克", "納斯達克", "台指期", "期貨"]),
    "systemic_company": (3, ["台積電", "TSMC", "輝達", "NVIDIA", "聯發科", "鴻海", "蘋果", "微軟", "亞馬遜", "Alphabet"]),
    "earnings_financial": (3, ["財報", "營收", "獲利", "本益比", "法說會", "財測", "展望", "毛利率"]),
    "market_move": (3, ["大漲", "大跌", "重挫", "崩盤", "跳水", "漲停", "跌停", "創新高", "爆量", "反彈", "破底"]),
    "sector_supply_chain": (2, ["AI", "CoWoS", "CPO", "矽光子", "水冷", "散熱", "機器人", "半導體", "面板級封裝"]),
    "market_structure": (2, ["外資", "法人", "資金流", "ETF", "處置", "分盤", "解禁", "監管"]),
}

LOW_SIGNAL_TERMS = ["投資人必看", "懶人包", "這檔會", "老師", "飆股密碼", "買點", "賣點", "報明牌"]


def get_time_window(now=None):
    now = now or datetime.now(TAIPEI)

    def is_trading_day(day):
        if day.weekday() >= 5:
            return False
        holidays_2026 = {
            "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
            "2026-02-27", "2026-04-03", "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25",
            "2026-10-09",
        }
        return day.strftime("%Y-%m-%d") not in holidays_2026

    start_time = now
    for _ in range(10):
        start_time -= timedelta(days=1)
        if is_trading_day(start_time):
            return start_time.replace(hour=13, minute=30, second=0, microsecond=0), now
    return now - timedelta(days=1), now


def parse_pubdate(date_str):
    if not date_str:
        return None
    try:
        parsed = parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(TAIPEI)
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def clean_title(title, source):
    title = normalize_text(title)
    source = normalize_text(source)
    if source and title.endswith(f" - {source}"):
        title = title[: -(len(source) + 3)].rstrip()
    return title


def normalize_title(title):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())


def source_quality(source):
    normalized = normalize_text(source).lower()
    for name, score in SOURCE_QUALITY.items():
        if name.lower() in normalized:
            return score
    return 1


def impact_score(title):
    title_upper = title.upper()
    score = 0
    matched_groups = []
    for group, (weight, keywords) in IMPACT_GROUPS.items():
        if any(keyword.upper() in title_upper for keyword in keywords):
            score += weight
            matched_groups.append(group)
    return score, matched_groups


def score_breakdown(title, source=""):
    quality = source_quality(source)
    impact, groups = impact_score(title)
    penalty = sum(1 for term in LOW_SIGNAL_TERMS if term.upper() in title.upper())
    total = quality + impact - (penalty * 2)
    return {
        "score": total,
        "quality_score": quality,
        "impact_score": impact,
        "matched_groups": groups,
        "quality_pass": quality >= 2,
        "impact_pass": impact >= 3,
    }


def score_news(title, source=""):
    return score_breakdown(title, source)["score"]


def is_qualified(article):
    return (
        len(article["title"]) >= MIN_TITLE_LENGTH
        and bool(article.get("link"))
        and article["quality_score"] >= 2
        and article["impact_score"] >= 3
        and article["score"] >= MIN_TOTAL_SCORE
    )


def parse_feed(xml_data, start_time, end_time):
    if not xml_data:
        return []
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    articles = []
    for item in root.findall(".//item"):
        title = normalize_text(item.findtext("title"))
        link = normalize_text(item.findtext("link"))
        source = normalize_text(item.findtext("source"))
        pub_date = parse_pubdate(item.findtext("pubDate"))
        if not title or not pub_date or not (start_time <= pub_date <= end_time):
            continue
        title = clean_title(title, source)
        scores = score_breakdown(title, source)
        article = {
            "title": title,
            "link": link,
            "source": source,
            "time": pub_date.strftime("%m/%d %H:%M"),
            "timestamp": pub_date.timestamp(),
            **scores,
        }
        article["qualified"] = is_qualified(article)
        articles.append(article)
    return articles


def dedupe_articles(articles):
    unique = {}
    for article in articles:
        key = normalize_title(article["title"])
        if not key:
            continue
        previous = unique.get(key)
        if previous is None or (article["score"], article["timestamp"]) > (previous["score"], previous["timestamp"]):
            unique[key] = article
    return list(unique.values())


def fetch_feed(query):
    encoded_query = urllib.parse.quote_plus(f"{query} when:1d")
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read()
    except Exception as exc:
        print(f"Error fetching RSS query {query!r}: {exc}", file=sys.stderr)
        return b""


def select_top_news(articles, limit=MAX_NEWS):
    ranked = sorted(
        (article for article in dedupe_articles(articles) if article["qualified"]),
        key=lambda article: (article["score"], article["impact_score"], article["timestamp"]),
        reverse=True,
    )
    return ranked[:limit]


def main():
    start_time, end_time = get_time_window()
    print(f"Time Window: {start_time} to {end_time}", file=sys.stderr)

    queries = [
        "台股 財經",
        "美股 聯準會 財報",
        "台積電 NVIDIA 科技股",
    ]
    articles = []
    successful_feeds = 0
    for query in queries:
        feed = fetch_feed(query)
        if feed:
            successful_feeds += 1
            articles.extend(parse_feed(feed, start_time, end_time))

    selected = select_top_news(articles)
    print(
        f"Found {len(dedupe_articles(articles))} unique candidates; selected {len(selected)} qualified articles (max {MAX_NEWS}, no padding).",
        file=sys.stderr,
    )
    for article in selected:
        print(f"[{article['score']}] Q{article['quality_score']} I{article['impact_score']} {article['title']}", file=sys.stderr)

    out_dir = "data/latest"
    os.makedirs(out_dir, exist_ok=True)
    output_path = f"{out_dir}/news.json"
    if successful_feeds == 0:
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print("All RSS feeds failed; retaining the most recent valid news snapshot.", file=sys.stderr)
            return
        print("All RSS feeds failed and no previous news snapshot exists.", file=sys.stderr)
        raise SystemExit(1)

    with open(output_path, "w", encoding="utf-8") as output:
        json.dump(selected, output, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
