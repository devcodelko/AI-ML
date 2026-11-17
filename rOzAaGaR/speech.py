"""
speech.py
─────────────────────────────────────────────────────────────
Server-side speech-to-text using Groq's hosted Whisper model.

Browser-native speech recognition (webkitSpeechRecognition) is
inconsistent — it clips quiet words, mishears Hindi/English
code-switched speech, and silently drops low-confidence audio.
Whisper (run here via Groq) transcribes the *actual recorded
audio*, so it handles soft speech, accents, and Hindi-English
mixing far more reliably.

transcribe_audio() returns (ok: bool, text_or_error: str).
"""

from typing import Tuple

import requests

from config import logger, GROQ_API_KEY, GROQ_STT_URL, GROQ_STT_MODEL, STT_TIMEOUT

# Maps our UI language codes to a Whisper ISO-639-1 language hint.
# Passing the hint (rather than leaving it to auto-detect) noticeably
# improves accuracy for short utterances.
_LANG_HINT = {"en": "en", "hi": "hi"}


def transcribe_audio(file_bytes: bytes, filename: str, mimetype: str, ui_lang: str = "") -> Tuple[bool, str]:
    if not GROQ_API_KEY:
        return False, "Speech-to-text is not configured on the server."

    if not file_bytes:
        return False, "Empty audio."

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    data = {
        "model": GROQ_STT_MODEL,
        "response_format": "json",
        "temperature": "0",
    }
    lang_hint = _LANG_HINT.get((ui_lang or "").lower())
    if lang_hint:
        data["language"] = lang_hint

    files = {"file": (filename or "audio.webm", file_bytes, mimetype or "audio/webm")}

    try:
        resp = requests.post(
            GROQ_STT_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=STT_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.exception("Groq STT request failed")
        return False, f"Speech service unreachable: {e}"

    if resp.status_code != 200:
        logger.error(f"Groq STT error {resp.status_code}: {resp.text[:300]}")
        return False, "Speech-to-text failed, please try again."

    try:
        payload = resp.json()
    except ValueError:
        return False, "Speech-to-text returned an invalid response."

    text = (payload.get("text") or "").strip()
    if not text:
        return False, ""

    return True, text
