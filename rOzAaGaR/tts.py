"""
tts.py
─────────────────────────────────────────────────────────────
Server-side text-to-speech using TTS.ai's hosted Kokoro model.

Mirrors the style of speech.py (Groq Whisper STT): a single
synthesize_speech() function that returns (ok: bool, data_or_error).
On success, data_or_error is the raw audio bytes (mp3). On failure,
it's a human-readable error string.

This is intentionally fail-soft: if the API key is missing or the
request fails, we return ok=False and the caller (app.py) just
omits the "audio" field from the /chat response instead of breaking
the chat flow. Text chat keeps working even if TTS is down.
"""

import re
from typing import Optional, Tuple

import requests

from config import (
    logger,
    TTS_AI_API_KEY,
    TTS_AI_API_URL,
    TTS_AI_MODEL,
    TTS_AI_VOICE_EN,
    TTS_AI_VOICE_HI,
    TTS_MAX_CHARS,
    TTS_TIMEOUT,
)

# ── Number-to-words (for prices/amounts) ──────────────────────────────────
# Plain digit-spacing (below) is right for OTPs and phone numbers, but wrong
# for money: "1500.00" should be read "fifteen hundred", not "one five zero
# zero point zero zero". These helpers convert currency-shaped numbers
# (decimal amounts, comma-grouped thousands, or numbers with a ₹/Rs/INR/$
# prefix) into natural words before the digit-spacing rule ever sees them.
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _two_digit_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _four_digit_words(n: int) -> str:
    """Colloquial year/price style: 1500 -> 'fifteen hundred', 1905 ->
    'nineteen oh five', 4230 -> 'forty-two thirty'."""
    first, second = divmod(n, 100)
    if second == 0:
        return f"{_two_digit_words(first)} hundred"
    if second < 10:
        return f"{_two_digit_words(first)} oh {_ONES[second]}"
    return f"{_two_digit_words(first)} {_two_digit_words(second)}"


def _int_to_words(n: int) -> str:
    if n == 0:
        return "zero"
    if n < 0:
        return f"minus {_int_to_words(-n)}"
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _two_digit_words(n)
    if n < 1000:
        h, rem = divmod(n, 100)
        s = f"{_ONES[h]} hundred"
        return s + (f" {_two_digit_words(rem)}" if rem else "")
    if n < 10000:
        return _four_digit_words(n)
    if n < 1000000:
        th, rem = divmod(n, 1000)
        s = f"{_int_to_words(th)} thousand"
        return s + (f" {_int_to_words(rem)}" if rem else "")
    mil, rem = divmod(n, 1000000)
    s = f"{_int_to_words(mil)} million"
    return s + (f" {_int_to_words(rem)}" if rem else "")


def _money_to_words(int_part: str, dec_part: Optional[str]) -> str:
    n = int(int_part.replace(",", ""))
    words = _int_to_words(n)
    if dec_part:
        digits = dec_part[1:]  # drop leading "."
        if digits.strip("0"):  # non-zero cents -> "point four five"
            words += " point " + " ".join(_ONES[int(d)] for d in digits)
        # all-zero decimal (".00") is dropped — "1500.00" just reads "fifteen hundred"
    return words


# Matches, in priority order: (1) a ₹/Rs/INR/$-prefixed amount, (2) a
# comma-grouped number ("1,50,000" or "12,000.50"), (3) a bare decimal
# number ("1500.00"). Each requires a signal (symbol, comma, or decimal)
# that a plain phone number/OTP would never have, so those are left alone
# for the digit-spacing rule further down.
_SYMBOL_MONEY_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*(\d[\d,]*)(\.\d{1,2})?", re.IGNORECASE)
_COMMA_NUMBER_RE = re.compile(r"\b(\d{1,3}(?:,\d{2,3})+)(\.\d{1,2})?\b")
_DECIMAL_NUMBER_RE = re.compile(r"\b(\d+)(\.\d{1,2})\b")

# Emoji / pictographic symbol ranges — stripped so the voice doesn't try
# to pronounce them (same ranges the frontend already strips for the
# browser-voice fallback).
_EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\U00002600-\U000027BF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE0F\U0000200D]"
)
_EMAIL_RE = re.compile(r"([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*)\.([a-zA-Z]{2,})")
_LONG_DIGITS_RE = re.compile(r"\d{4,}")
_BULLETS_RE = re.compile(r"[•\-–—]")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_for_speech(text: str) -> str:
    """Same cleanup the frontend already does for the browser voice
    (email readout, money-in-words, digit spacing for OTPs/phone numbers,
    emoji/bullet stripping) so audio generated server-side sounds just as
    natural."""
    t = text or ""
    t = _EMAIL_RE.sub(lambda m: f"{m.group(1)} at {m.group(2)} dot {m.group(3)}", t)
    t = t.replace("@", " at ")
    # Money/amounts -> natural words BEFORE the generic digit-spacing rule,
    # so "₹1,500.00" or "1500.00" reads "fifteen hundred", not spaced digits.
    t = _SYMBOL_MONEY_RE.sub(lambda m: _money_to_words(m.group(1), m.group(2)), t)
    t = _COMMA_NUMBER_RE.sub(lambda m: _money_to_words(m.group(1), m.group(2)), t)
    t = _DECIMAL_NUMBER_RE.sub(lambda m: _money_to_words(m.group(1), m.group(2)), t)
    t = _EMOJI_RE.sub("", t)
    t = _BULLETS_RE.sub(" ", t)
    # Remaining long digit runs are OTPs/phone numbers — read digit-by-digit.
    t = _LONG_DIGITS_RE.sub(lambda m: " ".join(m.group(0)), t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t[:TTS_MAX_CHARS]


def _voice_for_lang(ui_lang: str) -> str:
    return TTS_AI_VOICE_HI if (ui_lang or "").lower().startswith("hi") else TTS_AI_VOICE_EN


def synthesize_speech(text: str, ui_lang: str = "en") -> Tuple[bool, Optional[bytes]]:
    """Convert text to speech via TTS.ai (Kokoro model).

    Returns (True, audio_bytes) on success, (False, error_message) on
    failure. Never raises — all failure paths are caught and logged.
    """
    if not TTS_AI_API_KEY:
        return False, "Text-to-speech is not configured on the server."

    cleaned = _clean_for_speech(text)
    if not cleaned:
        return False, "Nothing to speak."

    headers = {
        "Authorization": f"Bearer {TTS_AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": TTS_AI_MODEL,
        "input": cleaned,
        "voice": _voice_for_lang(ui_lang),
        "response_format": "mp3",
    }

    try:
        resp = requests.post(
            TTS_AI_API_URL,
            headers=headers,
            json=payload,
            timeout=TTS_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.exception("TTS.ai request failed")
        return False, f"Speech service unreachable: {e}"

    if resp.status_code != 200:
        logger.error(f"TTS.ai error {resp.status_code} for voice={_voice_for_lang(ui_lang)!r}: {resp.text[:300]}")
        return False, "Text-to-speech failed."

    audio_bytes = resp.content
    if not audio_bytes:
        return False, "Text-to-speech returned empty audio."

    # Some APIs return HTTP 200 with a JSON/text error body instead of a
    # proper error status (e.g. an unknown voice ID). Verify the response
    # actually looks like audio before trusting it — otherwise we'd embed
    # garbage as "audio", the browser would fail to play it, and it would
    # silently fall back to the browser voice with no clue why.
    content_type = resp.headers.get("Content-Type", "")
    looks_like_audio = content_type.startswith("audio/") or audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb"
    if not looks_like_audio:
        logger.error(
            f"TTS.ai returned 200 but non-audio content for voice={_voice_for_lang(ui_lang)!r} "
            f"(Content-Type={content_type!r}): {audio_bytes[:300]!r}"
        )
        return False, f"Text-to-speech returned an unexpected response (voice {_voice_for_lang(ui_lang)!r} may not exist)."

    return True, audio_bytes
