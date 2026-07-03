import logging
from deep_translator import GoogleTranslator, MyMemoryTranslator

logger = logging.getLogger(__name__)

_cache = {}
PERSIAN_RANGE = set(range(0x0600, 0x06FF + 1))

# Track consecutive failures to skip translation entirely if service is down
_consecutive_failures = 0
_CIRCUIT_BREAKER_THRESHOLD = 5


def _is_persian(text):
    persian_chars = sum(1 for c in text if ord(c) in PERSIAN_RANGE)
    return persian_chars > len(text) * 0.3


def _translate_chunk(text):
    """Try Google once, then MyMemory once. No retries, no sleeping."""
    global _consecutive_failures

    if _consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
        return text

    try:
        result = GoogleTranslator(source="en", target="fa").translate(text)
        if result:
            _consecutive_failures = 0
            return result
    except Exception:
        pass

    try:
        result = MyMemoryTranslator(source="en", target="fa").translate(text)
        if result:
            _consecutive_failures = 0
            return result
    except Exception:
        pass

    _consecutive_failures += 1
    return text


def translate_to_persian(text):
    if not text or not text.strip():
        return text

    text = text.strip()

    if _is_persian(text):
        return text

    if text in _cache:
        return _cache[text]

    # Skip long texts — just translate first 2000 chars
    if len(text) > 2000:
        text_to_translate = text[:2000]
    else:
        text_to_translate = text

    result = _translate_chunk(text_to_translate)
    _cache[text] = result
    return result
