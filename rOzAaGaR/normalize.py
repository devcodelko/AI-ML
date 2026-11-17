"""
normalize.py
─────────────────────────────────────────────────────────────
Cleans up voice-recognition text for the fields that break most
often when spoken instead of typed: email addresses and phone
numbers.

The specific bug this was built to fix:
  User says: "harikeshtiwari at the rate gmail dot com"
  Browser speech-to-text mishears "at the rate" and glues it to
  the domain, producing something like:
      "harikeshtiwariatharategmail.com"
  (no @ symbol, no spaces, "at the rate" garbled into "atharate"
  and merged straight into "gmail.com").

normalize_email() below handles both the clean spoken form
("... at the rate gmail dot com") AND this glued/garbled form.
"""

import re
from typing import Optional, Tuple

_EMAIL_RE = re.compile(r"^[a-z0-9][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}$")

_KNOWN_DOMAINS = [
    "googlemail", "gmail", "yahoo", "outlook", "hotmail",
    "rediffmail", "rediff", "icloud", "protonmail", "live", "ymail", "zoho",
]

# Longest phrases first so "at the rate of" matches before "at the rate", etc.
_SYMBOL_PHRASES = [
    (" at the rate of ", " @ "),
    (" at the rate ", " @ "),
    (" at ther rate ", " @ "),
    (" at der rate ", " @ "),
    (" at the rated ", " @ "),
    (" at therate ", " @ "),
    (" atthe rate ", " @ "),
    (" att the rate ", " @ "),
    (" add the rate ", " @ "),
    (" at rate of ", " @ "),
    (" at rate ", " @ "),
    (" atrate ", " @ "),
    (" at symbol ", " @ "),
    (" at the ", " @ "),
    (" at ", " @ "),
    (" underscore ", "_"),
    (" under score ", "_"),
    (" hyphen ", "-"),
    (" dash ", "-"),
    (" minus ", "-"),
    (" dot com ", ".com "),
    (" dot co dot in ", ".co.in "),
    (" dot co in ", ".co.in "),
    (" dot in ", ".in "),
    (" dot org ", ".org "),
    (" dot net ", ".net "),
    (" dot edu ", ".edu "),
    (" dot ", "."),
    (" point ", "."),
]

# Glued junk that "at the rate" (and friends) commonly turns into when a
# speech engine mishears it and mashes it against the next word.
_GLUE_JUNK_SUFFIX_RE = re.compile(
    r"(atharate|attherate|atthe rate|addtherate|atderrate|attherated|"
    r"therate|atrate|addrate|atsymbol|the rate|rate|there|add|at|the)+$"
)


def _apply_phrase_map(padded_text: str) -> str:
    text = padded_text
    for phrase, repl in _SYMBOL_PHRASES:
        text = text.replace(phrase, repl)
    return text


def normalize_email(raw: str) -> Tuple[bool, str]:
    """Returns (ok, cleaned_email_or_error_message)."""
    if not raw or not raw.strip():
        return False, ""

    text = raw.strip().lower()
    text = re.sub(r"\s+", " ", text)

    # Step 1: replace spoken symbol phrases while spaces still exist.
    padded = f" {text} "
    padded = _apply_phrase_map(padded)
    text = padded.strip()

    # Step 2: collapse remaining spaces (voice engines sometimes insert
    # stray spaces inside words/domains).
    text = text.replace(" ", "")

    # Step 3: if there's still no "@", the phrase was probably glued
    # (e.g. "harikeshtiwariatharategmail.com") — detect a known domain
    # inside the string and rebuild "local@domain.tld" around it.
    if "@" not in text:
        text = _rebuild_glued_email(text)

    # Step 4: final light cleanup.
    text = text.replace("..", ".").strip(".-_")
    text = re.sub(r"@+", "@", text)

    if _EMAIL_RE.match(text):
        return True, text

    return False, (
        "That email doesn't look valid / यह ईमेल सही नहीं लग रहा। "
        "Please type it, or say it slowly like: name AT gmail DOT com."
    )


def _rebuild_glued_email(text: str) -> str:
    for domain_kw in sorted(_KNOWN_DOMAINS, key=len, reverse=True):
        idx = text.find(domain_kw)
        if idx <= 0:
            continue

        local = text[:idx]
        local = _GLUE_JUNK_SUFFIX_RE.sub("", local)
        local = re.sub(r"[^a-z0-9._-]", "", local)
        if not local:
            continue

        rest = text[idx + len(domain_kw):]
        rest_letters = re.sub(r"[^a-z]", "", rest)
        if rest_letters.startswith("coin"):
            tld = "co.in"
        elif rest_letters.startswith("com"):
            tld = "com"
        elif rest_letters.startswith("in"):
            tld = "in"
        elif rest_letters.startswith("org"):
            tld = "org"
        elif rest_letters.startswith("net"):
            tld = "net"
        else:
            tld = "com"

        domain = "gmail" if domain_kw == "googlemail" else domain_kw
        return f"{local}@{domain}.{tld}"

    return text  # no known domain found — will fail validation upstream


# ─────────────────────────────────────────────
# PHONE NUMBER NORMALIZATION
# ─────────────────────────────────────────────
_WORD_DIGITS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3",
    "four": "4", "for": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "ate": "8", "nine": "9",
}


def _words_to_digits(text: str) -> str:
    out = []
    for w in re.findall(r"[A-Za-z]+|\d+", text.lower()):
        if w in _WORD_DIGITS:
            out.append(_WORD_DIGITS[w])
        elif w.isdigit():
            out.append(w)
    return "".join(out)


def normalize_mobile(raw: str) -> Tuple[bool, str]:
    """Returns (ok, cleaned_10_digit_mobile_or_error_message)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 10:
        alt = _words_to_digits(raw or "")
        if len(alt) >= 10:
            digits = alt
    if len(digits) > 10:
        digits = digits[-10:]

    if len(digits) == 10 and digits[0] in "6789":
        return True, digits

    return False, (
        "That doesn't look like a valid 10-digit mobile number / यह सही 10 अंकों "
        "का मोबाइल नंबर नहीं लग रहा। Please say or type your 10-digit number again."
    )


def normalize_otp(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        digits = _words_to_digits(raw or "")
    return digits if digits else None
