import os
import sys

os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import app as app_module  # noqa: E402
import rag  # noqa: E402
import tts  # noqa: E402


@pytest.fixture
def app():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def stub_answer(monkeypatch):
    calls = []

    def fake_answer_query(question, lang="en"):
        calls.append((question, lang))
        return "<strong>ok</strong>", lang

    monkeypatch.setattr(rag, "answer_query", fake_answer_query)
    return calls


@pytest.fixture
def stub_tts(monkeypatch):
    calls = []

    def fake_synthesize(text, lang):
        calls.append((text, lang))
        return b"RIFFfake", "audio/wav"

    monkeypatch.setattr(tts, "synthesize_speech", fake_synthesize)
    return calls
