import base64
import datetime
import os
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import logger, FLASK_PORT
import conversation
import speech
import tts

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)


@app.route("/")
def home():
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    return (
        "<h2>Rozzgaar.in Assistant — Register / Courses / Bundles / Contact</h2>"
        "<p>POST <code>/chat</code> with "
        "<code>{\"message\": \"...\", \"session_id\": \"...\"}</code></p>"
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "version": "rozzgaar-bot-2.0",
        "timestamp": datetime.datetime.now().isoformat(),
    })


@app.route("/transcribe", methods=["POST"])
def transcribe():
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No audio file received."}), 400

    ui_lang = str(request.form.get("language", "")).strip()
    file_bytes = audio_file.read()

    ok, result = speech.transcribe_audio(
        file_bytes=file_bytes,
        filename=audio_file.filename or "audio.webm",
        mimetype=audio_file.mimetype or "audio/webm",
        ui_lang=ui_lang,
    )

    if not ok:
        # 503 tells the frontend this is a config/service issue so it can
        # gracefully fall back to browser-native speech recognition instead
        # of showing a scary error to the user.
        return jsonify({"error": result}), 503

    return jsonify({"text": result})


def _attach_audio(result: Dict[str, Any], ui_lang: str) -> Dict[str, Any]:
    """Best-effort: adds a base64 audio data URI for result['reply'] via
    TTS.ai. Never raises — if TTS fails or isn't configured, the response
    is returned unchanged (frontend falls back to the browser voice)."""
    reply_text = str(result.get("reply", "")).strip()
    if not reply_text:
        return result
    try:
        ok, data = tts.synthesize_speech(reply_text, ui_lang=ui_lang)
        if ok:
            b64 = base64.b64encode(data).decode("ascii")
            result["audio"] = f"data:audio/mp3;base64,{b64}"
            logger.info(f"[TTS] ok: lang={ui_lang} bytes={len(data)}")
        else:
            logger.info(f"[TTS] skipped: lang={ui_lang} reason={data}")
    except Exception:
        logger.exception("Unexpected error generating TTS audio")
    return result


@app.route("/chat", methods=["POST"])
def chat():
    try:
        body = request.get_json(silent=True) or {}
        user_input = str(body.get("message", "")).strip()
        session_id = str(body.get("session_id", "default"))

        if not user_input:
            return jsonify({"reply": "Please type a message.", "type": "error"}), 400

        sess = conversation._session(session_id)
        upper = user_input.upper()

        # ── Language selection (always allowed, resets the conversation) ──
        if upper.startswith("__SET_LANG__:"):
            lang = user_input.split(":", 1)[1].strip().lower()
            if lang not in ("en", "hi"):
                lang = "en"
            result = conversation.start_flow(session_id, lang)
            logger.info(f"[LANG] session={session_id} -> {lang}")
            result = _attach_audio(result, lang)
            return jsonify(result)

        # ── Language gate: nothing works until a language is chosen ──
        if not sess.get("lang"):
            return jsonify({
                "reply": conversation.LANG_GATE_TEXT,
                "type": "language_select",
                "options": conversation.LANG_OPTIONS,
            })

        result = conversation.handle_message(session_id, user_input)
        logger.info(f"[CHAT] session={session_id} | type={result.get('type')}")
        result = _attach_audio(result, sess.get("lang") or "en")
        return jsonify(result)

    except Exception as e:
        logger.exception("Unhandled error in /chat")
        return jsonify({
            "reply": "Internal server error. Please check server logs. / सर्वर में त्रुटि हुई।",
            "error": str(e),
        }), 500


if __name__ == "__main__":
    print("=" * 60)
    print("  Rozzgaar.in Register / OTP / Login Assistant")
    print(f"  URL   : http://127.0.0.1:{FLASK_PORT}")
    print("  Endpoints:")
    print("    POST /chat")
    print("    GET  /health")
    print("=" * 60)
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=True)
