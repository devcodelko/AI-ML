import os
import logging
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ai_learning_assistant")

ROZZGAAR_API_BASE = os.getenv("ROZZGAAR_API_BASE", "https://rozzgaar.in/apis").strip().rstrip("/")
ROZZGAAR_API_KEY = os.getenv("ROZZGAAR_API_KEY", "").strip()

if not ROZZGAAR_API_KEY:
    raise ValueError("ROZZGAAR_API_KEY missing. Add it to your .env file.")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY missing. Add it to your .env file.")

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.3"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "4096"))

REQUEST_TIMEOUT = 20
CONTENT_CACHE_TTL_SECONDS = int(os.getenv("CONTENT_CACHE_TTL_SECONDS", "300"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "10"))

APP_PORT = int(os.getenv("APP_PORT", "8000"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")


def course_contents_url(course_slug: str) -> str:
    return f"{ROZZGAAR_API_BASE}/courses/{course_slug}/contents"
