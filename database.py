import sqlite3
import json
import os
from datetime import datetime, timezone
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            title_fa TEXT,
            summary TEXT,
            summary_fa TEXT,
            content TEXT,
            source TEXT NOT NULL,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            importance TEXT,
            countries TEXT,
            language TEXT DEFAULT 'en',
            is_duplicate INTEGER DEFAULT 0,
            duplicate_of INTEGER,
            sent_to_telegram INTEGER DEFAULT 0,
            sent_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            sources_fetched INTEGER,
            articles_found INTEGER,
            articles_new INTEGER,
            articles_sent INTEGER,
            errors TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            chat_id TEXT PRIMARY KEY,
            username TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            news_tokens INTEGER DEFAULT 4,
            last_token_refill TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_articles_sent ON articles(sent_to_telegram);
        CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
        CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at);
    """)
    conn.commit()

    # Add missing columns if DB already exists
    try:
        conn.execute("ALTER TABLE users ADD COLUMN news_tokens INTEGER DEFAULT 4")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN last_token_refill TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except Exception:
        pass
    conn.commit()
    conn.close()


def url_exists(url):
    conn = get_connection()
    row = conn.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None


def url_exists_bulk(urls):
    if not urls:
        return set()
    conn = get_connection()
    placeholders = ",".join("?" for _ in urls)
    rows = conn.execute(f"SELECT url FROM articles WHERE url IN ({placeholders})", urls).fetchall()
    conn.close()
    return {row["url"] for row in rows}


def insert_article(article):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO articles
            (url, title, title_fa, summary, summary_fa, content, source,
             published_at, category, importance, countries, language)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article["url"], article["title"], article.get("title_fa"),
            article.get("summary"), article.get("summary_fa"),
            article.get("content"), article["source"],
            article.get("published_at"), article.get("category"),
            article.get("importance"),
            json.dumps(article.get("countries", [])),
            article.get("language", "en"),
        ))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_unsent_articles(limit=50):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE sent_to_telegram = 0 AND is_duplicate = 0
        ORDER BY
            CASE importance
                WHEN 'Critical' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                WHEN 'Low' THEN 4
            END,
            published_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_sent(article_ids):
    if not article_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" for _ in article_ids)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        f"UPDATE articles SET sent_to_telegram = 1, sent_at = ? WHERE id IN ({placeholders})",
        [now] + list(article_ids),
    )
    conn.commit()
    conn.close()


def mark_duplicate(article_id, duplicate_of):
    conn = get_connection()
    conn.execute(
        "UPDATE articles SET is_duplicate = 1, duplicate_of = ? WHERE id = ?",
        (duplicate_of, article_id),
    )
    conn.commit()
    conn.close()


def get_recent_titles(hours=48):
    conn = get_connection()
    cutoff = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT id, title FROM articles WHERE fetched_at >= datetime('now', ?)",
        (f"-{hours} hours",),
    ).fetchall()
    conn.close()
    return [(row["id"], row["title"]) for row in rows]


def log_run(started_at, finished_at, sources_fetched, articles_found, articles_new, articles_sent, errors):
    conn = get_connection()
    conn.execute("""
        INSERT INTO run_log (started_at, finished_at, sources_fetched, articles_found,
                             articles_new, articles_sent, errors)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        started_at, finished_at, sources_fetched, articles_found,
        articles_new, articles_sent, json.dumps(errors) if errors else None,
    ))
    conn.commit()
    conn.close()


def add_user(chat_id, username=None):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT OR IGNORE INTO users (chat_id, username, first_seen, last_active, news_tokens, last_token_refill)
        VALUES (?, ?, ?, ?, 4, ?)
    """, (str(chat_id), username, now, now, now))
    conn.execute("""
        UPDATE users SET last_active = ? WHERE chat_id = ?
    """, (now, str(chat_id)))
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_connection()
    rows = conn.execute("SELECT chat_id FROM users").fetchall()
    conn.close()
    return [row["chat_id"] for row in rows]


MAX_TOKENS = 4
TOKEN_REFILL_HOURS = 24


def use_news_token(chat_id):
    """Try to use a /news token. Returns (success, tokens_remaining, hours_until_refill)."""
    conn = get_connection()
    now = datetime.now(timezone.utc)
    row = conn.execute(
        "SELECT news_tokens, last_token_refill FROM users WHERE chat_id = ?",
        (str(chat_id),)
    ).fetchone()

    if not row:
        conn.close()
        return False, 0, 0

    tokens = row["news_tokens"]
    last_refill = datetime.fromisoformat(row["last_token_refill"])

    # Refill tokens if enough time has passed
    hours_since_refill = (now - last_refill).total_seconds() / 3600
    if hours_since_refill >= TOKEN_REFILL_HOURS:
        tokens = MAX_TOKENS
        conn.execute(
            "UPDATE users SET news_tokens = ?, last_token_refill = ? WHERE chat_id = ?",
            (tokens, now.isoformat(), str(chat_id))
        )
        conn.commit()

    if tokens <= 0:
        hours_left = TOKEN_REFILL_HOURS - hours_since_refill
        conn.close()
        return False, 0, max(0, round(hours_left, 1))

    # Use a token
    tokens -= 1
    conn.execute(
        "UPDATE users SET news_tokens = ?, last_active = ? WHERE chat_id = ?",
        (tokens, now.isoformat(), str(chat_id))
    )
    conn.commit()
    conn.close()
    return True, tokens, 0
