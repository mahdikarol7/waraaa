import asyncio
import logging
import sys
import os
import json
from datetime import datetime, timezone

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
from scheduler import setup_scheduler


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


async def run_monitor():
    """Main monitoring cycle: fetch, process, send."""
    started_at = datetime.now(timezone.utc).isoformat()
    logger = logging.getLogger("monitor")
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
        "escalat", "ceasefire", "negotiat", "peace talk",
        "cruise missile", "ballistic", "himars", "patriot", "s-300",
        "kherson", "mykolaiv", "dnipro", "odesa", "mariupol",
    ]

    def is_war_relevant(article):
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        return any(kw in text for kw in WAR_KEYWORDS)

    filtered = [a for a in unique_articles if is_war_relevant(a)]
    logger.info(f"War-relevant filter: {len(filtered)}/{len(unique_articles)} articles passed")

    # Cap at 30 articles per run to keep it manageable
    MAX_ARTICLES_PER_RUN = 30
    if len(filtered) > MAX_ARTICLES_PER_RUN:
        filtered = filtered[:MAX_ARTICLES_PER_RUN]
        logger.info(f"Capped to {MAX_ARTICLES_PER_RUN} articles per run")

    unique_articles = filtered

    # Step 3: Process each article
    articles_new = 0
    processed_articles = []

    total = len(unique_articles)
    for i, article in enumerate(unique_articles, 1):
        try:
            # Skip full-text extraction (RSS summary is enough, saves ~4 sec per article)
            article["content"] = article.get("summary", "")

            # Classify
            article = classify_article(article)

            # Translate and summarize
            article = generate_persian_summary(article)

            # Store in DB
            if insert_article(article):
                articles_new += 1
                processed_articles.append(article)

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


async def main():
    """Main entry point: init DB, set up scheduler, start bot."""
    setup_logging()
    logger = logging.getLogger("main")

    # Validate config
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Add it to .env file.")
        sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set. Add it to .env file.")
        sys.exit(1)

    # Init database
    init_db()
    logger.info("Database initialized")

    # Check for test mode
    if "--test" in sys.argv:
        logger.info("Running in test mode (single immediate run)")
        await run_monitor()
        logger.info("Test run complete")
        return

    # Set up scheduler
    scheduler = setup_scheduler(run_monitor)
    scheduler.start()

    logger.info("News monitor scheduler started")
    logger.info(f"Next runs at: {', '.join(job.next_run_time.isoformat() for job in scheduler.get_jobs())}")

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
