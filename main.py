import logging
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_FILE, LOG_LEVEL
from database import (
    init_db, insert_article, get_unsent_articles, mark_sent, log_run
)
from sources import fetch_all_sources
from processor import (
    deduplicate_articles,
    classify_article, generate_persian_summary
)
from telegram_bot import send_articles, send_run_summary

logger = logging.getLogger(__name__)

WAR_KEYWORDS = [
    "war", "attack", "strike", "missile", "drone", "bomb", "blast",
    "explosion", "shelling", "offensive", "frontline", "troops",
    "military", "army", "weapon", "sanction", "ceasefire", "invasion",
    "conflict", "combat", "casualty", "killed", "wounded", "refugee",
    "evacuation", "nato", "nuclear", "air defense", "artillery",
    "ukraine", "russia", "gaza", "israel", "hezbollah", "hamas",
    "iran", "syria", "yemen", "houthi", "donbas", "crimea",
    "kyiv", "kharkiv", "belgorod", "sumy", "zaporizhzhia",
    "pentagon", "kremlin", "zelensky", "putin", "netanyahu",
    "escalat", "negotiat", "peace talk", "cruise missile",
    "ballistic", "himars", "patriot", "s-300", "kherson",
    "mykolaiv", "dnipro", "odesa", "mariupol",
]
MAX_ARTICLES_PER_RUN = 30


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def is_war_relevant(article):
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    return any(kw in text for kw in WAR_KEYWORDS)


async def run_monitor(context: ContextTypes.DEFAULT_TYPE = None):
    """Main monitoring cycle: fetch, process, send."""
    started_at = datetime.now(timezone.utc).isoformat()
    errors = []

    logger.info("=" * 60)
    logger.info("Starting news monitoring run")

    # Step 1: Fetch all sources
    all_articles = {}
    sources_fetched = 0
    articles_found = 0

    try:
        all_articles = fetch_all_sources()
        for source, articles in all_articles.items():
            if articles:
                sources_fetched += 1
                articles_found += len(articles)
    except Exception as e:
        logger.error(f"Error fetching sources: {e}")
        errors.append(f"Fetch error: {e}")

    logger.info(f"Fetched {articles_found} articles from {sources_fetched} sources")

    # Step 2: Flatten and deduplicate
    flat_articles = []
    for articles in all_articles.values():
        flat_articles.extend(articles)

    unique_articles, duplicate_urls = deduplicate_articles(flat_articles)
    logger.info(f"After dedup: {len(unique_articles)} unique articles")

    # Step 2.5: Pre-filter for war/conflict relevance
    filtered = [a for a in unique_articles if is_war_relevant(a)]
    logger.info(f"War-relevant filter: {len(filtered)}/{len(unique_articles)} articles passed")

    if len(filtered) > MAX_ARTICLES_PER_RUN:
        filtered = filtered[:MAX_ARTICLES_PER_RUN]
        logger.info(f"Capped to {MAX_ARTICLES_PER_RUN} articles per run")

    unique_articles = filtered

    # Step 3: Process each article
    articles_new = 0
    total = len(unique_articles)

    for i, article in enumerate(unique_articles, 1):
        try:
            article["content"] = article.get("summary", "")
            article = classify_article(article)
            article = generate_persian_summary(article)

            if insert_article(article):
                articles_new += 1

            if i % 25 == 0 or i == total:
                logger.info(f"Progress: {i}/{total} articles processed ({articles_new} new)")
        except Exception as e:
            logger.error(f"Error processing article '{article.get('title', '')[:50]}': {e}")
            errors.append(f"Processing error: {e}")

    logger.info(f"Processed and stored {articles_new} new articles")

    # Step 4: Get unsent articles and send to Telegram
    unsent = get_unsent_articles(limit=50)
    articles_sent = 0
    sent_ids = []

    if unsent:
        try:
            articles_sent, sent_ids = await send_articles(unsent)
            mark_sent(sent_ids)
            logger.info(f"Sent {articles_sent} articles to Telegram")
        except Exception as e:
            logger.error(f"Error sending to Telegram: {e}")
            errors.append(f"Telegram send error: {e}")
    else:
        logger.info("No new articles to send")

    # Step 5: Log run
    finished_at = datetime.now(timezone.utc).isoformat()
    log_run(
        started_at, finished_at, sources_fetched,
        articles_found, articles_new, articles_sent, errors
    )

    # Step 6: Send run summary
    try:
        await send_run_summary({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sources_fetched": sources_fetched,
            "articles_found": articles_found,
            "articles_new": articles_new,
            "articles_sent": articles_sent,
            "errors": errors,
        })
    except Exception as e:
        logger.error(f"Failed to send summary: {e}")

    logger.info(
        f"Run complete: {articles_sent} sent, {articles_new} new, "
        f"{len(errors)} errors"
    )
    logger.info("=" * 60)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /news command — fetch and send latest news immediately."""
    await update.message.reply_text("正在获取最新新闻，请稍候...")

    try:
        await run_monitor()
        await update.message.reply_text("新闻已发送完成!")
    except Exception as e:
        logger.error(f"Error in /news command: {e}")
        await update.message.reply_text(f"获取新闻时出错: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "欢迎使用战争新闻监控机器人!\n\n"
        "命令:\n"
        "/news - 立即获取最新新闻\n"
        "/status - 查看机器人状态\n\n"
        "新闻每3小时自动发送一次。"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    from database import get_connection
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM articles WHERE sent_to_telegram = 1").fetchone()[0]
    unsent = conn.execute("SELECT COUNT(*) FROM articles WHERE sent_to_telegram = 0 AND is_duplicate = 0").fetchone()[0]
    conn.close()

    await update.message.reply_text(
        f"📊 机器人状态\n\n"
        f"📰 数据库中的文章: {total}\n"
        f"📤 已发送: {sent}\n"
        f"📥 待发送: {unsent}\n"
        f"⏰ 自动发送: 每3小时"
    )


def main():
    setup_logging()
    logger.info("Starting War News Bot")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set.")
        sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set.")
        sys.exit(1)

    init_db()
    logger.info("Database initialized")

    # Test mode: single run without bot
    if "--test" in sys.argv:
        import asyncio
        logger.info("Running in test mode")
        asyncio.run(run_monitor())
        logger.info("Test run complete")
        return

    # Build bot application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("status", status_command))

    # Scheduled job: every 3 hours
    app.job_queue.run_repeating(
        run_monitor,
        interval=3 * 3600,  # 3 hours in seconds
        first=10,  # first run 10 seconds after start
        name="news_monitor",
    )

    logger.info("Bot started with /news command and 3-hour auto schedule")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
