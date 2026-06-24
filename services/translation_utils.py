import httpx
from cachetools import TTLCache

# Translation cache (key: (text, src, tgt))
_translation_cache = TTLCache(maxsize=256, ttl=3600)

def _translate_text(text: str, src: str = "en", tgt: str = "en") -> str:
    """Translate `text` from `src` language to `tgt` using LibreTranslate.
    Returns original text if src == tgt or on failure.
    """
    if src == tgt:
        return text
    cache_key = (text, src, tgt)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]
    try:
        resp = httpx.post(
            "https://libretranslate.de/translate",
            json={"q": text, "source": src, "target": tgt, "format": "text"},
            timeout=5,
        )
        resp.raise_for_status()
        translated = resp.json().get("translatedText", text)
        _translation_cache[cache_key] = translated
        return translated
    except Exception:
        # Fallback to original text on any error
        return text

def _maybe_translate_input(**kwargs):
    """Extract language param and translate all string inputs to English.
    Returns a tuple (modified_kwargs, original_language).
    """
    language = kwargs.pop("language", "en")
    # Translate each string argument to English for Groq
    for key, val in list(kwargs.items()):
        if isinstance(val, str):
            kwargs[key] = _translate_text(val, src=language, tgt="en")
    return kwargs, language

def _translate_output(data, target_lang: str):
    """Recursively translate all string fields in a JSON‑serialisable dict/list back to target language.
    """
    if target_lang == "en":
        return data
    if isinstance(data, dict):
        return {k: _translate_output(v, target_lang) for k, v in data.items()}
    if isinstance(data, list):
        return [_translate_output(item, target_lang) for item in data]
    if isinstance(data, str):
        return _translate_text(data, src="en", tgt=target_lang)
    return data
