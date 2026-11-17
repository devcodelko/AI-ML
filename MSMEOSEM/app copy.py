import os
from flask import Flask, request, jsonify, render_template
import requests
from config import Config

# ------------------------
# Paths setup
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "chatbot", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "chatbot", "static")

# ------------------------
# Initialize Flask app
# ------------------------
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = getattr(app, 'secret_key', Config.SECRET_KEY)

# ------------------------
# Lyzr API Configuration
# ------------------------
LYZR_API_KEY = "sk-default-phYvRzQpPLvim4wIqsurX37KzYBOwKhY"
AGENT_ID = "68ec80bf8d106b3b3abbb277"
LYZR_API_URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"

# ------------------------
# Routes
# ------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/chat", methods=["GET", "POST"])
def chat():
    user_message = ""
    if request.method == "GET":
        user_message = request.args.get("message", "").strip()
        if not user_message:
            return jsonify({"response": "Please provide a 'message' parameter in the URL."}), 400
    else:
        if request.is_json:
            user_message = request.json.get("message", "").strip()
        else:
            user_message = request.form.get("message", "").strip()
        if not user_message:
            return jsonify({"response": "Please enter a message in the request body."}), 400

    payload = {
        "user_id": "harikeshtiwarinaughty@gmail.com",
        "agent_id": AGENT_ID,
        "session_id": f"{AGENT_ID}-session-1",
        "message": user_message
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": LYZR_API_KEY
    }

    try:
        response = requests.post(LYZR_API_URL, json=payload, headers=headers, timeout=90)
        response.raise_for_status()
        res_json = response.json()
        bot_reply = res_json.get("response", "No response from Lyzr.")
    except requests.exceptions.RequestException as e:
        bot_reply = f"Error connecting to Lyzr API: {e}"

    return jsonify({"reply": bot_reply})

if __name__ == "__main__":
    app.run(debug=getattr(Config, "DEBUG", True), port=getattr(Config, "PORT", 5000))
