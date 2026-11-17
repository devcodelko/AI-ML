import config


def _post(client, payload, **kwargs):
    return client.post("/chat", json=payload, **kwargs)


def test_missing_message_is_rejected(client, stub_answer):
    response = _post(client, {})
    assert response.status_code == 400
    assert stub_answer == []


def test_blank_message_is_rejected(client, stub_answer):
    assert _post(client, {"message": "   "}).status_code == 400
    assert stub_answer == []


def test_non_string_message_is_rejected(client, stub_answer):
    assert _post(client, {"message": 123}).status_code == 400
    assert _post(client, {"message": ["a"]}).status_code == 400
    assert stub_answer == []


def test_non_json_body_is_rejected(client, stub_answer):
    response = client.post("/chat", data="message=hello", content_type="application/x-www-form-urlencoded")
    assert response.status_code == 400
    response = client.post("/chat", data="[1, 2]", content_type="application/json")
    assert response.status_code == 400
    assert stub_answer == []


def test_message_over_limit_is_rejected(client, stub_answer):
    response = _post(client, {"message": "a" * (config.MAX_MESSAGE_CHARS + 1)})
    assert response.status_code == 400
    assert str(config.MAX_MESSAGE_CHARS) in response.get_json()["error"]
    assert stub_answer == []


def test_message_at_limit_is_accepted(client, stub_answer):
    response = _post(client, {"message": "a" * config.MAX_MESSAGE_CHARS})
    assert response.status_code == 200
    assert response.get_json() == {"answer": "<strong>ok</strong>", "lang": "en"}


def test_oversized_body_returns_400(client, stub_answer):
    response = client.post(
        "/chat",
        data='{"message": "' + "a" * (config.MAX_CONTENT_LENGTH + 10) + '"}',
        content_type="application/json",
    )
    assert response.status_code == 400
    assert stub_answer == []


def test_unknown_lang_falls_back_to_english(client, stub_answer):
    _post(client, {"message": "what is msme", "lang": "fr"})
    assert stub_answer == [("what is msme", "en")]


def test_hindi_lang_is_passed_through(client, stub_answer):
    _post(client, {"message": "msme kya hai", "lang": "hi"})
    assert stub_answer == [("msme kya hai", "hi")]


def test_backend_failure_returns_503_without_leaking_details(client, monkeypatch):
    import rag

    def boom(question, lang="en"):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(rag, "answer_query", boom)
    response = _post(client, {"message": "what is msme"})
    assert response.status_code == 503
    assert "secret" not in response.get_data(as_text=True)


def test_speak_rejects_missing_blank_and_non_string(client, stub_tts):
    assert client.post("/speak", json={}).status_code == 400
    assert client.post("/speak", json={"text": "  "}).status_code == 400
    assert client.post("/speak", json={"text": 5}).status_code == 400
    assert stub_tts == []


def test_speak_rejects_text_over_limit(client, stub_tts):
    response = client.post("/speak", json={"text": "a" * (config.MAX_TTS_CHARS + 1)})
    assert response.status_code == 400
    assert stub_tts == []


def test_speak_accepts_text_at_limit(client, stub_tts):
    response = client.post("/speak", json={"text": "a" * config.MAX_TTS_CHARS, "lang": "hi"})
    assert response.status_code == 200
    assert response.mimetype == "audio/wav"
    assert stub_tts[0][1] == "hi"


def test_speak_unspeakable_text_returns_400(client):
    response = client.post("/speak", json={"text": "<br><br>"})
    assert response.status_code == 400
