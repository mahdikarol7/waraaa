import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Schedule times (24h format, local timezone)
SCHEDULE_TIMES = ["05:00", "08:00", "11:00", "14:00", "17:00", "20:00", "23:00"]

# Database
DB_PATH = os.path.join(os.path.dirname(__file__), "news.db")

# Logging
LOG_FILE = os.path.join(os.path.dirname(__file__), "news_manager.log")
LOG_LEVEL = "INFO"

# HTTP
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2

# Deduplication
TITLE_SIMILARITY_THRESHOLD = 0.85

# Telegram
MAX_ARTICLES_PER_MESSAGE = 5
TELEGRAM_SEND_DELAY = 1.0  # seconds between sends

# RSS Sources
RSS_SOURCES = {
    "Reuters": {
        "url": "https://news.google.com/rss/search?q=site:reuters.com+war+OR+conflict+OR+strike&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://www.reuters.com/arc/outboundfeeds/v3/all/rss.xml",
        "weight": 1.2,
    },
    "AP News": {
        "url": "https://feedx.net/rss/ap.xml",
        "fallback_url": "https://rsshub.app/apnews/topics/world-news",
        "weight": 1.1,
    },
    "BBC": {
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "fallback_url": None,
        "weight": 1.0,
    },
    "Al Jazeera": {
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "fallback_url": None,
        "weight": 1.0,
    },
    "DW": {
        "url": "https://rss.dw.com/rdf/rss-en-all",
        "fallback_url": None,
        "weight": 0.9,
    },
    "Google News": {
        "url": "https://news.google.com/rss/search?q=ukraine+war+OR+russia+war+OR+middle+east+war&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": None,
        "weight": 0.8,
    },
    "ISW": {
        "url": "https://news.google.com/rss/search?q=ISW+institute+for+the+study+of+war&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://news.google.com/rss/search?q=understandingwar+daily+update&hl=en-US&gl=US&ceid=US:en",
        "weight": 1.3,
    },
}

# Category keywords
CATEGORY_KEYWORDS = {
    "missile_strike": [
        "missile", "ballistic", "cruise missile", "interceptor", "air defense",
        "s-300", "s-400", "patriot", " HIMARS", "rocket", "projectile",
    ],
    "air_attack": [
        "airstrike", "air strike", "bombing", "drone", "uav", "shahed",
        "kamikaze drone", "fighter jet", "bomber", "aviation", "aerial",
    ],
    "ground_war": [
        "offensive", "frontline", "front line", "infantry", "tank",
        "artillery", "bakhmut", "avdiivka", "counteroffensive", "advance",
        "retreat", "capture", "liberate", "trench",
    ],
    "diplomacy": [
        "diplomat", "negotiate", "negotiation", "ceasefire", "peace talk",
        "summit", "sanctions", "treaty", "agreement", "un resolution",
        "united nations", "security council",
    ],
    "sanctions": [
        "sanction", "embargo", "restrict", "ban", "freeze asset",
        "economic pressure", "trade ban", "export control",
    ],
    "nuclear": [
        "nuclear", "radiation", "chernobyl", "zaporizhzhia", "reactor",
        "atomic", "npp", "nuclear plant",
    ],
    "humanitarian": [
        "civilian", "casualty", "refugee", "humanitarian", "evacuate",
        "displaced", "red cross", "aid", "human rights", "war crime",
    ],
    "energy": [
        "pipeline", "gas", "oil", "energy", "gazprom", "naftogaz",
        "power grid", "electricity", "blackout",
    ],
    "cyber": [
        "cyber", "hack", "malware", "ransomware", "phishing", "ddos",
        "information warfare", "propaganda",
    ],
}

# Importance keywords (scored)
IMPORTANCE_KEYWORDS = {
    "critical": [
        "nuclear", "tactical nuclear", "mobilization", "declaration of war",
        "mass casualty", "chemical weapon", "biological weapon",
        "escalation", "red line", "ww3", "world war",
    ],
    "high": [
        "missile", "bombed", "killed", "destroyed", "captured",
        "counteroffensive", "major", "significant", "large-scale",
        "zelensky", "putin", "biden", "nato",
    ],
    "medium": [
        "drone", "shelling", "clash", "fighting", "troops",
        "weapon", "supply", "training", "equipment",
    ],
}

# Countries to detect
COUNTRIES = [
    "Ukraine", "Russia", "United States", "USA", "US", "Britain", "United Kingdom",
    "UK", "France", "Germany", "Poland", "Turkey", "Türkiye", "China", "Iran",
    "Israel", "Palestine", "Gaza", "Syria", "Lebanon", "Hezbollah", "Hamas",
    "Georgia", "Belarus", "Kazakhstan", "Moldova", "Romania", "Bulgaria",
    "Lithuania", "Latvia", "Estonia", "Finland", "Sweden", "Norway",
    "Czech Republic", "Slovakia", "Hungary", "Croatia", "Serbia",
    "NATO", "European Union", "EU", "United Nations", "UN",
    "North Korea", "South Korea", "Japan", "India", "Pakistan",
    "Iraq", "Yemen", "Saudi Arabia", "Qatar", "UAE", "Egypt", "Jordan",
    "Caucasus", "Donbas", "Crimea", "Kyiv", "Kharkiv", "Odesa",
]
