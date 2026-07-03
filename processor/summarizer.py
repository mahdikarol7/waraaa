import re
import logging
from processor.translator import translate_to_persian
from processor.extractor import extract_full_text

logger = logging.getLogger(__name__)


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_key_sentences(text, num_sentences=8):
    if not text or len(text) < 50:
        return text

    text = clean_html(text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    scored = []
    for i, sent in enumerate(sentences):
        score = len(sent) / 100.0
        if i == 0:
            score += 2.0
        elif i == 1:
            score += 1.0
        elif i == 2:
            score += 0.5
        important_words = [
            "killed", "destroyed", "attack", "missile", "strike", "offensive",
            "critical", "major", "significant", "confirmed", "reported",
            "according to", "sources", "officials", "bodies", "forces",
            "ukraine", "russia", "iran", "israel", "gaza", "nuclear",
        ]
        for word in important_words:
            if word.lower() in sent.lower():
                score += 0.5
        scored.append((score, i, sent))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:num_sentences], key=lambda x: x[1])
    return " ".join(s[2] for s in top)


def generate_persian_summary(article):
    title = article.get("title", "")
    if title:
        article["title_fa"] = translate_to_persian(title)

    # Combine all available text for maximum content
    summary_text = clean_html(article.get("summary", ""))
    content_text = clean_html(article.get("content", ""))

    # If summary is short, try to get full text
    if len(summary_text) < 300 and article.get("url"):
        full_text = extract_full_text(article["url"], "")
        if full_text and len(full_text) > len(summary_text):
            content_text = clean_html(full_text)

    # Combine: title + summary + content for rich context
    combined = " ".join(filter(None, [title, summary_text, content_text]))

    if combined:
        key_text = extract_key_sentences(combined, num_sentences=16)
        article["summary_fa"] = translate_to_persian(key_text)
    else:
        article["summary_fa"] = article.get("title_fa", "")

    return article
