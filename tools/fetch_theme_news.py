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
        "keywords": ["太空", "航天", "卫星", "火箭", "space", "aerospace", "satellite", "rocket", "launch"],
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
    if len(keyword) <= 3:
        return keyword in set(re.findall(r"[a-z0-9]+", text))
    return keyword in text


def attach_theme_news(rows, theme_news):
    for row in rows:
        text = row_text(row)
        matched = []
        for theme in theme_news:
            if any(keyword_matches(text, keyword) for keyword in theme.get("keywords", [])):
                matched.append(
                    {
                        "theme": theme["theme"],
                        "heat": theme["heat"],
                        "articles": theme["articles"][:3],
                    }
                )
        if matched:
            row["themeNews"] = matched
            row["themeNewsScore"] = sum(item["heat"] for item in matched)
        else:
            row.pop("themeNews", None)
            row["themeNewsScore"] = 0


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

    attach_theme_news(payload.get("rows", []), theme_news)
    payload["themeNewsFeed"] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lookbackHours": args.lookback_hours,
        "provider": args.provider,
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
