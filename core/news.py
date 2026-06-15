import feedparser
import requests
from datetime import datetime
from config import NEWS_API_KEY


def get_news_rss(query: str, max_items: int = 10) -> list[dict]:
    """Google News RSSから関連ニュースを取得する（APIキー不要）"""
    url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        feed = feedparser.parse(url)
        results = []
        for entry in feed.entries[:max_items]:
            published = entry.get("published", "")
            results.append({
                "title":   entry.get("title", ""),
                "link":    entry.get("link", ""),
                "source":  entry.get("source", {}).get("title", ""),
                "published": published,
            })
        return results
    except Exception:
        return []


def get_news_api(query: str, max_items: int = 10) -> list[dict]:
    """NewsAPIからニュースを取得する（APIキーが必要）"""
    if not NEWS_API_KEY:
        return get_news_rss(query, max_items)

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "ja",
        "sortBy": "publishedAt",
        "pageSize": max_items,
        "apiKey": NEWS_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        results = []
        for article in data.get("articles", []):
            results.append({
                "title":     article.get("title", ""),
                "link":      article.get("url", ""),
                "source":    article.get("source", {}).get("name", ""),
                "published": article.get("publishedAt", ""),
            })
        return results
    except Exception:
        return get_news_rss(query, max_items)


def get_stock_news(ticker: str, company_name: str) -> list[dict]:
    """銘柄に関連するニュースを取得する"""
    query = company_name if company_name else ticker
    return get_news_api(query, max_items=8)
