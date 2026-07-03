import asyncio
import logging
import re
from html import escape
from telegram import Bot
from telegram.constants import ParseMode
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_SEND_DELAY

logger = logging.getLogger(__name__)

IMPORTANCE_EMOJI = {
    "Critical": "🔴",
    "High": "🟠",
    "Medium": "🟡",
    "Low": "⚪",
}

SOURCE_URLS = {
    "Reuters": "https://www.reuters.com",
    "AP News": "https://apnews.com",
    "BBC": "https://www.bbc.com",
    "Al Jazeera": "https://www.aljazeera.com",
    "DW": "https://www.dw.com",
    "NPR": "https://www.npr.org",
    "The Guardian": "https://www.theguardian.com",
    "Google News": "https://news.google.com",
    "ISW": "https://www.understandingwar.org",
}


def clean_url(url):
    """Clean Google News redirect URLs — return source website instead."""
    if not url:
        return ""
    if "news.google.com" in url:
        return ""
    return url


def format_article(article):
    importance = article.get("importance", "Low")
    emoji = IMPORTANCE_EMOJI.get(importance, "⚪")
    title_fa = article.get("title_fa") or article.get("title", "No title")
    source = article.get("source", "Unknown")
    published = article.get("published_at", "Unknown time")
    category = article.get("category", "general")
    countries = article.get("countries", "[]")
    if isinstance(countries, str):
        import json
        try:
            countries = json.loads(countries)
        except (json.JSONDecodeError, TypeError):
            countries = []

    summary_fa = article.get("summary_fa") or article.get("summary", "")
    if len(summary_fa) > 2000:
        summary_fa = summary_fa[:1997] + "..."

    countries_str = ", ".join(countries) if countries else "N/A"
    raw_url = article.get("url", "")
    url = clean_url(raw_url)
    source_url = SOURCE_URLS.get(source, "")
    title_en = article.get("title", "")

    if published and published != "Unknown time":
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            published = dt.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            pass

    message = (
        f"{emoji} <b>{escape(importance)}</b>\n\n"
        f"📌 <b>{escape(title_fa)}</b>\n"
    )

    # Show English title if different from Persian
    if title_en and title_fa and title_en != title_fa:
        message += f"🇬🇧 {escape(title_en)}\n"

    if source_url:
        message += f'📰 <a href="{escape(source_url)}">{escape(source)}</a>'
    else:
        message += f"📰 {escape(source)}"

    message += f" | 🕐 {escape(str(published))}\n"
    message += f"🏷️ {escape(category)} | 🌍 {escape(countries_str)}\n\n"

    if summary_fa:
        message += f"{escape(summary_fa)}\n"

    # Only show article link if it's a real URL (not Google News redirect)
    if url:
        message += f'\n🔗 <a href="{escape(url)}">مطالعه مقاله</a>'

    return message


async def send_articles(articles, chat_id=None):
    if not articles:
        return 0, []

    target_chat = chat_id or TELEGRAM_CHAT_ID
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    sent_count = 0
    sent_ids = []

    for article in articles:
        try:
            message = format_article(article)
            await bot.send_message(
                chat_id=target_chat,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent_count += 1
            sent_ids.append(article["id"])
            logger.info(f"Sent article {article['id']}: {article['title'][:50]}")
            await asyncio.sleep(TELEGRAM_SEND_DELAY)

        except Exception as e:
            logger.error(f"Failed to send article {article.get('id')}: {e}")
            try:
                await asyncio.sleep(3)
                await bot.send_message(
                    chat_id=target_chat,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                sent_count += 1
                sent_ids.append(article["id"])
            except Exception as e2:
                logger.error(f"Retry also failed for {article.get('id')}: {e2}")

    return sent_count, sent_ids


def send_articles_sync(articles):
    return asyncio.run(send_articles(articles))


async def send_run_summary(stats):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    message = (
        f"📊 <b>News Monitor Run Complete</b>\n\n"
        f"🕐 {stats['time']}\n"
        f"📡 Sources: {stats['sources_fetched']}\n"
        f"📰 Found: {stats['articles_found']}\n"
        f"🆕 New: {stats['articles_new']}\n"
        f"📤 Sent: {stats['articles_sent']}\n"
    )
    if stats.get("errors"):
        message += f"⚠️ Errors: {len(stats['errors'])}\n"

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to send run summary: {e}")
