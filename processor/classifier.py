import re
import logging
from config import CATEGORY_KEYWORDS, IMPORTANCE_KEYWORDS, COUNTRIES, RSS_SOURCES

logger = logging.getLogger(__name__)


def classify_category(text):
    """Classify article into a category based on keyword matching."""
    text_lower = text.lower()
    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


def classify_importance(text, source):
    """Classify importance level based on keywords and source weight."""
    text_lower = text.lower()
    score = 0

    for level, keywords in IMPORTANCE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                if level == "critical":
                    score += 4
                elif level == "high":
                    score += 3
                elif level == "medium":
                    score += 2

    # Source weight bonus
    source_weight = RSS_SOURCES.get(source, {}).get("weight", 1.0)
    score *= source_weight

    if score >= 8:
        return "Critical"
    elif score >= 5:
        return "High"
    elif score >= 2:
        return "Medium"
    else:
        return "Low"


def detect_countries(text):
    """Detect mentioned countries in article text."""
    found = []
    text_lower = text.lower()

    for country in COUNTRIES:
        # Use word boundary matching for short names
        if len(country) <= 3:
            pattern = r'\b' + re.escape(country) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                found.append(country)
        else:
            if country.lower() in text_lower:
                found.append(country)

    return list(set(found))


def classify_article(article):
    """Full classification pipeline for an article."""
    text = " ".join(filter(None, [
        article.get("title", ""),
        article.get("summary", ""),
        article.get("content", ""),
    ]))

    category = classify_category(text)
    importance = classify_importance(text, article.get("source", ""))
    countries = detect_countries(text)

    article["category"] = category
    article["importance"] = importance
    article["countries"] = countries

    return article
