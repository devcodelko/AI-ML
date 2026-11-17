import base64
import io
import wave

import config
import http_utils

_session = http_utils.build_session(config.HTTP_MAX_RETRIES)

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiUnavailableError(RuntimeError):
    """Raised when Gemini cannot serve requests at all (missing/invalid key, forbidden, quota)."""

# Gemini's TTS model follows a natural-language style instruction placed in
# front of the text it is asked to read (it speaks the instruction's intent,
# not the instruction itself). We use this to force a clear, natural Indian
# accent in both languages instead of leaving the accent to chance.
_ACCENT_INSTRUCTION_EN = (
    "Speak the following in a warm, clear, natural Indian English accent, "
    "at a calm and easy-to-follow pace, the way a helpful Indian government "
    "helpdesk officer would speak. Pronounce every word clearly: "
)
_ACCENT_INSTRUCTION_HI = (
    "निम्नलिखित को स्पष्ट, शुद्ध और सरल भारतीय हिंदी उच्चारण में, शांत और समझने में आसान गति से, "
    "एक सहायक भारतीय सरकारी हेल्पडेस्क अधिकारी की तरह बोलें: "
)


def _pcm_to_wav(pcm_bytes, channels=1, sample_rate=24000, sample_width=2):
    """Gemini's TTS API returns raw 16-bit PCM audio; wrap it in a playable WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    buffer.seek(0)
    return buffer.read()


def generate_answer(system_prompt, question, max_output_tokens=1800):
    """Fallback chat answer using Gemini, used when the Groq API is rate-limited or unavailable."""
    if not config.GEMINI_API_KEY:
        raise GeminiUnavailableError("Gemini API key is not configured")
    url = GEMINI_URL_TEMPLATE.format(model=config.GEMINI_TEXT_MODEL)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": int(max_output_tokens),
            # Gemini 2.5 Flash counts internal "thinking" tokens against maxOutputTokens,
            # which silently truncates visible answers. Disable thinking for this fallback.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    response = _session.post(
        url,
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=(config.HTTP_CONNECT_TIMEOUT, config.GEMINI_TEXT_READ_TIMEOUT),
    )
    response.raise_for_status()
    data = response.json()
    parts = data["candidates"][0]["content"]["parts"]
    answer = "".join(part.get("text", "") for part in parts).strip()
    if not answer:
        raise RuntimeError("Gemini returned an empty answer")
    return answer


def _request_speech_once(display_text, spoken_text, voice_name):
    url = GEMINI_URL_TEMPLATE.format(model=config.GEMINI_TTS_MODEL)
    payload = {
        "contents": [{"parts": [{"text": spoken_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            # Gemini's TTS models are known to silently cut audio short for longer
            # text unless given a generous output budget - set it explicitly high.
            "maxOutputTokens": 8000,
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}
            },
        },
    }
    if not config.GEMINI_API_KEY:
        raise GeminiUnavailableError("Gemini API key is not configured")
    response = _session.post(
        url,
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=(config.HTTP_CONNECT_TIMEOUT, config.GEMINI_TTS_READ_TIMEOUT),
    )
    if response.status_code in (401, 403, 429):
        raise GeminiUnavailableError(
            f"{response.status_code} Client Error for url: {url}"
        )
    response.raise_for_status()
    data = response.json()
    candidate = data["candidates"][0]
    finish_reason = candidate.get("finishReason", "STOP")
    inline_data = candidate["content"]["parts"][0].get("inlineData")
    if not inline_data or not inline_data.get("data"):
        raise RuntimeError(f"Gemini TTS returned no audio (finishReason={finish_reason})")
    pcm_bytes = base64.b64decode(inline_data["data"])

    # Gemini TTS is known to occasionally cut audio short even on a normal 200
    # response with no error. Sanity-check the audio length against the text
    # length (24kHz, 16-bit, mono = 48000 bytes/second) and treat clearly
    # short/incomplete audio as a failure so the caller retries or falls back.
    # The duration check uses only display_text (the real content the user
    # will hear), not the accent instruction prefixed onto spoken_text.
    actual_seconds = len(pcm_bytes) / 48000
    expected_min_seconds = max(0.6, len(display_text) / 40)
    if finish_reason not in ("STOP", None) or actual_seconds < expected_min_seconds:
        raise RuntimeError(
            f"Gemini TTS audio looks truncated (finishReason={finish_reason}, "
            f"{actual_seconds:.1f}s audio for {len(display_text)} chars of text)"
        )
    return pcm_bytes


def synthesize_speech(text, lang="en", voice_name=None):
    """Generate clear speech audio with Gemini's TTS model, steered into a clear
    Indian accent for both English and Hindi. Returns (wav_bytes, mimetype).
    Retries once, since Gemini's TTS occasionally truncates audio on the first try.
    """
    voice_name = voice_name or config.GEMINI_TTS_VOICE
    accent_instruction = _ACCENT_INSTRUCTION_HI if lang == "hi" else _ACCENT_INSTRUCTION_EN
    spoken_text = f"{accent_instruction}{text}"
    last_error = None
    for attempt in range(2):
        try:
            pcm_bytes = _request_speech_once(text, spoken_text, voice_name)
            return _pcm_to_wav(pcm_bytes), "audio/wav"
        except GeminiUnavailableError:
            raise
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Gemini TTS failed after retries: {last_error}")
