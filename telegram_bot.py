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

    # Header message (always same)
    header = (
        f"{emoji} <b>{escape(importance)}</b>\n\n"
        f"📌 <b>{escape(title_fa)}</b>\n"
    )
    if title_en and title_fa and title_en != title_fa:
        header += f"🇬🇧 {escape(title_en)}\n"

    if source_url:
        header += f'📰 <a href="{escape(source_url)}">{escape(source)}</a>'
    else:
        header += f"📰 {escape(source)}"

    header += f" | 🕐 {escape(str(published))}\n"
    header += f"🏷️ {escape(category)} | 🌍 {escape(countries_str)}\n\n"

    # Split summary into chunks of 10 lines
    messages = []
    if summary_fa:
        lines = summary_fa.split("\n")
        # If single line, split by sentence
        if len(lines) <= 1:
            lines = summary_fa.split(". ")
            lines = [l.strip() + "." if not l.strip().endswith(".") else l.strip() for l in lines if l.strip()]

        chunk = []
        for line in lines:
            chunk.append(line)
            if len(chunk) >= 10:
                messages.append("\n".join(chunk))
                chunk = []
        if chunk:
            messages.append("\n".join(chunk))
    else:
        messages.append("(No summary available)")

    # First message: header + first chunk
    result = [header + messages[0]]

    # Remaining chunks as follow-up messages
    for msg in messages[1:]:
        result.append(f"📄 <b>{escape(title_fa[:30])}...</b>\n\n{escape(msg)}")

    # Last message: link
    if url:
        result.append(f'🔗 <a href="{escape(url)}">مطالعه مقاله</a>')

    return result


async def send_articles(articles, chat_id=None):
    if not articles:
        return 0, []

    target_chat = chat_id or TELEGRAM_CHAT_ID
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    sent_count = 0
    sent_ids = []

    for article in articles:
        try:
            messages = format_article(article)
            for msg in messages:
                await bot.send_message(
                    chat_id=target_chat,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.5)
            sent_count += 1
            sent_ids.append(article["id"])
            logger.info(f"Sent article {article['id']}: {article['title'][:50]}")
            await asyncio.sleep(TELEGRAM_SEND_DELAY)

        except Exception as e:
            logger.error(f"Failed to send article {article.get('id')}: {e}")
            try:
                await asyncio.sleep(3)
                for msg in messages:
                    await bot.send_message(
                        chat_id=target_chat,
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                    await asyncio.sleep(0.5)
                sent_count += 1
                sent_ids.append(article["id"])
            except Exception as e2:
                logger.error(f"Retry also failed for {article.get('id')}: {e2}")

    return sent_count, sent_ids


def send_articles_sync(articles):
    return asyncio.run(send_articles(articles))


async def send_run_summary(stats, chat_id=None):
    target_chat = chat_id or TELEGRAM_CHAT_ID
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
            chat_id=target_chat,
            text=message,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to send run summary: {e}")
