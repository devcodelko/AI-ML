"""
conversation.py
─────────────────────────────────────────────────────────────
Step-by-step bilingual (English / Hindi) chat flow:

  LANGUAGE GATE -> "Are you interested to register?" (Yes/No)

  YES -> salutation -> name -> mobile -> email -> state ->
         district -> password -> referral code -> terms ->
         confirm -> POST /auth/register (sends OTP to email +
         mobile, returns verification_id) -> ask user for the
         OTP -> POST /auth/verify-otp -> on success, show
         mobile + password credentials and the
         https://rozzgaar.in/login link -> HELP HUB

  NO  -> HELP HUB directly

  HELP HUB: free-text or button driven Q&A backed by:
         GET /courses            (course list)
         GET /courses/{slug}     (course detail)
         GET /courses/bundles    (bundle list)
         GET /courses/bundles/{slug} (bundle detail)
         POST /misc/contact      (contact form)
         "About Us" is static content (no API for this).

All state lives in-memory per session_id.
"""

import datetime
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

import api_client
from config import logger, SIGNUP_LOG_FILE, ROZZGAAR_LOGIN_URL
from normalize import normalize_email, normalize_mobile

_SESSIONS: Dict[str, Dict[str, Any]] = {}
_signup_log_lock = threading.Lock()


def T(bundle: Dict[str, str], lang: str, **kwargs) -> str:
    text = bundle.get(lang) or bundle.get("en") or ""
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def _session(session_id: str) -> Dict[str, Any]:
    return _SESSIONS.setdefault(session_id, {"lang": None, "step": "interest_ask", "data": {}})


def reset_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


# ─────────────────────────────────────────────
# STATIC TEXT
# ─────────────────────────────────────────────
LANG_GATE_TEXT = "Please select your language / कृपया अपनी भाषा चुनें"
LANG_OPTIONS = [
    {"label": "English", "value": "__SET_LANG__:en"},
    {"label": "हिंदी (Hindi)", "value": "__SET_LANG__:hi"},
]

INTEREST_PROMPT = {
    "en": "Welcome to Rozzgaar! 👋",
    "hi": "Welcome to Rozzgaar! 👋",
}
INTEREST_OPTIONS = {
    "en": [
        {"label": "📝 Register", "value": "__WELCOME__:register"},
        {"label": "🔐 Login", "value": "__WELCOME__:login"},
        {"label": "🔎 Explore", "value": "__WELCOME__:explore"},
    ],
    "hi": [
        {"label": "📝 Register", "value": "__WELCOME__:register"},
        {"label": "🔐 Login", "value": "__WELCOME__:login"},
        {"label": "🔎 Explore", "value": "__WELCOME__:explore"},
    ],
}
LOGIN_WORDS = {"login", "log in", "sign in", "लॉगिन", "लॉग इन", "साइन इन"}
EXPLORE_WORDS = {"explore", "browse", "एक्सप्लोर", "देखें"}

HUB_PROMPT = {
    "en": "Okay! How can I help you? Ask me about our Courses, Course Bundles, About Us, or Contact Us. 😊",
    "hi": "ठीक है! मैं आपकी कैसे मदद कर सकता हूँ? आप हमारे Courses, Course Bundles, About Us, या Contact Us के बारे में पूछ सकते हैं। 😊",
}
HUB_OPTIONS = {
    "en": [
        {"label": "📚 Courses", "value": "__HUB__:courses"},
        {"label": "🎁 Course Bundles", "value": "__HUB__:bundles"},
        {"label": "ℹ️ About Us", "value": "__HUB__:about"},
        {"label": "📞 Contact Us", "value": "__HUB__:contact"},
    ],
    "hi": [
        {"label": "📚 कोर्सेज़", "value": "__HUB__:courses"},
        {"label": "🎁 कोर्स बंडल", "value": "__HUB__:bundles"},
        {"label": "ℹ️ हमारे बारे में", "value": "__HUB__:about"},
        {"label": "📞 संपर्क करें", "value": "__HUB__:contact"},
    ],
}

ABOUT_TEXT = {
    "en": (
        "Rozzgaar is an online skill-development and career platform. "
        "We offer certified, practical courses in digital marketing, entrepreneurship, "
        "and other in-demand skills to help you learn and grow your career."
    ),
    "hi": (
        "Rozzgaar एक ऑनलाइन स्किल-डेवलपमेंट और करियर प्लेटफ़ॉर्म है। "
        "हम डिजिटल मार्केटिंग, entrepreneurship और अन्य जरूरी स्किल्स में प्रमाणित, "
        "प्रैक्टिकल कोर्स देते हैं ताकि आप सीखें और अपना करियर आगे बढ़ाएं।"
    ),
}

SALUTATIONS = ["Mr", "Mrs", "Ms", "Dr"]

CANCEL_WORDS = {
    "cancel", "stop", "exit", "quit", "start over", "restart",
    "रद्द", "रद्द करो", "बंद करो", "रुको", "फिर से शुरू", "शुरू से",
}
YES_WORDS = {"yes", "yeah", "yep", "haan", "ha", "sure", "yup", "y", "हाँ", "हां", "है"}
NO_WORDS = {"no", "nahi", "nope", "n", "नहीं", "नही"}

COURSE_KEYWORDS = {"course", "courses", "class", "classes", "कोर्स", "कोर्सेज़", "क्लास"}
BUNDLE_KEYWORDS = {"bundle", "bundles", "package", "packages", "combo", "बंडल", "पैकेज"}
ABOUT_KEYWORDS = {"about", "rozzgaar", "who are you", "company", "बारे में", "के बारे", "कंपनी"}
CONTACT_KEYWORDS = {"contact", "support", "help desk", "reach", "email us", "call", "संपर्क", "कॉन्टेक्ट", "सहायता"}

# Phrases that mean "how many courses does this bundle contain?"
COUNT_KEYWORDS = {
    "how many course", "how many courses", "number of course", "number of courses",
    "total course", "total courses", "courses included", "courses in this",
    "courses in the bundle", "courses does it have", "courses are there",
    "कितने कोर्स", "कोर्स की संख्या", "कुल कोर्स", "इसमें कितने कोर्स",
}

# Words that ask specifically to register / enroll for whatever was just shown
REGISTER_INTENT_WORDS = {
    "register", "enroll", "enrol", "sign up", "signup", "join", "buy", "admission",
    "रजिस्टर", "एनरोल", "दाखिला", "ज्वाइन",
}


# ─────────────────────────────────────────────
# ENTRY POINTS (called from app.py)
# ─────────────────────────────────────────────
def start_flow(session_id: str, lang: str) -> Dict[str, Any]:
    sess = _session(session_id)
    sess["lang"] = lang
    sess["step"] = "interest_ask"
    sess["data"] = {}
    return {"reply": T(INTEREST_PROMPT, lang), "type": "interest_ask", "options": INTEREST_OPTIONS[lang]}


def handle_message(session_id: str, user_input: str) -> Dict[str, Any]:
    sess = _session(session_id)
    lang = sess.get("lang") or "en"
    text = user_input.strip()
    norm = text.lower().rstrip(".!।")

    if norm in CANCEL_WORDS:
        registered_data = sess.get("_registered_data")
        reset_session(session_id)
        msg = {
            "en": "Okay, I've cancelled that. Say 'hi' anytime to start again.",
            "hi": "ठीक है, मैंने इसे रद्द कर दिया है। दोबारा शुरू करने के लिए कभी भी 'hi' लिखें।",
        }
        return {"reply": T(msg, lang), "type": "cancelled"}

    step = sess.get("step", "interest_ask")

    if step == "interest_ask":
        return _handle_interest(session_id, sess, text)

    if step.startswith("reg_"):
        return _handle_register_step(session_id, sess, text)

    if step == "help_hub":
        return _handle_hub(session_id, sess, text)

    if step.startswith("contact_"):
        return _handle_contact_step(session_id, sess, text)

    # Fallback: session got into an unknown state -> restart.
    return start_flow(session_id, lang)


# ─────────────────────────────────────────────
# INTEREST GATE (Register / Login / Explore)
# ─────────────────────────────────────────────
def _handle_interest(session_id: str, sess: Dict[str, Any], text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    norm = text.strip().lower()

    if norm.startswith("__welcome__:"):
        choice = norm.split(":", 1)[1]
    elif norm in LOGIN_WORDS or "login" in norm or "log in" in norm or "sign in" in norm:
        choice = "login"
    elif norm in EXPLORE_WORDS or norm in NO_WORDS or "explore" in norm or "no" in norm:
        choice = "explore"
    elif norm in YES_WORDS or "yes" in norm or any(w in norm for w in REGISTER_INTENT_WORDS):
        choice = "register"
    else:
        return {"reply": T(INTEREST_PROMPT, lang), "type": "interest_ask", "options": INTEREST_OPTIONS[lang]}

    if choice == "register":
        return _start_register(session_id, sess)
    if choice == "login":
        return _show_login_link(sess)
    return _go_to_hub(sess)


def _show_login_link(sess: Dict[str, Any]) -> Dict[str, Any]:
    lang = sess["lang"]
    msg = {
        "en": "Tap the button below to go straight to the Rozzgaar login page.",
        "hi": "कोई बात नहीं! नीचे दिए बटन पर टैप करें और सीधे Rozzgaar के लॉगिन पेज पर जाएं।",
    }
    login_label = {"en": "🔐 Login to Rozzgaar", "hi": "🔐 Rozzgaar पर लॉगिन करें"}
    login_button = {"label": T(login_label, lang), "value": f"__OPEN_LINK__:{ROZZGAAR_LOGIN_URL}"}
    return {"reply": T(msg, lang), "type": "login_link", "options": [login_button]}


def _go_to_hub(sess: Dict[str, Any]) -> Dict[str, Any]:
    lang = sess["lang"]
    sess["step"] = "help_hub"
    sess["data"] = {}
    return {"reply": T(HUB_PROMPT, lang), "type": "help_hub", "options": HUB_OPTIONS[lang]}


# ─────────────────────────────────────────────
# REGISTRATION FLOW (no OTP)
# ─────────────────────────────────────────────
_REG_PROMPTS = {
    "reg_salutation": {
        "en": "Let's create your account. First, how should we address you?",
        "hi": "चलिए आपका अकाउंट बनाते हैं। सबसे पहले बताइए, हम आपको कैसे संबोधित करें?",
    },
    "reg_name": {
        "en": "What is your full name?",
        "hi": "आपका पूरा नाम क्या है?",
    },
    "reg_mobile": {
        "en": "Thanks, {name}! What's your 10-digit mobile number?",
        "hi": "धन्यवाद, {name}! आपका 10 अंकों का मोबाइल नंबर क्या है?",
    },
    "reg_email": {
        "en": "What's your email address? You can say it like 'name AT gmail DOT com', or just type it.",
        "hi": "आपका ईमेल एड्रेस क्या है? आप बोल सकते हैं जैसे 'name एट जीमेल डॉट कॉम', या टाइप कर सकते हैं।",
    },
    "reg_state": {
        "en": "Which state are you from?",
        "hi": "आप किस राज्य से हैं?",
    },
    "reg_district": {
        "en": "And which district in {state}?",
        "hi": "और {state} में कौन सा जिला?",
    },
    "reg_password": {
        "en": "Now please set a password for your account (minimum 6 characters). For safety, please type it instead of speaking it out loud.",
        "hi": "अब कृपया अपने अकाउंट के लिए एक पासवर्ड सेट करें (कम से कम 6 अक्षर)। सुरक्षा के लिए इसे बोलने की बजाय टाइप करें।",
    },
    "reg_referral_ask": {
        "en": "Do you have a referral code? (optional)",
        "hi": "क्या आपके पास कोई रेफरल कोड है? (यह वैकल्पिक है)",
    },
    "reg_referral_code": {
        "en": "Please enter your referral code.",
        "hi": "कृपया अपना रेफरल कोड बताएं।",
    },
    "reg_terms": {
        "en": (
            "Last step — do you agree to our Terms & Conditions, Privacy Policy, "
            "and Refund & Cancellation Policy? (yes/no)"
        ),
        "hi": (
            "आखिरी कदम — क्या आप हमारी नियम व शर्तें, प्राइवेसी पॉलिसी, और रिफंड व "
            "कैंसिलेशन पॉलिसी से सहमत हैं? (हाँ/नहीं)"
        ),
    },
}


def _start_register(session_id: str, sess: Dict[str, Any], pending: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    lang = sess["lang"]
    sess["step"] = "reg_salutation"
    sess["data"] = {}
    if pending:
        sess["_pending_item"] = pending
    intro = ""
    if pending and pending.get("title"):
        intro_msg = {
            "en": f"Great choice — let's get you registered for \"{pending['title']}\". ",
            "hi": f"बढ़िया — चलिए \"{pending['title']}\" के लिए आपका रजिस्ट्रेशन करते हैं। ",
        }
        intro = T(intro_msg, lang)
    return {
        "reply": intro + T(_REG_PROMPTS["reg_salutation"], lang),
        "type": "reg_salutation",
        "options": [{"label": s, "value": s} for s in SALUTATIONS],
    }


def _handle_register_step(session_id: str, sess: Dict[str, Any], text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    step = sess["step"]
    data = sess["data"]

    if step == "reg_salutation":
        val = text.strip().rstrip(".")
        matched = next((s for s in SALUTATIONS if s.lower() == val.lower()), None)
        if not matched:
            return {
                "reply": T(_REG_PROMPTS["reg_salutation"], lang),
                "type": "reg_salutation",
                "options": [{"label": s, "value": s} for s in SALUTATIONS],
            }
        data["salutation"] = matched
        sess["step"] = "reg_name"
        return {"reply": T(_REG_PROMPTS["reg_name"], lang), "type": "reg_name"}

    if step == "reg_name":
        cleaned = text.strip()
        if len(cleaned) < 2:
            msg = {"en": "That doesn't look like a valid name, please try again.",
                   "hi": "यह सही नाम नहीं लग रहा, कृपया दोबारा बताएं।"}
            return {"reply": T(msg, lang), "type": "reg_name"}
        data["name"] = cleaned
        sess["step"] = "reg_mobile"
        return {"reply": T(_REG_PROMPTS["reg_mobile"], lang, name=cleaned), "type": "reg_mobile"}

    if step == "reg_mobile":
        ok, value = normalize_mobile(text)
        if not ok:
            return {"reply": value, "type": "reg_mobile"}
        data["mobile"] = value
        sess["step"] = "reg_email"
        return {"reply": T(_REG_PROMPTS["reg_email"], lang), "type": "reg_email"}

    if step == "reg_email":
        ok, value = normalize_email(text)
        if not ok:
            return {"reply": value, "type": "reg_email"}
        data["email"] = value
        sess["step"] = "reg_state"
        ok_api, states, _status = api_client.get_states()
        sess["_states_cache"] = states if ok_api and states else []
        if sess["_states_cache"]:
            return {
                "reply": T(_REG_PROMPTS["reg_state"], lang),
                "type": "reg_state",
                "options": [{"label": s, "value": s} for s in sess["_states_cache"]],
            }
        return {"reply": T(_REG_PROMPTS["reg_state"], lang), "type": "reg_state"}

    if step == "reg_state":
        cleaned = text.strip()
        cache = sess.get("_states_cache") or []
        if cache:
            matched = next((s for s in cache if s.lower() == cleaned.lower()), None)
            if not matched:
                msg = {"en": "Please choose a valid state from the list.",
                       "hi": "कृपया सूची में से एक सही राज्य चुनें।"}
                return {
                    "reply": T(msg, lang), "type": "reg_state",
                    "options": [{"label": s, "value": s} for s in cache],
                }
            cleaned = matched
        if len(cleaned) < 2:
            msg = {"en": "Please tell me your state again.", "hi": "कृपया अपना राज्य दोबारा बताएं।"}
            return {"reply": T(msg, lang), "type": "reg_state"}
        data["state"] = cleaned.title()
        sess["step"] = "reg_district"
        ok_api, districts, _status = api_client.get_districts(data["state"])
        sess["_districts_cache"] = districts if ok_api and districts else []
        prompt = T(_REG_PROMPTS["reg_district"], lang, state=data["state"])
        if sess["_districts_cache"]:
            return {
                "reply": prompt, "type": "reg_district",
                "options": [{"label": d, "value": d} for d in sess["_districts_cache"]],
            }
        return {"reply": prompt, "type": "reg_district"}

    if step == "reg_district":
        cleaned = text.strip()
        cache = sess.get("_districts_cache") or []
        if cache:
            matched = next((d for d in cache if d.lower() == cleaned.lower()), None)
            if matched:
                cleaned = matched
        if len(cleaned) < 2:
            msg = {"en": "Please tell me your district again.", "hi": "कृपया अपना जिला दोबारा बताएं।"}
            return {"reply": T(msg, lang), "type": "reg_district"}
        data["district"] = cleaned.title()
        sess["step"] = "reg_password"
        return {"reply": T(_REG_PROMPTS["reg_password"], lang), "type": "reg_password"}

    if step == "reg_password":
        pw = text.strip()
        if len(pw) < 6:
            msg = {"en": "Password must be at least 6 characters. Please try again.",
                   "hi": "पासवर्ड कम से कम 6 अक्षर का होना चाहिए। कृपया दोबारा कोशिश करें।"}
            return {"reply": T(msg, lang), "type": "reg_password"}
        data["password"] = pw
        sess["step"] = "reg_referral_ask"
        return {
            "reply": T(_REG_PROMPTS["reg_referral_ask"], lang),
            "type": "reg_referral_ask",
            "options": [
                {"label": "Yes" if lang == "en" else "हाँ", "value": "yes"},
                {"label": "No" if lang == "en" else "नहीं", "value": "no"},
            ],
        }

    if step == "reg_referral_ask":
        norm = text.strip().lower()
        if norm in YES_WORDS:
            sess["step"] = "reg_referral_code"
            return {"reply": T(_REG_PROMPTS["reg_referral_code"], lang), "type": "reg_referral_code"}
        data["referral_code"] = ""
        return _go_to_terms(sess, lang)

    if step == "reg_referral_code":
        data["referral_code"] = text.strip()
        return _go_to_terms(sess, lang)

    if step == "reg_terms":
        norm = text.strip().lower()
        if norm in YES_WORDS:
            data["terms_accepted"] = True
            return _register_confirm_summary(sess, lang)
        if norm in NO_WORDS:
            msg = {
                "en": "You need to accept the Terms & Conditions and Privacy Policy to create an account. Do you agree? (yes/no)",
                "hi": "अकाउंट बनाने के लिए आपको नियम व शर्तें और प्राइवेसी पॉलिसी स्वीकार करनी होंगी। क्या आप सहमत हैं? (हाँ/नहीं)",
            }
            return {"reply": T(msg, lang), "type": "reg_terms"}
        return {"reply": T(_REG_PROMPTS["reg_terms"], lang), "type": "reg_terms"}

    if step == "reg_confirm" or step.startswith("reg_edit_"):
        return _handle_register_confirm(session_id, sess, text)

    if step == "reg_otp":
        return _handle_otp_step(session_id, sess, text)

    return _go_to_hub(sess)


def _go_to_terms(sess: Dict[str, Any], lang: str) -> Dict[str, Any]:
    sess["step"] = "reg_terms"
    return {"reply": T(_REG_PROMPTS["reg_terms"], lang), "type": "reg_terms"}


def _summary_lines(data: Dict[str, Any], lang: str) -> str:
    labels = {
        "salutation": {"en": "Salutation", "hi": "संबोधन"},
        "name": {"en": "Full Name", "hi": "पूरा नाम"},
        "mobile": {"en": "Mobile", "hi": "मोबाइल"},
        "email": {"en": "Email", "hi": "ईमेल"},
        "state": {"en": "State", "hi": "राज्य"},
        "district": {"en": "District", "hi": "जिला"},
        "referral_code": {"en": "Referral Code", "hi": "रेफरल कोड"},
    }
    lines = []
    for key, label in labels.items():
        val = data.get(key)
        if val:
            lines.append(f"• {T(label, lang)}: {val}")
    pw_label = {"en": "Password", "hi": "पासवर्ड"}
    lines.append(f"• {T(pw_label, lang)}: {'•' * len(data.get('password', ''))}")
    return "\n".join(lines)


_EDIT_BUTTON_FIELDS = [
    ("name", {"en": "✏️ Edit Name", "hi": "✏️ नाम बदलें"}),
    ("mobile", {"en": "✏️ Edit Mobile", "hi": "✏️ मोबाइल बदलें"}),
    ("email", {"en": "✏️ Edit Email", "hi": "✏️ ईमेल बदलें"}),
    ("state", {"en": "✏️ Edit State", "hi": "✏️ राज्य बदलें"}),
    ("district", {"en": "✏️ Edit District", "hi": "✏️ जिला बदलें"}),
    ("password", {"en": "✏️ Edit Password", "hi": "✏️ पासवर्ड बदलें"}),
]


def _register_confirm_summary(sess: Dict[str, Any], lang: str) -> Dict[str, Any]:
    sess["step"] = "reg_confirm"
    summary = _summary_lines(sess["data"], lang)
    msg = {
        "en": (f"Great, here's what I've got — please check and confirm:\n{summary}\n\n"
               f"Tap ✅ Confirm & Save to submit, or tap a field below to edit it "
               f"(you can also just type the change, e.g. 'change email to name@example.com')."),
        "hi": (f"बढ़िया, यह रही आपकी जानकारी — कृपया जांचें और कन्फर्म करें:\n{summary}\n\n"
               f"सबमिट करने के लिए ✅ Confirm & Save दबाएं, या नीचे किसी फ़ील्ड पर टैप करके बदलें "
               f"(या टाइप करके भी बता सकते हैं, जैसे 'ईमेल बदलकर name@example.com करो')।"),
    }
    confirm_label = {"en": "✅ Confirm & Save", "hi": "✅ Confirm & Save"}
    options = [{"label": T(confirm_label, lang), "value": "confirm"}]
    for field_key, label in _EDIT_BUTTON_FIELDS:
        if sess["data"].get(field_key):
            options.append({"label": T(label, lang), "value": f"__EDITFIELD__:{field_key}"})
    return {"reply": T(msg, lang), "type": "reg_confirm", "options": options}


_CONFIRM_WORDS = {"confirm", "yes", "submit", "correct", "done", "haan", "sahi",
                   "हाँ", "सही", "पक्का", "कन्फर्म", "जमा करो"}

_EDIT_FIELD_MAP = {
    "name": "name", "full name": "name", "नाम": "name",
    "email": "email", "mail": "email", "ईमेल": "email",
    "mobile": "mobile", "phone": "mobile", "number": "mobile", "मोबाइल": "mobile", "फ़ोन": "mobile",
    "state": "state", "राज्य": "state",
    "district": "district", "जिला": "district",
    "password": "password", "पासवर्ड": "password",
    "referral": "referral_code", "referral code": "referral_code", "रेफरल": "referral_code",
}


def _handle_register_confirm(session_id: str, sess: Dict[str, Any], text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    norm = text.strip().lower().rstrip(".!।")

    # Already mid-edit (user tapped ✏️ Edit Email and this message is the new
    # value) — apply it directly. This must come before the phrase-scan below,
    # otherwise a new email like "x@gmail.com" gets misread as the word
    # "email" and re-triggers the edit prompt instead of saving it.
    if sess["step"].startswith("reg_edit_"):
        field_key = sess["step"].replace("reg_edit_", "")
        return _apply_edit(sess, field_key, text)

    if norm in _CONFIRM_WORDS or any(w in norm.split() for w in ("confirm", "submit", "yes", "correct")):
        return _submit_registration(session_id, sess)

    if norm.startswith("__editfield__:"):
        field_key = text.split(":", 1)[1].strip()
        sess["step"] = f"reg_edit_{field_key}"
        label = {"name": "your full name", "email": "your email", "mobile": "your mobile number",
                  "state": "your state", "district": "your district", "password": "your new password",
                  "referral_code": "your referral code"}.get(field_key, "the new value")
        msg = {"en": f"Sure, please tell me {label}.", "hi": "ठीक है, कृपया नई जानकारी बताएं।"}
        return {"reply": T(msg, lang), "type": "reg_edit"}

    for phrase, field_key in _EDIT_FIELD_MAP.items():
        if phrase in norm:
            sess["step"] = f"reg_edit_{field_key}"
            label = {"name": "your full name", "email": "your email", "mobile": "your mobile number",
                      "state": "your state", "district": "your district", "password": "your new password",
                      "referral_code": "your referral code"}[field_key]
            msg = {"en": f"Sure, please tell me {label}.", "hi": "ठीक है, कृपया नई जानकारी बताएं।"}
            return {"reply": T(msg, lang), "type": "reg_edit"}

    return _register_confirm_summary(sess, lang)


def _apply_edit(sess: Dict[str, Any], field_key: str, text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    data = sess["data"]

    if field_key == "email":
        ok, value = normalize_email(text)
        if not ok:
            return {"reply": value, "type": "reg_edit"}
        data["email"] = value
    elif field_key == "mobile":
        ok, value = normalize_mobile(text)
        if not ok:
            return {"reply": value, "type": "reg_edit"}
        data["mobile"] = value
    elif field_key == "password":
        if len(text.strip()) < 6:
            msg = {"en": "Password must be at least 6 characters.", "hi": "पासवर्ड कम से कम 6 अक्षर का होना चाहिए।"}
            return {"reply": T(msg, lang), "type": "reg_edit"}
        data["password"] = text.strip()
    else:
        data[field_key] = text.strip()

    sess["step"] = "reg_confirm"
    return _register_confirm_summary(sess, lang)


_OTP_PROMPT = {
    "en": ("We've sent a 6-digit OTP to your email ({email}) and mobile ({mobile}). "
           "Please enter the OTP to complete your registration. "
           "(Type or say 'resend' if you didn't get it.)"),
    "hi": ("आपके ईमेल ({email}) और मोबाइल ({mobile}) पर 6 अंकों का OTP भेज दिया गया है। "
           "रजिस्ट्रेशन पूरा करने के लिए कृपया OTP दर्ज करें। "
           "(अगर OTP नहीं मिला तो 'resend' टाइप करें या बोलें।)"),
}
RESEND_WORDS = {"resend", "resend otp", "again", "फिर से भेजो", "दोबारा भेजो", "otp फिर से"}


def _submit_registration(session_id: str, sess: Dict[str, Any]) -> Dict[str, Any]:
    """Step 1: POST /auth/register. On success the API sends an OTP to the
    user's email + mobile and returns a verification_id, so we move to the
    OTP step. If the API doesn't return a verification_id (e.g. registration
    completed directly with no OTP required), we finalize immediately."""
    lang = sess["lang"]
    data = sess["data"]

    ok, resp, status = api_client.register_user(
        name=data.get("name", ""),
        mobile=data.get("mobile", ""),
        email=data.get("email", ""),
        password=data.get("password", ""),
        referral_code=data.get("referral_code", ""),
        salutation=data.get("salutation", ""),
        state=data.get("state", ""),
        district=data.get("district", ""),
    )

    if not ok:
        server_msg = resp.get("message") or resp.get("error") or ""
        msg = {
            "en": f"Registration failed: {server_msg or 'please try again.'} Say 'confirm' to retry, or tell me what to change.",
            "hi": f"रजिस्ट्रेशन विफल रहा: {server_msg or 'कृपया दोबारा कोशिश करें।'} दोबारा कोशिश के लिए 'कन्फर्म' बोलें, या बताएं क्या बदलना है।",
        }
        return {"reply": T(msg, lang), "type": "reg_confirm"}

    # verification_id = api_client.extract_verification_id(resp)
    # if not verification_id:
    #     # API completed registration directly without an OTP step.
    #     return _finalize_registration(sess, resp)

    # data["verification_id"] = verification_id
    # sess["step"] = "reg_otp"
    # return {
    #     "reply": T(_OTP_PROMPT, lang, email=data.get("email", ""), mobile=data.get("mobile", "")),
    #     "type": "reg_otp",
    # }

# otp verification 
    return _finalize_registration(sess, resp)

def _handle_otp_step(session_id: str, sess: Dict[str, Any], text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    data = sess["data"]
    norm = text.strip().lower().rstrip(".!।")
    verification_id = data.get("verification_id", "")

    if norm in RESEND_WORDS:
        ok, resp, status = api_client.resend_otp(verification_id)
        if ok:
            msg = {
                "en": "✅ A new OTP has been sent. Please check your email/SMS and enter the code.",
                "hi": "✅ नया OTP भेज दिया गया है। कृपया अपना ईमेल/SMS चेक करें और कोड दर्ज करें।",
            }
        else:
            server_msg = resp.get("message") or resp.get("error") or ""
            msg = {
                "en": f"Sorry, couldn't resend the OTP{': ' + server_msg if server_msg else '.'} Please try again in a moment.",
                "hi": f"माफ़ कीजिए, OTP दोबारा नहीं भेज पाया{': ' + server_msg if server_msg else '।'} कृपया थोड़ी देर बाद कोशिश करें।",
            }
        return {"reply": T(msg, lang), "type": "reg_otp"}

    otp = "".join(ch for ch in text if ch.isdigit())
    if len(otp) < 4:
        msg = {
            "en": "Please enter the OTP you received (numbers only), or type 'resend' for a new code.",
            "hi": "कृपया प्राप्त OTP दर्ज करें (सिर्फ़ अंक), या नया कोड पाने के लिए 'resend' लिखें।",
        }
        return {"reply": T(msg, lang), "type": "reg_otp"}

    ok, resp, status = api_client.verify_otp(verification_id, otp)
    if not ok:
        server_msg = resp.get("message") or resp.get("error") or ""
        msg = {
            "en": f"That OTP didn't work{': ' + server_msg if server_msg else '.'} Please check and try again, or type 'resend' for a new code.",
            "hi": f"यह OTP सही नहीं है{': ' + server_msg if server_msg else '।'} कृपया दोबारा जांचें, या नया कोड पाने के लिए 'resend' लिखें।",
        }
        return {"reply": T(msg, lang), "type": "reg_otp"}

    return _finalize_registration(sess, resp)


def _finalize_registration(sess: Dict[str, Any], api_resp: Dict[str, Any]) -> Dict[str, Any]:
    lang = sess["lang"]
    data = sess["data"]

    _log_signup(data, api_resp)

    sess["_registered_data"] = {
        "name": data.get("name", ""),
        "mobile": data.get("mobile", ""),
        "email": data.get("email", ""),
    }

    pending = sess.pop("_pending_item", None)
    interest_line = ""
    if pending and pending.get("title"):
        interest_msg = {
            "en": f"Your interest in \"{pending['title']}\" has been noted — our team will help you enroll after you log in.\n",
            "hi": f"\"{pending['title']}\" में आपकी रुचि दर्ज कर ली गई है — लॉगिन करने के बाद हमारी टीम एनरोलमेंट में मदद करेगी।\n",
        }
        interest_line = T(interest_msg, lang)

    msg = {
        "en": (f"🎉 Congratulations, you have successfully registered! Here are your login credentials:\n"
               f"• Mobile: {data.get('mobile')}\n"
               f"• Password: {data.get('password')}\n\n"
               f"{interest_line}"
               f"Tap the button below to log in and see your courses."),
        "hi": (f"🎉 बधाई हो, आपका रजिस्ट्रेशन सफलतापूर्वक हो गया है! ये रहे आपके लॉगिन क्रेडेंशियल:\n"
               f"• मोबाइल: {data.get('mobile')}\n"
               f"• पासवर्ड: {data.get('password')}\n\n"
               f"{interest_line}"
               f"लॉगिन करके अपने कोर्सेज़ देखने के लिए नीचे दिया बटन दबाएं।"),
    }
    login_label = {"en": "🔐 Login to Rozzgaar", "hi": "🔐 Rozzgaar पर लॉगिन करें"}
    login_button = {"label": T(login_label, lang), "value": f"__OPEN_LINK__:{ROZZGAAR_LOGIN_URL}"}

    hub = _go_to_hub(sess)
    return {
        "reply": T(msg, lang) + "\n\n" + hub["reply"],
        "type": "reg_success",
        "options": [login_button] + hub["options"],
    }


def _log_signup(data: Dict[str, Any], register_response: Dict[str, Any]) -> None:
    record = {
        "name": data.get("name"),
        "mobile": data.get("mobile"),
        "email": data.get("email"),
        "salutation": data.get("salutation"),
        "state": data.get("state"),
        "district": data.get("district"),
        "referral_code": data.get("referral_code"),
        "register_response": register_response,
        "submitted_at": datetime.datetime.now().isoformat(),
    }
    with _signup_log_lock:
        items: List[Dict[str, Any]] = []
        if os.path.exists(SIGNUP_LOG_FILE):
            try:
                with open(SIGNUP_LOG_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                items = []
        items.append(record)
        os.makedirs(os.path.dirname(SIGNUP_LOG_FILE), exist_ok=True)
        with open(SIGNUP_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# HELP HUB (Courses / Bundles / About / Contact)
# ─────────────────────────────────────────────
def _handle_hub(session_id: str, sess: Dict[str, Any], text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    norm = text.strip().lower()

    if norm.startswith("__hub__:"):
        choice = norm.split(":", 1)[1]
        if choice == "courses":
            return _show_courses(sess, lang)
        if choice == "bundles":
            return _show_bundles(sess, lang)
        if choice == "about":
            return _show_about(sess, lang)
        if choice == "contact":
            return _start_contact(session_id, sess)

    if norm.startswith("__course__:"):
        slug = text.split(":", 1)[1]
        return _show_course_detail(sess, lang, slug)

    if norm.startswith("__bundle__:"):
        slug = text.split(":", 1)[1]
        return _show_bundle_detail(sess, lang, slug)

    if norm.startswith("__register_course__:"):
        slug = text.split(":", 1)[1]
        last = sess.get("_last_course") or {}
        title = last.get("title") if last.get("slug") == slug else None
        if not title:
            _, detail, _ = api_client.get_course_detail(slug)
            title = _item_title(detail) or slug
        return _start_register(session_id, sess, pending={"type": "course", "slug": slug, "title": title})

    if norm.startswith("__register_bundle__:"):
        slug = text.split(":", 1)[1]
        last = sess.get("_last_bundle") or {}
        title = last.get("title") if last.get("slug") == slug else None
        if not title:
            _, detail, _ = api_client.get_bundle_detail(slug)
            title = _item_title(detail) or slug
        return _start_register(session_id, sess, pending={"type": "bundle", "slug": slug, "title": title})

    # "how many courses are in this bundle?"
    if any(k in norm for k in COUNT_KEYWORDS):
        return _answer_bundle_course_count(sess, lang, text)

    course_match = _match_cached_item(sess.get("_courses_cache"), text)
    if course_match:
        return _show_course_detail(sess, lang, course_match["slug"])

    bundle_match = _match_cached_item(sess.get("_bundles_cache"), text)
    if bundle_match:
        return _show_bundle_detail(sess, lang, bundle_match["slug"])

    # "register" typed as free text for whatever was last viewed
    if any(w in norm for w in REGISTER_INTENT_WORDS):
        if sess.get("_last_course"):
            item = sess["_last_course"]
            return _start_register(session_id, sess, pending={"type": "course", **item})
        if sess.get("_last_bundle"):
            item = sess["_last_bundle"]
            return _start_register(session_id, sess, pending={"type": "bundle", "slug": item["slug"], "title": item["title"]})

    # Free-text mention of a specific course/bundle (e.g. "tell me about EDP")
    # — checked before the generic keyword redirects below, since a real
    # course/bundle name can itself contain a word like "about" or "course".
    ok_c, all_courses, _ = api_client.get_courses()
    if ok_c and all_courses:
        fuzzy_course = _fuzzy_find_item(all_courses, text)
        if fuzzy_course:
            slug = _item_slug(fuzzy_course)
            if slug:
                return _show_course_detail(sess, lang, slug)

    ok_b, all_bundles, _ = api_client.get_bundles()
    if ok_b and all_bundles:
        fuzzy_bundle = _fuzzy_find_item(all_bundles, text)
        if fuzzy_bundle:
            slug = _item_slug(fuzzy_bundle)
            if slug:
                return _show_bundle_detail(sess, lang, slug)

    if any(k in norm for k in BUNDLE_KEYWORDS):
        return _show_bundles(sess, lang)
    if any(k in norm for k in COURSE_KEYWORDS):
        return _show_courses(sess, lang)
    if any(k in norm for k in ABOUT_KEYWORDS):
        return _show_about(sess, lang)
    if any(k in norm for k in CONTACT_KEYWORDS):
        return _start_contact(session_id, sess)

    msg = {
        "en": "Sorry, I didn't quite get that. Here's how I can help:",
        "hi": "माफ़ कीजिए, समझ नहीं पाया। मैं इन चीज़ों में मदद कर सकता हूँ:",
    }
    return {"reply": T(msg, lang), "type": "help_hub", "options": HUB_OPTIONS[lang]}


# ── item helpers (courses & bundles share the same shape) ──
def _item_title(item: Dict[str, Any]) -> str:
    for key in ("title", "name", "course_name", "course_title", "bundle_name"):
        if item.get(key):
            return str(item[key])
    return ""


def _item_slug(item: Dict[str, Any]) -> str:
    for key in ("slug", "course_slug", "bundle_slug"):
        if item.get(key):
            return str(item[key])
    for key in ("id", "course_id", "bundle_id"):
        if item.get(key) not in (None, ""):
            return str(item[key])
    return ""


def _item_price(item: Dict[str, Any]) -> Optional[str]:
    for key in ("price", "fee", "amount", "cost", "discounted_price"):
        if item.get(key) not in (None, ""):
            return str(item[key])
    return None


def _item_desc(item: Dict[str, Any]) -> str:
    for key in ("short_description", "description", "desc", "details", "summary"):
        if item.get(key):
            return str(item[key])
    return ""


def _shorten(text: str, max_words: int = 200) -> str:
    """Trim to a short response capped at `max_words` words (default 200),
    always ending on a full sentence where possible."""
    if not text:
        return ""
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    truncated = " ".join(words[:max_words])
    parts = re.split(r"(?<=[.!?])\s+", truncated)
    if len(parts) > 1:
        truncated = " ".join(parts[:-1]).strip()
    return truncated.rstrip(",;:") + "…"


def _extract_bundle_courses(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Bundle-detail responses list which individual courses are covered by
    the bundle under keys like 'courses', 'included_courses', 'course_list'.
    Returns a list of {"title": ...} dicts, defensively handling whatever
    shape the API actually sends. Some bundles only mention the real course
    names inside the free-text description (e.g. "5 Courses: Instagram,
    YouTube, Facebook, Email & WhatsApp Marketing.") while the structured
    field is empty or incomplete — so we parse both and keep whichever is
    more complete."""
    structured: List[Dict[str, Any]] = []
    if isinstance(detail, dict):
        list_keys = ("courses", "included_courses", "bundle_courses", "course_list", "items")
        raw: List[Any] = []
        for key in list_keys:
            val = detail.get(key)
            if isinstance(val, list) and val:
                raw = val
                break
        for item in raw:
            if isinstance(item, dict):
                title = _item_title(item)
                if title:
                    structured.append({"title": title, "slug": _item_slug(item)})
            elif isinstance(item, str):
                structured.append({"title": item, "slug": ""})

    from_desc = _parse_courses_from_description(_item_desc(detail)) if isinstance(detail, dict) else []

    return from_desc if len(from_desc) > len(structured) else structured


def _parse_courses_from_description(desc: str) -> List[Dict[str, Any]]:
    """Looks for a pattern like '5 Courses: A, B, C & D' inside a bundle's
    description text and pulls out the individual course names."""
    if not desc:
        return []
    match = re.search(r"courses?\s*:\s*([^.\n]+)", desc, re.IGNORECASE)
    if not match:
        return []
    chunk = match.group(1)
    chunk = re.sub(r"\s*&\s*", ", ", chunk)
    chunk = re.sub(r"\s+and\s+", ", ", chunk, flags=re.IGNORECASE)
    names = [n.strip(" .") for n in chunk.split(",")]
    return [{"title": n, "slug": ""} for n in names if len(n) >= 2]


def _register_button_option(lang: str, kind: str, slug: str) -> Dict[str, str]:
    label = {
        "en": "📝 Register for this course" if kind == "course" else "📝 Register for this bundle",
        "hi": "📝 इस कोर्स के लिए रजिस्टर करें" if kind == "course" else "📝 इस बंडल के लिए रजिस्टर करें",
    }
    tag = "__REGISTER_COURSE__" if kind == "course" else "__REGISTER_BUNDLE__"
    return {"label": T(label, lang), "value": f"{tag}:{slug}"}


def _fuzzy_find_item(items: List[Dict[str, Any]], text: str) -> Optional[Dict[str, Any]]:
    """Loose keyword match used when the user names a course/bundle (or an
    abbreviation like 'EDP') without tapping it from a list first."""
    norm = text.strip().lower()
    norm = norm.strip(".!?।")
    if len(norm) < 2:
        return None
    query_tokens = {w for w in re.split(r"[^a-z0-9\u0900-\u097F]+", norm) if len(w) >= 2}
    query_tokens -= {"the", "a", "an", "of", "and", "tell", "me", "about", "know", "what",
                     "is", "course", "courses", "bundle", "bundles", "please", "detail",
                     "details", "in", "for", "how", "many", "does", "do", "they", "it",
                     "cover", "covers", "covered", "this", "that", "have", "has", "are",
                     "there", "included", "include", "includes", "with", "on", "to"}
    if not query_tokens:
        return None

    best_item = None
    best_score = 0
    for item in items:
        title = _item_title(item)
        if not title:
            continue
        title_lower = title.lower()
        if title_lower in norm or norm in title_lower:
            return item
        title_tokens = {w for w in re.split(r"[^a-z0-9\u0900-\u097F]+", title_lower) if len(w) >= 2}
        score = len(query_tokens & title_tokens)
        if score > best_score:
            best_score = score
            best_item = item
    return best_item if best_score > 0 else None


def _match_cached_item(cache: Optional[List[Dict[str, Any]]], text: str) -> Optional[Dict[str, Any]]:
    if not cache:
        return None
    norm = text.strip().lower()
    if len(norm) < 4:
        return None
    for item in cache:
        title = (item.get("title") or "").lower()
        if len(title) < 4:
            continue
        if title in norm or norm in title:
            return item
    return None


def _show_courses(sess: Dict[str, Any], lang: str) -> Dict[str, Any]:
    ok, courses, status = api_client.get_courses()
    if not ok or not courses:
        msg = {
            "en": "Sorry, I couldn't fetch the course list right now. Please try again shortly.",
            "hi": "माफ़ कीजिए, अभी कोर्स की सूची नहीं ला पाया। कृपया थोड़ी देर बाद कोशिश करें।",
        }
        return {"reply": T(msg, lang), "type": "help_hub", "options": HUB_OPTIONS[lang]}

    cache = []
    options = []
    for c in courses:
        title = _item_title(c)
        slug = _item_slug(c)
        if not title or not slug:
            continue
        cache.append({"title": title, "slug": slug})
        options.append({"label": title, "value": f"__COURSE__:{slug}"})

    sess["_courses_cache"] = cache
    msg = {
        "en": "Here are all our courses — tap one to know more:",
        "hi": "ये रहे हमारे सभी कोर्स — किसी एक पर टैप करें और जानें:",
    }
    return {"reply": T(msg, lang), "type": "courses_list", "options": options}


def _show_course_detail(sess: Dict[str, Any], lang: str, slug: str) -> Dict[str, Any]:
    ok, detail, status = api_client.get_course_detail(slug)
    if not ok or not detail:
        msg = {
            "en": "Sorry, I couldn't fetch that course's details right now.",
            "hi": "माफ़ कीजिए, अभी इस कोर्स की जानकारी नहीं ला पाया।",
        }
        return {"reply": T(msg, lang), "type": "help_hub", "options": HUB_OPTIONS[lang]}

    title = _item_title(detail) or slug
    real_slug = _item_slug(detail) or slug
    price = _item_price(detail)
    short = _shorten(_item_desc(detail), max_words=200)

    line = f"📚 {title}"
    if price:
        line += f" — ₹{price}"
    if short:
        line += f"\n{short}"

    sess["_last_course"] = {"slug": real_slug, "title": title}
    options = [_register_button_option(lang, "course", real_slug)]
    return {"reply": line, "type": "course_detail", "options": options}


def _show_bundles(sess: Dict[str, Any], lang: str) -> Dict[str, Any]:
    ok, bundles, status = api_client.get_bundles()
    if not ok or not bundles:
        msg = {
            "en": "Sorry, I couldn't fetch the course bundles right now. Please try again shortly.",
            "hi": "माफ़ कीजिए, अभी कोर्स बंडल की सूची नहीं ला पाया। कृपया थोड़ी देर बाद कोशिश करें।",
        }
        return {"reply": T(msg, lang), "type": "help_hub", "options": HUB_OPTIONS[lang]}

    cache = []
    options = []
    for b in bundles:
        title = _item_title(b)
        slug = _item_slug(b)
        if not title or not slug:
            continue
        cache.append({"title": title, "slug": slug})
        options.append({"label": title, "value": f"__BUNDLE__:{slug}"})

    sess["_bundles_cache"] = cache
    msg = {
        "en": "Here are our course bundles — tap one to know more:",
        "hi": "ये रहे हमारे कोर्स बंडल — किसी एक पर टैप करें और जानें:",
    }
    return {"reply": T(msg, lang), "type": "bundles_list", "options": options}


def _show_bundle_detail(sess: Dict[str, Any], lang: str, slug: str) -> Dict[str, Any]:
    ok, detail, status = api_client.get_bundle_detail(slug)
    if not ok or not detail:
        msg = {
            "en": "Sorry, I couldn't fetch that bundle's details right now.",
            "hi": "माफ़ कीजिए, अभी इस बंडल की जानकारी नहीं ला पाया।",
        }
        return {"reply": T(msg, lang), "type": "help_hub", "options": HUB_OPTIONS[lang]}

    title = _item_title(detail) or slug
    real_slug = _item_slug(detail) or slug
    price = _item_price(detail)
    short = _shorten(_item_desc(detail), max_words=200)
    included = _extract_bundle_courses(detail)

    line = f"🎁 {title}"
    if price:
        line += f" — ₹{price}"
    if short:
        line += f"\n{short}"

    if included:
        count_msg = {
            "en": f"\n\nThis bundle covers {len(included)} course{'s' if len(included) != 1 else ''}:",
            "hi": f"\n\nयह बंडल {len(included)} कोर्स को कवर करता है:",
        }
        line += T(count_msg, lang)
        for c in included[:20]:
            line += f"\n• {c['title']}"
        if len(included) > 20:
            more_msg = {"en": f"…and {len(included) - 20} more.", "hi": f"…और {len(included) - 20} और।"}
            line += "\n" + T(more_msg, lang)

    sess["_last_bundle"] = {"slug": real_slug, "title": title, "courses": included}
    options = [_register_button_option(lang, "bundle", real_slug)]
    return {"reply": line, "type": "bundle_detail", "options": options}


def _answer_bundle_course_count(sess: Dict[str, Any], lang: str, text: str) -> Dict[str, Any]:
    """Answers "how many courses does <bundle> cover?" — resolves the bundle
    the user is actually naming in THIS message first (so asking about a
    different bundle than the last one viewed still works correctly), and
    only falls back to whatever bundle was last opened if none is named."""
    target_slug = None
    target_title = None

    ok_b, all_bundles, _ = api_client.get_bundles()
    if ok_b and all_bundles:
        matched = _fuzzy_find_item(all_bundles, text)
        if matched:
            target_slug = _item_slug(matched)
            target_title = _item_title(matched)

    if target_slug:
        ok, detail, _ = api_client.get_bundle_detail(target_slug)
        if ok and detail:
            return _show_bundle_detail(sess, lang, target_slug)

    last = sess.get("_last_bundle")
    if not last:
        return _show_bundles(sess, lang)

    included = last.get("courses") or []
    title = last.get("title") or ""
    if not included:
        msg = {
            "en": f"I don't have a course-by-course list for \"{title}\" right now, but you can ask me about it after checking the bundle page.",
            "hi": f"अभी \"{title}\" के लिए कोर्स-वार सूची उपलब्ध नहीं है।",
        }
        return {"reply": T(msg, lang), "type": "bundle_detail", "options": [_register_button_option(lang, "bundle", last["slug"])]}

    header = {
        "en": f"\"{title}\" covers {len(included)} course{'s' if len(included) != 1 else ''}:",
        "hi": f"\"{title}\" में {len(included)} कोर्स शामिल हैं:",
    }
    lines = [T(header, lang)]
    for c in included[:20]:
        lines.append(f"• {c['title']}")
    if len(included) > 20:
        lines.append(T({"en": f"…and {len(included) - 20} more.", "hi": f"…और {len(included) - 20} और।"}, lang))

    options = [_register_button_option(lang, "bundle", last["slug"])]
    return {"reply": "\n".join(lines), "type": "bundle_detail", "options": options}


def _show_about(sess: Dict[str, Any], lang: str) -> Dict[str, Any]:
    return {"reply": T(ABOUT_TEXT, lang), "type": "about", "options": HUB_OPTIONS[lang]}


# ─────────────────────────────────────────────
# CONTACT FORM (POST /misc/contact)
# ─────────────────────────────────────────────
_CONTACT_PROMPTS = {
    "contact_name": {
        "en": "Sure! What's your name?",
        "hi": "ज़रूर! आपका नाम क्या है?",
    },
    "contact_mobile": {
        "en": "What's your 10-digit mobile number?",
        "hi": "आपका 10 अंकों का मोबाइल नंबर क्या है?",
    },
    "contact_email": {
        "en": "What's your email address?",
        "hi": "आपका ईमेल एड्रेस क्या है?",
    },
    "contact_message": {
        "en": "What would you like to tell us?",
        "hi": "आप हमें क्या बताना चाहेंगे?",
    },
}


def _start_contact(session_id: str, sess: Dict[str, Any]) -> Dict[str, Any]:
    lang = sess["lang"]
    reg = sess.get("_registered_data") or {}

    if reg.get("name") and reg.get("mobile") and reg.get("email"):
        sess["step"] = "contact_message"
        sess["data"] = {"name": reg["name"], "mobile": reg["mobile"], "email": reg["email"]}
        return {"reply": T(_CONTACT_PROMPTS["contact_message"], lang), "type": "contact_message"}

    sess["step"] = "contact_name"
    sess["data"] = {}
    return {"reply": T(_CONTACT_PROMPTS["contact_name"], lang), "type": "contact_name"}


def _handle_contact_step(session_id: str, sess: Dict[str, Any], text: str) -> Dict[str, Any]:
    lang = sess["lang"]
    step = sess["step"]
    data = sess["data"]

    if step == "contact_name":
        cleaned = text.strip()
        if len(cleaned) < 2:
            msg = {"en": "That doesn't look like a valid name, please try again.",
                   "hi": "यह सही नाम नहीं लग रहा, कृपया दोबारा बताएं।"}
            return {"reply": T(msg, lang), "type": "contact_name"}
        data["name"] = cleaned
        sess["step"] = "contact_mobile"
        return {"reply": T(_CONTACT_PROMPTS["contact_mobile"], lang), "type": "contact_mobile"}

    if step == "contact_mobile":
        ok, value = normalize_mobile(text)
        if not ok:
            return {"reply": value, "type": "contact_mobile"}
        data["mobile"] = value
        sess["step"] = "contact_email"
        return {"reply": T(_CONTACT_PROMPTS["contact_email"], lang), "type": "contact_email"}

    if step == "contact_email":
        ok, value = normalize_email(text)
        if not ok:
            return {"reply": value, "type": "contact_email"}
        data["email"] = value
        sess["step"] = "contact_message"
        return {"reply": T(_CONTACT_PROMPTS["contact_message"], lang), "type": "contact_message"}

    if step == "contact_message":
        message = text.strip()
        if len(message) < 3:
            return {"reply": T(_CONTACT_PROMPTS["contact_message"], lang), "type": "contact_message"}

        subject = message[:60] if len(message) > 60 else message
        ok, resp, status = api_client.submit_contact(
            name=data.get("name", ""),
            mobile=data.get("mobile", ""),
            email=data.get("email", ""),
            subject=subject or "Chatbot Inquiry",
            message=message,
        )

        if ok:
            msg = {
                "en": "✅ Thanks! Your message has been sent to our team — we'll get back to you soon.",
                "hi": "✅ धन्यवाद! आपका मैसेज हमारी टीम को भेज दिया गया है — हम जल्द ही आपसे संपर्क करेंगे।",
            }
        else:
            server_msg = resp.get("message") or resp.get("error") or ""
            msg = {
                "en": f"Sorry, I couldn't send your message{': ' + server_msg if server_msg else '.'} Please try again shortly.",
                "hi": f"माफ़ कीजिए, आपका मैसेज नहीं भेज पाया{': ' + server_msg if server_msg else '।'} कृपया थोड़ी देर बाद कोशिश करें।",
            }

        hub = _go_to_hub(sess)
        return {"reply": T(msg, lang) + "\n\n" + hub["reply"], "type": "contact_done", "options": hub["options"]}

    return _go_to_hub(sess)
