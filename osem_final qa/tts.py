import io
import logging
import re
import threading
import time
from collections import OrderedDict

from gtts import gTTS

import config
import gemini_client
import http_utils

logger = logging.getLogger(__name__)

_session = http_utils.build_session(config.HTTP_MAX_RETRIES)

GROQ_SPEECH_URL = "https://api.groq.com/openai/v1/audio/speech"

GROQ_EN_VOICE_OPTIONS = [
    {"model": "canopylabs/orpheus-v1-english", "voice": config.GROQ_TTS_VOICE_EN},
    {"model": "playai-tts", "voice": "Fritz-PlayAI"},
]

PROVIDER_COOLDOWN_SECONDS = 300
AUDIO_CACHE_MAX_ITEMS = 64

_state_lock = threading.Lock()
_disabled_until = {}
_audio_cache = OrderedDict()


def _is_disabled(provider):
    with _state_lock:
        return _disabled_until.get(provider, 0) > time.time()


def _disable(provider, seconds=PROVIDER_COOLDOWN_SECONDS):
    with _state_lock:
        _disabled_until[provider] = time.time() + seconds


def _cache_get(key):
    with _state_lock:
        value = _audio_cache.get(key)
        if value is not None:
            _audio_cache.move_to_end(key)
        return value


def _cache_put(key, value):
    with _state_lock:
        _audio_cache[key] = value
        _audio_cache.move_to_end(key)
        while len(_audio_cache) > AUDIO_CACHE_MAX_ITEMS:
            _audio_cache.popitem(last=False)


# UPICON is a name and must be spoken as one word, never spelled out as U-P-I-C-O-N.
# The Devanagari spelling makes every voice engine read it as a single word, in English
# and Hindi speech alike. Only the standalone name is replaced: domains such as
# upicon.in are left alone, and the text shown on screen is not changed.
_UPICON_SPOKEN = "उपिकॉन"
_UPICON_LATIN_RE = re.compile(r"(?<![\w/.@-])upicon(?![\w@-]|\.\w)", re.IGNORECASE)
_UPICON_HINDI_RE = re.compile(r"यू\s*पी\s*आई\s*कॉन")


def clean_text_for_speech(text):
    """Strip HTML tags, links and markdown noise so only speakable words remain."""
    if not text:
        return ""
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_#`~|^]+", " ", text)
    text = _UPICON_HINDI_RE.sub(_UPICON_SPOKEN, text)
    text = _UPICON_LATIN_RE.sub(_UPICON_SPOKEN, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _groq_english(text):
    """Call Groq's TTS API. Raises on failure so the caller can fall back."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("Groq API key is not configured")
    last_error = None
    for option in GROQ_EN_VOICE_OPTIONS:
        try:
            response = _session.post(
                GROQ_SPEECH_URL,
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": option["model"],
                    "voice": option["voice"],
                    "input": text,
                    "response_format": "wav",
                },
                timeout=(config.HTTP_CONNECT_TIMEOUT, config.GROQ_TTS_READ_TIMEOUT),
            )
            if response.status_code == 200 and response.content:
                return response.content, "audio/wav"
            last_error = f"{option['model']} returned {response.status_code}: {response.text[:200]}"
            logger.warning("Groq TTS attempt failed: %s", last_error)
            if response.status_code in (401, 403):
                _disable("groq")
                break
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Groq TTS attempt errored: %s", last_error)
    raise RuntimeError(f"Groq TTS failed for all voice options: {last_error}")


def _gtts_speech(text, lang, tld="com"):
    """Last-resort speech using gTTS.
    tld='co.in' forces the Indian-accented English voice; Hindi (lang='hi')
    is always the India-based voice regardless of tld, so this guarantees a
    clear Indian accent for both languages even if every other provider fails.
    Each attempt has an explicit timeout and failures are retried a bounded
    number of times.
    """
    last_error = None
    for attempt in range(config.GTTS_MAX_RETRIES + 1):
        try:
            buffer = io.BytesIO()
            gTTS(text=text, lang=lang, tld=tld, timeout=config.GTTS_TIMEOUT).write_to_fp(buffer)
            buffer.seek(0)
            return buffer.read(), "audio/mpeg"
        except Exception as exc:
            last_error = exc
            logger.warning("gTTS attempt %d failed: %s", attempt + 1, exc)
            if attempt < config.GTTS_MAX_RETRIES:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"gTTS failed after retries: {last_error}")


def _try_gemini(text, lang):
    if _is_disabled("gemini"):
        return None
    try:
        return gemini_client.synthesize_speech(text, lang=lang)
    except gemini_client.GeminiUnavailableError as exc:
        _disable("gemini")
        logger.warning("Gemini TTS unavailable, skipping it for %ss: %s", PROVIDER_COOLDOWN_SECONDS, exc)
    except Exception as exc:
        logger.warning("Gemini TTS failed: %s", exc)
    return None


def synthesize_english(text):
    """English speech, Indian-accented. Order: Gemini (steered to a clear
    Indian English accent) -> Groq -> gTTS with tld='co.in' as the guaranteed
    Indian-accent fallback."""
    result = _try_gemini(text, "en")
    if result:
        return result
    if not _is_disabled("groq"):
        try:
            return _groq_english(text)
        except Exception as exc:
            logger.warning("Groq TTS unavailable, falling back to gTTS (Indian English): %s", exc)
    return _gtts_speech(text, lang="en", tld="co.in")


def synthesize_hindi(text):
    """Hindi speech, Indian-accented. Order: Gemini (steered to clear, simple
    Indian Hindi) -> gTTS Hindi (always an India-based voice) as fallback."""
    result = _try_gemini(text, "hi")
    if result:
        return result
    return _gtts_speech(text, lang="hi")


def synthesize_speech(text, lang):
    """Return (audio_bytes, mimetype) of clear, Indian-accented speech for the
    given text and language ('en' or 'hi')."""
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        raise ValueError("No speakable text provided")
    cache_key = (lang, clean_text)
    cached = _cache_get(cache_key)
    if cached:
        return cached
    if lang == "hi":
        result = synthesize_hindi(clean_text)
    else:
        result = synthesize_english(clean_text)
    _cache_put(cache_key, result)
    return result