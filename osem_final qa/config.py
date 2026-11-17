import os

from dotenv import load_dotenv

load_dotenv()


def _env(name, default=""):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name, default):
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name, default):
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name, default=False):
    value = _env(name, "")
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on")


REQUIRED_ENV_KEYS = ("GROQ_API_KEY", "GEMINI_API_KEY")

GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-120b"

# Gemini is the fallback: used for chat answers when Groq is rate-limited/unavailable,
# and used for Hindi voice (Groq has no Hindi TTS voice; Gemini's TTS supports Hindi
# clearly). English speech still tries Groq's TTS first, then falls back to Gemini too.
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_VOICE = _env("GEMINI_TTS_VOICE", "Kore")

# Groq's text-to-speech API only supports English and Arabic voices (no Hindi
# voice model exists there), so English replies are spoken with Groq's TTS
# voice below and Hindi replies use Gemini's TTS engine for clear audio.
GROQ_TTS_VOICE_EN = _env("GROQ_TTS_VOICE_EN", "autumn")

SITE_URLS = [
    "https://upicon.in/",
    "https://upicon.in/skill-development",
    "https://upicon.in/contact",
    "https://cmyouthadda.in/",
    "https://upicon.in/csr-training",
    "https://upicon.in/consultancy",
    "https://msmeosem.in/",
    "https://vssy.org.in/",
    "https://xn--i1bn6adp9emg4dcbcajdeflxp1gua1n7bt10abief.xn--11b7cb3a6a.xn--h2brj9c/",
    "https://msme.up.gov.in/hi/login/error",
    "https://cmyuva.org.in/",
    "https://upid.ac.in/vishwakarma-shram-samman-yojana-vssy/",
    "https://msme.up.gov.in/",
    "https://up.gov.in/",
    "https://msme1connect.up.gov.in",
    "https://msme1connect.up.gov.in/scheme/up-schemem",
    "https://msme1connect.up.gov.in/about",
    "https://invest.up.gov.in",
    "https://startinup.up.gov.in",
]

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_PATH = os.path.join(DATA_DIR, "site_chunks.pkl")
REFRESH_LOCK_PATH = os.path.join(DATA_DIR, ".refresh.lock")
INTENTS_PATH = os.path.join(BASE_DIR, "intents.json")

# Request limits
MAX_MESSAGE_CHARS = 500
MAX_TTS_CHARS = 1500
MAX_CONTENT_LENGTH = 16 * 1024

# Rate limiting (per client IP, per worker unless RATELIMIT_STORAGE_URI points at Redis).
CHAT_RATE_LIMIT = _env("CHAT_RATE_LIMIT", "20 per minute")
# The browser requests speech in ~400 character chunks, so one spoken answer is several calls.
SPEAK_RATE_LIMIT = _env("SPEAK_RATE_LIMIT", "60 per minute")
DEFAULT_RATE_LIMIT = _env("DEFAULT_RATE_LIMIT", "120 per minute")
RATELIMIT_STORAGE_URI = _env("RATELIMIT_STORAGE_URI", "memory://")
TRUSTED_PROXIES = max(0, _env_int("TRUSTED_PROXIES", 0))

# Space separated list of origins allowed to embed the chat page in an iframe.
# Default forbids all framing (X-Frame-Options: DENY, CSP frame-ancestors 'none').
FRAME_ANCESTORS = _env("FRAME_ANCESTORS", "")

# Outbound HTTP: every call has an explicit (connect, read) timeout and bounded retries.
HTTP_CONNECT_TIMEOUT = _env_float("HTTP_CONNECT_TIMEOUT", 5.0)
GEMINI_TEXT_READ_TIMEOUT = _env_float("GEMINI_TEXT_READ_TIMEOUT", 25.0)
GEMINI_TTS_READ_TIMEOUT = _env_float("GEMINI_TTS_READ_TIMEOUT", 45.0)
GROQ_TTS_READ_TIMEOUT = _env_float("GROQ_TTS_READ_TIMEOUT", 30.0)
CRAWL_READ_TIMEOUT = _env_float("CRAWL_READ_TIMEOUT", 10.0)
HTTP_MAX_RETRIES = max(0, _env_int("HTTP_MAX_RETRIES", 1))
CRAWL_MAX_RETRIES = max(0, _env_int("CRAWL_MAX_RETRIES", 2))
GROQ_TIMEOUT = _env_float("GROQ_TIMEOUT", 15.0)
GROQ_MAX_RETRIES = max(0, _env_int("GROQ_MAX_RETRIES", 2))
GTTS_TIMEOUT = _env_float("GTTS_TIMEOUT", 15.0)
GTTS_MAX_RETRIES = max(0, _env_int("GTTS_MAX_RETRIES", 2))

# Some .gov.in sites serve broken certificate chains. Verification failures are
# fatal for the crawler unless this is explicitly enabled.
CRAWLER_ALLOW_INSECURE_SSL = _env_bool("CRAWLER_ALLOW_INSECURE_SSL", False)

LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()


def validate():
    missing = [name for name in REQUIRED_ENV_KEYS if not globals().get(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill them in, or set them in the process environment."
        )
