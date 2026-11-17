import re


def test_api_responses_carry_security_headers(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_csp_nonce_matches_inline_tags_in_page(client):
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    nonce = re.search(r"script-src 'self' 'nonce-([^']+)'", csp).group(1)
    assert f"style-src 'self' 'nonce-{nonce}'" in csp
    html = response.get_data(as_text=True)
    assert f'<script nonce="{nonce}">' in html
    assert f'<style nonce="{nonce}">' in html


def test_nonce_changes_between_requests(client):
    first = client.get("/").headers["Content-Security-Policy"]
    second = client.get("/").headers["Content-Security-Policy"]
    assert first != second


def test_error_responses_also_carry_headers(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_only_on_https(client):
    assert "Strict-Transport-Security" not in client.get("/health").headers
    secure = client.get("/health", base_url="https://localhost")
    assert "Strict-Transport-Security" in secure.headers


def test_page_limits_input_length(client):
    assert 'maxlength="500"' in client.get("/").get_data(as_text=True)
