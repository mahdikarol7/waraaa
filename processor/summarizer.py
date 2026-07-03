import re
import logging
from processor.translator import translate_to_persian

logger = logging.getLogger(__name__)


def clean_html(text):
    """Remove HTML tags from text."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_key_sentences(text, num_sentences=3):
    """Extract the most important sentences from text."""
    if not text or len(text) < 50:
        return text

    # Clean HTML first
    text = clean_html(text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    scored = []
    for i, sent in enumerate(sentences):
        score = len(sent) / 100.0
        if i == 0:
            score += 1.5
        if i == 1:
            score += 0.5
        if i == 2:
            score += 0.3
        important_words = [
            "killed", "destroyed", "attack", "missile", "strike", "offensive",
            "critical", "major", "significant", "confirmed", "reported",
            "according to", "sources", "officials", "bodies", "forces",
        ]
        for word in important_words:
            if word.lower() in sent.lower():
                score += 0.3
        scored.append((score, i, sent))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:num_sentences], key=lambda x: x[1])
    return " ".join(s[2] for s in top)


def generate_persian_summary(article):
    """Generate a Persian summary with title + 3-line summary."""
    title = article.get("title", "")
    if title:
        article["title_fa"] = translate_to_persian(title)

    source_text = article.get("summary", "") or article.get("content", "")
    if source_text:
        key_text = extract_key_sentences(source_text, num_sentences=8)
        article["summary_fa"] = translate_to_persian(key_text)
    else:
        article["summary_fa"] = article.get("title_fa", "")

    return article
