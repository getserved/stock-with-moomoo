import argparse
import email.utils
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "ai-stock-screener" / "src" / "data" / "apiSnapshot.json"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_RSS_URL = "https://news.google.com/rss/search"
USER_AGENT = "stock-with-moomoo local theme news research"

EVENT_TERMS = {
    "negative_shock": [
        "explosion",
        "failure",
        "anomaly",
        "setback",
        "delay",
        "damaged",
        "crash",
        "probe",
        "investigation",
        "lawsuit",
        "warning",
        "downgrade",
        "guidance cut",
        "misses",
        "loss widens",
        "bankruptcy",
        "offering",
        "dilution",
        "fires",
        "layoffs",
        "recall",
        "regulatory",
        "export controls",
        "sanctions",
        "爆炸",
        "失败",
        "异常",
        "延期",
        "调查",
        "诉讼",
        "下调",
        "裁员",
        "增发",
        "融资",
    ],
    "positive_catalyst": [
        "contract",
        "award",
        "approval",
        "partnership",
        "launches",
        "breakthrough",
        "funding",
        "ipo",
        "beats",
        "raises guidance",
        "订单",
        "合同",
        "获批",
        "突破",
        "融资",
        "上调",
    ],
    "scheduled_event": [
        "earnings",
        "investor day",
        "conference",
        "keynote",
        "computex",
        "财报",
        "发布会",
        "大会",
    ],
}

COMMON_NAME_TOKENS = {
    "inc",
    "corp",
    "corporation",
    "company",
    "holdings",
    "group",
    "technology",
    "technologies",
    "systems",
    "class",
    "common",
    "stock",
    "ord",
    "ltd",
    "limited",
    "plc",
    "ai",
}

THEME_CONFIG = [
    {
        "theme": "AI/半导体链",
        "queries": [
            'Computex ("AI server" OR "AI PC" OR HBM OR "liquid cooling" OR "data center")',
            '"AI data center" ("power shortage" OR cooling OR server OR GPU)',
            '"semiconductor export controls" OR "AI chip export controls"',
        ],
        "keywords": ["ai", "人工智能", "半导体", "芯片", "数据中心", "光网络", "hbm", "gpu", "server", "computex", "liquid cooling", "ai pc"],
    },
    {
        "theme": "AI主题",
        "queries": [
            'Computex (AI OR "artificial intelligence" OR robotics OR "edge AI")',
            '"AI robotics" OR "physical AI" OR "edge AI"',
        ],
        "keywords": ["ai", "人工智能", "机器人", "aigc", "physical ai", "edge ai", "robotics"],
    },
    {
        "theme": "太空/卫星主题",
        "queries": [
            '"rocket launch failure" OR "rocket explosion" OR "launch anomaly"',
            '"satellite anomaly" OR "satellite failure" OR "spacecraft anomaly"',
            'NASA contract satellite launch rocket',
        ],
        "keywords": [
            "太空",
            "航天",
            "卫星",
            "火箭",
            "space",
            "aerospace",
            "satellite",
            "rocket",
            "launch",
            "rklb",
            "rocket lab",
            "lunr",
            "intuitive machines",
            "asts",
            "ast spacemobile",
            "pl",
            "planet labs",
            "spce",
            "virgin galactic",
            "satl",
            "bksy",
            "blacksky",
            "rdw",
            "redwire",
            "llap",
            "terran orbital",
        ],
    },
    {
        "theme": "量子主题",
        "queries": [
            '"quantum computing" breakthrough OR "quantum computing" funding',
            '"qubit" OR "quantum computer" OR "quantum processor"',
        ],
        "keywords": ["量子", "quantum", "qubit", "ionq", "rigetti", "d-wave"],
    },
]


def fetch_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def gdelt_articles(query, lookback_hours, max_records):
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "timespan": f"{lookback_hours}h",
        "maxrecords": str(max_records),
        "sort": "datedesc",
    }
    url = f"{GDELT_URL}?{urllib.parse.urlencode(params)}"
    try:
        payload = json.loads(fetch_text(url))
    except Exception:
        return []
    articles = payload.get("articles") or payload.get("items") or []
    result = []
    for article in articles:
        result.append(
            {
                "provider": "GDELT",
                "title": article.get("title") or article.get("name") or "",
                "url": article.get("url") or article.get("id") or "",
                "source": article.get("domain") or article.get("sourceCommonName") or "",
                "publishedAt": article.get("seendate") or article.get("date") or "",
            }
        )
    return result


def google_news_articles(query, lookback_hours, max_records):
    params = {
        "q": f"{query} when:{max(1, int(lookback_hours / 24))}d",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    url = f"{GOOGLE_RSS_URL}?{urllib.parse.urlencode(params)}"
    try:
        root = ET.fromstring(fetch_text(url))
    except Exception:
        return []
    result = []
    for item in root.findall("./channel/item")[:max_records]:
        published = item.findtext("pubDate") or ""
        try:
            parsed = email.utils.parsedate_to_datetime(published)
            published = parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        result.append(
            {
                "provider": "Google News RSS",
                "title": item.findtext("title") or "",
                "url": item.findtext("link") or "",
                "source": item.findtext("source") or "",
                "publishedAt": published,
            }
        )
    return result


def normalize_article(article):
    return {
        "provider": article.get("provider", ""),
        "title": " ".join(str(article.get("title", "")).split()),
        "url": article.get("url", ""),
        "source": article.get("source", ""),
        "publishedAt": article.get("publishedAt", ""),
    }


def dedupe_articles(articles):
    seen = set()
    result = []
    for article in articles:
        item = normalize_article(article)
        key = item["url"] or item["title"].lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def row_text(row):
    return " ".join(
        [
            str(row.get("ticker") or ""),
            str(row.get("name") or ""),
            str(row.get("theme") or ""),
            str(row.get("industry") or ""),
            " ".join(row.get("concepts") or []),
        ]
    ).lower()


def keyword_matches(text, keyword):
    keyword = keyword.lower().strip()
    if not keyword:
        return False
    if re.search(r"[\u4e00-\u9fff]", keyword) or " " in keyword or "-" in keyword:
        return keyword in text
    return keyword in set(re.findall(r"[a-z0-9]+", text))


def article_event_score(article):
    title = str(article.get("title") or "").lower()
    score = 0
    reasons = []
    for term in EVENT_TERMS["negative_shock"]:
        if term in title:
            score += 18
            reasons.append("负面/冲击新闻")
            break
    for term in EVENT_TERMS["positive_catalyst"]:
        if term in title:
            score += 10
            reasons.append("正面催化")
            break
    for term in EVENT_TERMS["scheduled_event"]:
        if term in title:
            score += 5
            reasons.append("时间窗口")
            break
    return score, sorted(set(reasons))


def row_match_terms(row):
    terms = []
    ticker = str(row.get("ticker") or "").lower().replace(".", " ")
    if len(ticker.replace(" ", "")) >= 4:
        terms.append(ticker)
    name = str(row.get("name") or "").lower()
    if name:
        terms.append(name)
        tokens = [token for token in re.findall(r"[a-z0-9]+", name) if len(token) >= 4 and token not in COMMON_NAME_TOKENS]
        terms.extend(tokens[:4])
    return sorted(set(terms), key=len, reverse=True)


def article_mentions_row(row, article):
    title = str(article.get("title") or "").lower()
    if not title:
        return False
    return any(keyword_matches(title, term) for term in row_match_terms(row))


def price_change_pct(row):
    price = row.get("price")
    previous = row.get("prePrice")
    if not price or not previous:
        return None
    try:
        return (float(price) / float(previous) - 1) * 100
    except Exception:
        return None


def recent_sec_score(row):
    events = ((row.get("fundamentalNews") or {}).get("events") or [])[:3]
    score = 0
    tags = []
    for event in events:
        category = event.get("category") or ""
        form = event.get("form") or "SEC"
        if "重大事件" in category:
            score += 20
        elif "融资" in category or "增发" in category:
            score += 16
        elif "财报" in category or "年报" in category:
            score += 10
        else:
            score += 6
        tags.append(f"{form} {category}".strip())
    return min(score, 35), tags[:3]


def event_days(row):
    primary = (row.get("nextEvent") or {}).get("primary") if row.get("nextEvent") else None
    if not primary:
        return None
    days = primary.get("daysUntil")
    return days if isinstance(days, (int, float)) else None


def row_event_score(row, matched_news):
    score = 0
    reasons = []
    news_score = sum(item["eventHeat"] for item in matched_news)
    if news_score:
        score += min(news_score, 60)
        reasons.append("新闻标题包含具体事件词")

    change_pct = price_change_pct(row)
    if change_pct is not None:
        if change_pct <= -12:
            score += 35
            reasons.append(f"当日/盘后大跌 {change_pct:.1f}%")
        elif change_pct <= -7:
            score += 26
            reasons.append(f"当日/盘后下跌 {change_pct:.1f}%")
        elif change_pct <= -3:
            score += 14
            reasons.append(f"当日/盘后回撤 {change_pct:.1f}%")
        elif change_pct >= 8:
            score += 8
            reasons.append(f"放量上涨/事件反应 {change_pct:.1f}%")

    sec_score, sec_tags = recent_sec_score(row)
    if sec_score:
        score += sec_score
        reasons.extend(sec_tags)

    days = event_days(row)
    if days is not None and 0 <= days <= 7:
        score += 12
        reasons.append("7天内有财报/重大会议")

    technical = row.get("technical") or {}
    volume_ratio = technical.get("volumeRatio")
    if volume_ratio and volume_ratio >= 2:
        score += 10
        reasons.append(f"成交量放大 {volume_ratio:.1f}x")

    market_cap = row.get("marketCap")
    if market_cap is not None and market_cap < 300_000_000:
        score -= 8
        reasons.append("市值低于3亿美元，降低可信度")

    return max(0, round(score, 3)), reasons[:6], change_pct


def attach_event_news(rows, theme_news):
    for row in rows:
        text = row_text(row)
        matched = []
        for theme in theme_news:
            if any(keyword_matches(text, keyword) for keyword in theme.get("keywords", [])):
                event_articles = []
                event_heat = 0
                event_reasons = []
                for article in theme["articles"]:
                    article_score, reasons = article_event_score(article)
                    if article_score:
                        direct_mention = article_mentions_row(row, article)
                        sector_shock = "负面/冲击新闻" in reasons
                        if not direct_mention and not sector_shock:
                            continue
                        event = dict(article)
                        event["eventScore"] = article_score if direct_mention else min(article_score, 18)
                        event["eventReasons"] = reasons
                        event["matchType"] = "direct" if direct_mention else "sector_shock"
                        event_articles.append(event)
                        event_heat += event["eventScore"]
                        event_reasons.extend(reasons)
                if not event_articles:
                    continue
                matched.append(
                    {
                        "theme": theme["theme"],
                        "heat": theme["heat"],
                        "eventHeat": event_heat,
                        "eventReasons": sorted(set(event_reasons)),
                        "articles": event_articles[:3],
                    }
                )
        score, reasons, change_pct = row_event_score(row, matched)
        if score > 0:
            row["themeNews"] = matched
            row["themeNewsScore"] = score
            row["eventDrivenScore"] = score
            row["eventDrivenReasons"] = reasons
            row["priceChangePct"] = round(change_pct, 3) if change_pct is not None else None
        else:
            row.pop("themeNews", None)
            row["themeNewsScore"] = 0
            row["eventDrivenScore"] = 0
            row["eventDrivenReasons"] = []
            row["priceChangePct"] = round(change_pct, 3) if change_pct is not None else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--max-records", type=int, default=25)
    parser.add_argument("--provider", choices=["gdelt", "google", "both"], default="both")
    args = parser.parse_args()

    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    theme_news = []
    for config in THEME_CONFIG:
        articles = []
        for query in config["queries"]:
            if args.provider in {"gdelt", "both"}:
                articles.extend(gdelt_articles(query, args.lookback_hours, args.max_records))
                time.sleep(0.25)
            if args.provider in {"google", "both"}:
                articles.extend(google_news_articles(query, args.lookback_hours, min(args.max_records, 20)))
                time.sleep(0.15)
        deduped = dedupe_articles(articles)
        theme_news.append(
            {
                "theme": config["theme"],
                "keywords": config["keywords"],
                "queries": config["queries"],
                "heat": len(deduped),
                "articles": deduped[:10],
            }
        )

    attach_event_news(payload.get("rows", []), theme_news)
    payload["themeNewsFeed"] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lookbackHours": args.lookback_hours,
        "provider": args.provider,
        "scoring": "产业/主题只负责匹配候选池；排序分只来自具体新闻事件词、SEC公告、价格冲击、临近事件和成交量异常。",
        "themes": theme_news,
    }
    with SNAPSHOT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Wrote {SNAPSHOT}")
    for item in theme_news:
        print(f"{item['theme']}: {item['heat']} articles")


if __name__ == "__main__":
    main()
