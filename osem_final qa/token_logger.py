import json
import logging
import sys
from datetime import datetime, timezone


class _StdoutHandler(logging.StreamHandler):
    """Writes to whatever sys.stdout currently is, so output is captured by
    process managers (gunicorn, Docker) and by test tooling alike."""

    def __init__(self):
        logging.Handler.__init__(self)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value):
        pass


_usage_logger = logging.getLogger("usage")
if not _usage_logger.handlers:
    _handler = _StdoutHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _usage_logger.addHandler(_handler)
    _usage_logger.setLevel(logging.INFO)
    _usage_logger.propagate = False


def log_usage(tokens_generated, lang):
    """Emit one JSON line per answered question. Raw user questions are never logged."""
    record = {
        "event": "token_usage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tokens_generated": int(tokens_generated or 0),
        "lang": lang,
    }
    _usage_logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
