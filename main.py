import asyncio
import logging
import sys
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, time as dtime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_FILE, LOG_LEVEL
from database import (
    init_db, insert_article, get_unsent_articles, mark_sent, log_run,
    add_user, get_all_users, use_news_token
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
MAX_ARTICLES_PER_RUN = 10  # auto-schedule sends 10; /news sends 30


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# Exclude non-relevant regions (only exact matches to avoid false positives)
EXCLUDE_KEYWORDS = [
    "china-taiwan", "south china sea", "taipei", "beijing",
    "myanmar", "sudan", "ethiopia", "haiti", "venezuela",
]


def is_war_relevant(article):
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    core_conflicts = ["ukraine", "russia", "gaza", "israel", "iran", "syria", "hezbollah", "hamas"]
    has_core = any(kw in text for kw in core_conflicts)
    if has_core:
        return True
    if any(kw in text for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in text for kw in WAR_KEYWORDS)


async def run_monitor(context: ContextTypes.DEFAULT_TYPE = None, target_chat_id=None, max_articles=None, when=None):
    """Main monitoring cycle: fetch, process, send."""
    started_at = datetime.now(timezone.utc).isoformat()
    errors = []
    is_auto = max_articles is None  # auto-schedule uses default, /news overrides
    limit = max_articles or MAX_ARTICLES_PER_RUN

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

    if len(filtered) > limit:
        filtered = filtered[:limit]
        logger.info(f"Capped to {limit} articles per run")

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
            # If called by /news, send to that user. If auto-schedule, send to all users.
            if target_chat_id:
                users = [target_chat_id]
            else:
                users = get_all_users()
                if not users:
                    users = [TELEGRAM_CHAT_ID]

            total_sent = 0
            for uid in users:
                sent, ids = await send_articles(unsent, chat_id=uid)
                total_sent += sent
                if uid != target_chat_id:
                    await asyncio.sleep(0.5)

            articles_sent = total_sent
            mark_sent([a["id"] for a in unsent])
            logger.info(f"Sent {articles_sent} articles to {len(users)} user(s)")
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

    # Step 6: Send run summary to owner (only for auto-schedule, not /news)
    if not target_chat_id:
        try:
            await send_run_summary({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sources_fetched": sources_fetched,
                "articles_found": articles_found,
                "articles_new": articles_new,
                "articles_sent": articles_sent,
                "errors": errors,
            }, chat_id=TELEGRAM_CHAT_ID)
        except Exception as e:
            logger.error(f"Failed to send summary: {e}")

    logger.info(
        f"Run complete: {articles_sent} sent, {articles_new} new, "
        f"{len(errors)} errors"
    )
    logger.info("=" * 60)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /news command — register user and send news to them."""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name
    add_user(chat_id, username)

    # Check token
    success, remaining, hours = use_news_token(chat_id)
    if not success:
        await update.message.reply_text(
            f"No tokens left. Refills every 3 hours.\n"
            f"Try again in {hours} hour(s)."
        )
        return

    await update.message.reply_text(f"Fetching latest news, please wait... ({remaining} token(s) left)")

    try:
        await run_monitor(target_chat_id=str(chat_id), max_articles=30)
        await update.message.reply_text("Done! News sent.")
    except Exception as e:
        logger.error(f"Error in /news command: {e}")
        await update.message.reply_text(f"Error fetching news: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — register user."""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name
    add_user(chat_id, username)
    logger.info(f"New user registered: {chat_id} ({username})")

    await update.message.reply_text(
        "Welcome to War News Monitor Bot!\n\n"
        "Commands:\n"
        "/news - Get latest news now\n"
        "/status - Check bot status\n\n"
        "News is automatically sent every 3 hours."
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
        f"📊 Bot Status\n\n"
        f"📰 Articles in DB: {total}\n"
        f"📤 Sent: {sent}\n"
        f"📥 Pending: {unsent}\n"
        f"⏰ Auto-send: Every 3 hours"
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

    # Scheduled jobs at Iran time (UTC+3:30)
    from telegram.ext import JobQueue
    job_queue = app.job_queue

    # Iran times: 05:00, 08:00, 11:00, 14:00, 17:00, 20:00, 23:00
    # = UTC: 01:30, 04:30, 07:30, 10:30, 13:30, 16:30, 19:30
    iran_times = [
        (1, 30), (4, 30), (7, 30), (10, 30), (13, 30), (16, 30), (19, 30)
    ]
    for hour, minute in iran_times:
        job_queue.run_daily(
            run_monitor,
            time=dtime(hour=hour, minute=minute, tzinfo=timezone.utc),
            name=f"news_{hour:02d}:{minute:02d}_UTC",
        )

    logger.info("Bot started with /news command and Iran-time schedule (every 3 hours)")

    # Keep-alive HTTP server for Railway
    port = int(os.environ.get("PORT", 8080))

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, format, *args):
            pass

    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Keep-alive server running on port {port}")

    # Background keep-alive: ping Telegram every 5 minutes to prevent sleep
    import httpx
    def keep_alive_loop():
        import time
        while True:
            time.sleep(300)  # every 5 minutes
            try:
                r = httpx.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=10)
                logger.debug(f"Keep-alive ping: {r.status_code}")
            except Exception as e:
                logger.warning(f"Keep-alive ping failed: {e}")

    ka_thread = threading.Thread(target=keep_alive_loop, daemon=True)
    ka_thread.start()
    logger.info("Keep-alive ping started (every 5 min)")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
