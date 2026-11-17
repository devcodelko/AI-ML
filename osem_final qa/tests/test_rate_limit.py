import app as app_module


def _fresh_client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_chat_is_limited_to_20_per_minute(stub_answer):
    client = _fresh_client()
    statuses = [client.post("/chat", json={"message": "what is msme"}).status_code for _ in range(21)]
    assert statuses[:20] == [200] * 20
    assert statuses[20] == 429


def test_rate_limit_response_is_json(stub_answer):
    client = _fresh_client()
    for _ in range(20):
        client.post("/chat", json={"message": "what is msme"})
    response = client.post("/chat", json={"message": "what is msme"})
    assert response.status_code == 429
    assert "error" in response.get_json()


def test_speak_has_its_own_limit(stub_tts):
    client = _fresh_client()
    statuses = [client.post("/speak", json={"text": "hello"}).status_code for _ in range(61)]
    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429


def test_chat_limit_does_not_consume_speak_budget(stub_answer, stub_tts):
    client = _fresh_client()
    for _ in range(21):
        client.post("/chat", json={"message": "what is msme"})
    assert client.post("/speak", json={"text": "hello"}).status_code == 200
