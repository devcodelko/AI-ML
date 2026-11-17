import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("rozzgaar_bot")

ROZZGAAR_API_BASE = os.getenv("ROZZGAAR_API_BASE", "https://rozzgaar.in/apis").strip().rstrip("/")
ROZZGAAR_API_KEY = os.getenv("ROZZGAAR_API_KEY", "").strip()
FLASK_PORT = int(os.getenv("FLASK_PORT", "5050"))
ROZZGAAR_LOGIN_URL = os.getenv("ROZZGAAR_LOGIN_URL", "https://rozzgaar.in/login").strip()

if not ROZZGAAR_API_KEY:
    raise ValueError("ROZZGAAR_API_KEY missing. Add it to your .env file.")

REQUEST_TIMEOUT = 20

# ── Speech-to-text (Groq Whisper) — used for accurate voice recognition ───
# Optional: if not set, /transcribe returns 503 and the frontend falls back
# to the browser's built-in (less accurate) speech recognition.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()
STT_TIMEOUT = 25

# ── Text-to-speech (TTS.ai, Kokoro model) — spoken chatbot replies ────────
# Optional: if not set, /chat responses simply omit the "audio" field and
# the frontend falls back to the browser's built-in speechSynthesis voice.
TTS_AI_API_KEY = os.getenv("TTS_AI_API_KEY", "").strip()
# TTS.ai's endpoint follows the OpenAI-compatible /v1/audio/speech shape
# used by Kokoro-based providers. Override TTS_AI_API_URL in .env if your
# TTS.ai account docs give you a different base URL.
TTS_AI_API_URL = os.getenv("TTS_AI_API_URL", "https://api.tts.ai/v1/audio/speech").strip()
TTS_AI_MODEL = os.getenv("TTS_AI_MODEL", "kokoro").strip()
TTS_AI_VOICE_EN = os.getenv("TTS_AI_VOICE_EN", "am_michael").strip()
TTS_AI_VOICE_HI = os.getenv("TTS_AI_VOICE_HI", "hm_omega").strip()
TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "600"))
TTS_TIMEOUT = 25

# ── API endpoints actually used by this bot ───────────────
EP_REGISTER    = f"{ROZZGAAR_API_BASE}/auth/register"
EP_VERIFY_OTP  = f"{ROZZGAAR_API_BASE}/auth/verify-otp"
EP_RESEND_OTP  = f"{ROZZGAAR_API_BASE}/auth/resend-otp"
EP_STATES     = f"{ROZZGAAR_API_BASE}/misc/states"
EP_DISTRICTS  = f"{ROZZGAAR_API_BASE}/misc/districts"
EP_COURSES    = f"{ROZZGAAR_API_BASE}/courses"
EP_BUNDLES    = f"{ROZZGAAR_API_BASE}/courses/bundles"
EP_CONTACT    = f"{ROZZGAAR_API_BASE}/misc/contact"


def course_detail_url(slug: str) -> str:
    return f"{ROZZGAAR_API_BASE}/courses/{slug}"


def bundle_detail_url(slug: str) -> str:
    return f"{ROZZGAAR_API_BASE}/courses/bundles/{slug}"


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNUP_LOG_FILE = os.path.join(_BASE_DIR, "data", "signups.json")
