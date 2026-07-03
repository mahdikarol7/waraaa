import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from database import url_exists_bulk
from config import TITLE_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def deduplicate_articles(articles):
    """Remove duplicates by URL exact match and title semantic similarity.
    Returns list of non-duplicate articles and list of duplicate URLs."""
    if not articles:
        return [], []

    # Step 1: URL dedup against DB
    urls = [a["url"] for a in articles]
    existing_urls = url_exists_bulk(urls)

    unique = []
    url_duplicates = []
    for a in articles:
        if a["url"] in existing_urls:
            url_duplicates.append(a["url"])
        else:
            unique.append(a)

    logger.info(f"URL dedup: {len(url_duplicates)} duplicates removed, {len(unique)} remaining")

    if len(unique) <= 1:
        return unique, url_duplicates

    # Step 2: Title similarity dedup within the batch
    titles = [a["title"] for a in unique]

    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(titles)
        sim_matrix = cosine_similarity(tfidf_matrix)
    except Exception as e:
        logger.warning(f"TF-IDF dedup failed: {e}")
        return unique, url_duplicates

    to_remove = set()
    for i in range(len(unique)):
        if i in to_remove:
            continue
        for j in range(i + 1, len(unique)):
            if j in to_remove:
                continue
            if sim_matrix[i][j] >= TITLE_SIMILARITY_THRESHOLD:
                to_remove.add(j)
                logger.debug(
                    f"Semantic dup: '{unique[j]['title'][:60]}' ~ '{unique[i]['title'][:60]}' "
                    f"(sim={sim_matrix[i][j]:.3f})"
                )

    semantic_duplicates = [unique[i]["url"] for i in sorted(to_remove)]
    result = [a for i, a in enumerate(unique) if i not in to_remove]

    logger.info(f"Semantic dedup: {len(semantic_duplicates)} duplicates removed, {len(result)} remaining")
    return result, url_duplicates + semantic_duplicates
