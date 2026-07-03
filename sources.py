import feedparser
import httpx
import logging
from datetime import datetime
from config import RSS_SOURCES, REQUEST_TIMEOUT, MAX_RETRIES

logger = logging.getLogger(__name__)


def fetch_feed(source_name, url):
    """Fetch and parse an RSS feed, returning a list of article dicts."""
    articles = []
    try:
        logger.info(f"Fetching {source_name}: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsBot/1.0"
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        feed = feedparser.parse(response.text)
        if feed.bozo and not feed.entries:
            logger.warning(f"Feed parse error for {source_name}: {feed.bozo_exception}")
            return []

        for entry in feed.entries[:100]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).isoformat()
                except (TypeError, ValueError):
                    pass
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    published = datetime(*entry.updated_parsed[:6]).isoformat()
                except (TypeError, ValueError):
                    pass

            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description

            link = entry.get("link", "")
            title = entry.get("title", "").strip()

            # Google News RSS has a source field with the real source URL
            real_url = link
            if hasattr(entry, "source") and hasattr(entry.source, "href"):
                source_href = entry.source.href
                if source_href and "news.google.com" not in source_href:
                    real_url = source_href

            if not title or not link:
                continue

            articles.append({
                "url": real_url,
                "google_url": link if "news.google.com" in link else "",
                "title": title,
                "summary": summary,
                "source": source_name,
                "published_at": published,
            })

        logger.info(f"Fetched {len(articles)} articles from {source_name}")
        return articles

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error for {source_name}: {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Request error for {source_name}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching {source_name}: {e}")
        return []


def fetch_all_sources():
    """Fetch articles from all configured sources. Returns {source_name: [articles]}."""
    all_articles = {}

    for source_name, source_config in RSS_SOURCES.items():
        articles = fetch_feed(source_name, source_config["url"])

        # Try fallback if primary fails
        if not articles and source_config.get("fallback_url"):
            logger.info(f"Trying fallback for {source_name}")
            articles = fetch_feed(source_name, source_config["fallback_url"])

        all_articles[source_name] = articles

    return all_articles
