import logging
import os
import secrets
import sys

from flask import Flask, Response, g, jsonify, render_template, request, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

import config
import crawler
import rag
import tts

logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _normalize_lang(value):
    lang = value.strip().lower() if isinstance(value, str) else "en"
    return lang if lang in ("en", "hi") else "en"


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _content_security_policy(nonce):
    frame_ancestors = config.FRAME_ANCESTORS or "'none'"
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            f"style-src 'self' 'nonce-{nonce}'",
            "img-src 'self' data:",
            "media-src 'self' blob:",
            "connect-src 'self'",
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            f"frame-ancestors {frame_ancestors}",
        ]
    )


def create_app():
    config.validate()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.json.ensure_ascii = False

    if config.TRUSTED_PROXIES > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=config.TRUSTED_PROXIES,
            x_proto=config.TRUSTED_PROXIES,
            x_host=0,
            x_prefix=0,
        )

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[config.DEFAULT_RATE_LIMIT],
        storage_uri=config.RATELIMIT_STORAGE_URI,
        headers_enabled=True,
        swallow_errors=True,
        in_memory_fallback_enabled=True,
    )

    @app.before_request
    def _set_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_nonce():
        return {"csp_nonce": g.get("csp_nonce", "")}

    @app.after_request
    def _security_headers(response):
        nonce = g.get("csp_nonce", "")
        response.headers["Content-Security-Policy"] = _content_security_policy(nonce)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not config.FRAME_ANCESTORS:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=(), microphone=(self)"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.errorhandler(413)
    def _too_large(_error):
        return jsonify({"error": "Request body is too large."}), 400

    @app.errorhandler(429)
    def _rate_limited(_error):
        return jsonify({"error": "Too many requests. Please wait a moment and try again."}), 429

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/logo.jpg")
    def logo():
        return send_file(os.path.join(app.root_path, "logo.jpg"), mimetype="image/jpeg", max_age=3600)

    @app.route("/health")
    @limiter.exempt
    def health():
        return jsonify({"status": "ok", "cache_chunks": len(crawler.load_chunk_cache(config.CACHE_PATH))})

    @app.route("/chat", methods=["POST"])
    @limiter.limit(config.CHAT_RATE_LIMIT)
    def chat():
        data = _json_body()
        if data is None:
            return jsonify({"error": "A JSON object body is required."}), 400
        message = data.get("message")
        if message is None:
            return jsonify({"error": "message is required"}), 400
        if not isinstance(message, str):
            return jsonify({"error": "message must be a string"}), 400
        question = message.strip()
        if not question:
            return jsonify({"error": "message is required"}), 400
        if len(question) > config.MAX_MESSAGE_CHARS:
            return jsonify({"error": f"message must be at most {config.MAX_MESSAGE_CHARS} characters"}), 400
        lang = _normalize_lang(data.get("lang"))
        try:
            answer, effective_lang = rag.answer_query(question, lang=lang)
        except Exception:
            logger.exception("Failed to answer a chat request")
            return jsonify({"error": "The assistant is temporarily unavailable. Please try again."}), 503
        return jsonify({"answer": answer, "lang": effective_lang})

    @app.route("/speak", methods=["POST"])
    @limiter.limit(config.SPEAK_RATE_LIMIT)
    def speak():
        data = _json_body()
        if data is None:
            return jsonify({"error": "A JSON object body is required."}), 400
        raw_text = data.get("text")
        if raw_text is None:
            return jsonify({"error": "text is required"}), 400
        if not isinstance(raw_text, str):
            return jsonify({"error": "text must be a string"}), 400
        text = raw_text.strip()
        if not text:
            return jsonify({"error": "text is required"}), 400
        if len(text) > config.MAX_TTS_CHARS:
            return jsonify({"error": f"text must be at most {config.MAX_TTS_CHARS} characters"}), 400
        lang = _normalize_lang(data.get("lang"))
        try:
            audio_bytes, mimetype = tts.synthesize_speech(text, lang)
        except ValueError:
            return jsonify({"error": "No speakable text provided"}), 400
        except Exception:
            logger.exception("Failed to synthesize speech for lang=%r", lang)
            return jsonify({"error": "Could not generate audio right now. Please try again."}), 503
        return Response(audio_bytes, mimetype=mimetype)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT") or 5000), debug=False, use_reloader=False, threaded=True)
