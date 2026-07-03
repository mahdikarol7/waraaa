import re
import logging
from processor.translator import translate_to_persian

logger = logging.getLogger(__name__)


def extract_key_sentences(text, num_sentences=3):
    """Extract the most important sentences from text using a simple scoring heuristic."""
    if not text or len(text) < 50:
        return text

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    # Score sentences: first sentence gets a bonus, longer sentences get a bonus
    scored = []
    for i, sent in enumerate(sentences):
        score = len(sent) / 100.0  # length bonus
        if i == 0:
            score += 1.5  # lead sentence bonus
        if i == 1:
            score += 0.5  # second sentence bonus
        # Check for important keywords
        important_words = [
            "killed", "destroyed", "attack", "missile", "strike", "offensive",
            "critical", "major", "significant", "confirmed", "reported",
            "according to", "sources", "officials",
        ]
        for word in important_words:
            if word.lower() in sent.lower():
                score += 0.3
        scored.append((score, i, sent))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:num_sentences], key=lambda x: x[1])  # restore order
    return " ".join(s[2] for s in top)


def generate_persian_summary(article):
    """Generate a Persian summary from article content."""
    # Translate title (most important for Persian readers)
    title = article.get("title", "")
    if title:
        article["title_fa"] = translate_to_persian(title)

    # For summary: use first 2 sentences, translated
    source_text = article.get("summary", "") or article.get("content", "")
    if source_text:
        first_sentences = extract_key_sentences(source_text, num_sentences=2)
        article["summary_fa"] = translate_to_persian(first_sentences)
    else:
        article["summary_fa"] = article.get("title_fa", "")

    return article
