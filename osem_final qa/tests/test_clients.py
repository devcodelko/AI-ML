import config
import gemini_client
import groq_client
import tts


def test_groq_client_has_timeout_and_retries(monkeypatch):
    monkeypatch.setattr(groq_client, "_client", None)
    client = groq_client.get_client()
    assert client.max_retries == config.GROQ_MAX_RETRIES
    assert client.timeout == config.GROQ_TIMEOUT
    monkeypatch.setattr(groq_client, "_client", None)


def test_gemini_fallback_uses_groq_sized_token_budget(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(gemini_client._session, "post", fake_post)
    assert gemini_client.generate_answer("system", "question", max_output_tokens=1800) == "answer"
    assert captured["payload"]["generationConfig"]["maxOutputTokens"] == 1800
    assert isinstance(captured["timeout"], tuple) and len(captured["timeout"]) == 2


def test_groq_failure_falls_back_to_gemini_with_matching_budget(monkeypatch):
    seen = {}

    class FailingCompletions:
        def create(self, **kwargs):
            raise RuntimeError("rate limited")

    class FakeClient:
        class chat:
            completions = FailingCompletions()

    def fake_gemini(system_prompt, question, max_output_tokens=0):
        seen["tokens"] = max_output_tokens
        return "<strong>fallback</strong>"

    monkeypatch.setattr(groq_client, "get_client", lambda: FakeClient())
    monkeypatch.setattr(groq_client.gemini_client, "generate_answer", fake_gemini)
    answer, tokens = groq_client.generate_answer("what is msme", [{"url": "u", "text": "t"}], "en")
    assert "fallback" in answer
    assert tokens == 0
    assert seen["tokens"] >= 1800


def test_gtts_is_called_with_timeout_and_retried(monkeypatch):
    attempts = []

    class FakeGTTS:
        def __init__(self, text, lang, tld, timeout):
            attempts.append(timeout)

        def write_to_fp(self, buffer):
            if len(attempts) < 2:
                raise RuntimeError("network")
            buffer.write(b"mp3")

    monkeypatch.setattr(tts, "gTTS", FakeGTTS)
    monkeypatch.setattr(tts.time, "sleep", lambda seconds: None)
    audio, mimetype = tts._gtts_speech("hello", "en")
    assert audio == b"mp3"
    assert mimetype == "audio/mpeg"
    assert attempts == [config.GTTS_TIMEOUT, config.GTTS_TIMEOUT]


def test_gtts_gives_up_after_bounded_retries(monkeypatch):
    attempts = []

    class AlwaysFails:
        def __init__(self, text, lang, tld, timeout):
            attempts.append(1)

        def write_to_fp(self, buffer):
            raise RuntimeError("down")

    monkeypatch.setattr(tts, "gTTS", AlwaysFails)
    monkeypatch.setattr(tts.time, "sleep", lambda seconds: None)
    try:
        tts._gtts_speech("hello", "en")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")
    assert len(attempts) == config.GTTS_MAX_RETRIES + 1
