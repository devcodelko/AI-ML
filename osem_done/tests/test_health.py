def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert isinstance(body["cache_chunks"], int)


def test_health_is_not_rate_limited(client):
    statuses = {client.get("/health").status_code for _ in range(150)}
    assert statuses == {200}
