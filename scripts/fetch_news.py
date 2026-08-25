import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime

MAX_NEWS = 10
MIN_TITLE_LENGTH = 12
# Keep the source and topic gates strict, but admit credible, single-topic market news.
MIN_TOTAL_SCORE = 7
TAIPEI = timezone(timedelta(hours=8))
POST_MARKET_TIME = time(13, 30)
HOLIDAYS_2026 = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-27", "2026-04-03", "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25",
    "2026-10-09",
}

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
    "yahoo股市": 3,
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

# These are editorial buckets, not extra quality gates. They keep the Top 10 from
# becoming ten rewrites of the same company or event when the feed is crowded.
NEWS_TOPIC_RULES = (
    ("geopolitics_trade", ("伊朗", "以色列", "俄烏", "戰爭", "地緣政治", "關稅", "制裁", "貿易戰", "出口管制")),
    ("currency_commodities", ("美元", "美金", "日圓", "人民幣", "匯率", "原油", "油價", "黃金", "銅價", "美債", "債券", "殖利率", "商品")),
    ("macro_policy", ("聯準會", "Fed", "升息", "降息", "利率", "CPI", "PCE", "非農", "失業率", "央行", "通膨")),
    ("global_market", ("美股", "標普", "標普500", "道瓊", "那斯達克", "納斯達克", "費半", "華爾街", "美國股市")),
    ("taiwan_market", ("台股", "加權指數", "台指期", "台灣股市", "櫃買", "集中市場")),
    ("asia_market", ("日經", "日本股市", "KOSPI", "韓國股市", "韓股", "中國股市", "陸股", "上證", "恆生", "港股", "亞股")),
    ("sector_technology", ("AI", "人工智慧", "半導體", "記憶體", "光通訊", "CPO", "矽光子", "機器人", "散熱", "面板")),
    ("company_earnings", ("台積電", "TSMC", "輝達", "NVIDIA", "聯發科", "鴻海", "蘋果", "微軟", "亞馬遜", "Alphabet", "財報", "營收", "法說會", "財測", "獲利")),
    ("market_structure", ("外資", "法人", "資金流", "ETF", "處置", "分盤", "解禁", "監管")),
)

NAMED_ENTITY_RULES = (
    ("nvidia", ("輝達", "NVIDIA")),
    ("tsmc", ("台積電", "TSMC")),
    ("apple", ("蘋果", "Apple")),
    ("microsoft", ("微軟", "Microsoft")),
    ("amazon", ("亞馬遜", "Amazon")),
    ("meta", ("Meta", "臉書")),
    ("broadcom", ("博通", "Broadcom")),
    ("taiwan_market", ("台股", "加權指數", "台指期")),
    ("us_market", ("美股", "標普", "道瓊", "那斯達克", "納斯達克", "費半")),
)

# The caps are soft: the first pass enforces them, then a fallback fills the list
# if the available qualified feed really lacks other topics. This avoids padding
# with low-quality articles while still preventing one crowded story from winning
# by score alone whenever alternatives exist.
MAX_PER_TOPIC = 3
MAX_PER_ENTITY = 3
MAX_PER_SOURCE = 4

QUERIES = [
    "台股 財經",
    "美股 財經",
    "聯準會 通膨 利率 債券",
    "中國 日本 韓國 歐洲 股市",
    "原油 黃金 美元 匯率 關稅 地緣政治",
    "半導體 AI 科技 財報",
]


def is_trading_day(day):
    return day.weekday() < 5 and day.strftime("%Y-%m-%d") not in HOLIDAYS_2026


def previous_trading_day(day):
    candidate = day - timedelta(days=1)
    for _ in range(10):
        if is_trading_day(candidate):
            return candidate
        candidate -= timedelta(days=1)
    return day - timedelta(days=1)


def get_time_window(now=None):
    now = now or datetime.now(TAIPEI)
    after_today_close = is_trading_day(now.date()) and now.timetz().replace(tzinfo=None) >= POST_MARKET_TIME
    start_date = now.date() if after_today_close else previous_trading_day(now.date())
    start_time = datetime.combine(start_date, POST_MARKET_TIME, tzinfo=TAIPEI)
    return start_time, now


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


def diversity_dimensions(title):
    title_upper = title.upper()
    topic_groups = [
        topic for topic, keywords in NEWS_TOPIC_RULES
        if any(keyword.upper() in title_upper for keyword in keywords)
    ]
    named_entities = [
        entity for entity, keywords in NAMED_ENTITY_RULES
        if any(keyword.upper() in title_upper for keyword in keywords)
    ]
    return {
        "topic_groups": topic_groups,
        "primary_topic": topic_groups[0] if topic_groups else "other",
        "named_entities": named_entities,
    }


def score_breakdown(title, source=""):
    quality = source_quality(source)
    impact, groups = impact_score(title)
    dimensions = diversity_dimensions(title)
    low_signal_hits = [term for term in LOW_SIGNAL_TERMS if term.upper() in title.upper()]
    penalty = len(low_signal_hits)
    total = quality + impact - (penalty * 2)
    return {
        "score": total,
        "quality_score": quality,
        "impact_score": impact,
        "matched_groups": groups,
        "low_signal_hits": low_signal_hits,
        **dimensions,
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
        and not article.get("low_signal_hits")
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


def _article_dimensions(article):
    dimensions = diversity_dimensions(article.get("title", ""))
    return {
        "primary_topic": article.get("primary_topic") or dimensions["primary_topic"],
        "named_entities": article.get("named_entities") or dimensions["named_entities"],
    }


def _source_key(article):
    return normalize_text(article.get("source")) or "unknown"


def _fits_diversity_caps(article, topic_counts, entity_counts, source_counts):
    dimensions = _article_dimensions(article)
    if topic_counts.get(dimensions["primary_topic"], 0) >= MAX_PER_TOPIC:
        return False
    if any(entity_counts.get(entity, 0) >= MAX_PER_ENTITY for entity in dimensions["named_entities"]):
        return False
    if source_counts.get(_source_key(article), 0) >= MAX_PER_SOURCE:
        return False
    return True


def _record_diversity(article, topic_counts, entity_counts, source_counts):
    dimensions = _article_dimensions(article)
    topic = dimensions["primary_topic"]
    topic_counts[topic] = topic_counts.get(topic, 0) + 1
    for entity in dimensions["named_entities"]:
        entity_counts[entity] = entity_counts.get(entity, 0) + 1
    source = _source_key(article)
    source_counts[source] = source_counts.get(source, 0) + 1


def _fits_entity_caps(article, entity_counts):
    return all(
        entity_counts.get(entity, 0) < MAX_PER_ENTITY
        for entity in _article_dimensions(article)["named_entities"]
    )


def select_top_news(articles, limit=MAX_NEWS):
    ranked = sorted(
        (article for article in dedupe_articles(articles) if article["qualified"]),
        key=lambda article: (article["score"], article["impact_score"], article["timestamp"]),
        reverse=True,
    )
    selected = []
    deferred = []
    topic_counts = {}
    entity_counts = {}
    source_counts = {}
    for article in ranked:
        if len(selected) >= limit:
            break
        if _fits_diversity_caps(article, topic_counts, entity_counts, source_counts):
            selected.append(article)
            _record_diversity(article, topic_counts, entity_counts, source_counts)
        else:
            deferred.append(article)

    # First relax topic/source caps while retaining entity caps. This prevents a
    # crowded company story from returning in the final slots when other
    # qualified entities are available but happen to share a feed/source cap.
    if len(selected) < limit:
        remaining = []
        for article in deferred:
            if len(selected) >= limit:
                break
            if _fits_entity_caps(article, entity_counts):
                selected.append(article)
                _record_diversity(article, topic_counts, entity_counts, source_counts)
            else:
                remaining.append(article)
        deferred = remaining

    # If the qualified pool is genuinely too narrow, fill the remaining slots
    # with the strongest deferred items rather than lowering the quality gate.
    if len(selected) < limit:
        selected.extend(deferred[: limit - len(selected)])
    return selected


def main():
    start_time, end_time = get_time_window()
    print(f"Time Window: {start_time} to {end_time}", file=sys.stderr)

    queries = QUERIES
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
