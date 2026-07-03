import httpx
import logging
from trafilatura import extract as trafilatura_extract
from config import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


MIN_SUMMARY_LENGTH = 200


def extract_full_text(url, fallback_summary=""):
    """Extract full article text from URL using trafilatura. Falls back to summary."""
    if not url:
        return fallback_summary

    # Skip extraction if summary is already good enough
    if fallback_summary and len(fallback_summary) >= MIN_SUMMARY_LENGTH:
        logger.debug(f"Summary sufficient ({len(fallback_summary)} chars), skipping extraction for {url}")
        return fallback_summary

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsBot/1.0"
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        text = trafilatura_extract(response.text)
        if text and len(text) > 50:
            return text

        logger.debug(f"trafilatura returned short/no content for {url}")
        return fallback_summary

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP {e.response.status_code} extracting {url}")
        return fallback_summary
    except httpx.RequestError as e:
        logger.warning(f"Request error extracting {url}: {e}")
        return fallback_summary
    except Exception as e:
        logger.warning(f"Extraction error for {url}: {e}")
        return fallback_summary
