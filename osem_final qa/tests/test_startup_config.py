import pytest

import app as app_module
import config


def test_missing_keys_fail_at_startup(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError) as excinfo:
        app_module.create_app()
    message = str(excinfo.value)
    assert "GROQ_API_KEY" in message
    assert "GEMINI_API_KEY" in message
    assert ".env.example" in message


def test_single_missing_key_is_named(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError) as excinfo:
        config.validate()
    assert "GEMINI_API_KEY" in str(excinfo.value)
    assert "GROQ_API_KEY" not in str(excinfo.value)


def test_valid_keys_pass():
    config.validate()
