"""
api_client.py
─────────────────────────────────────────────────────────────
Thin wrapper around every real Rozzgaar.in API this bot actually
uses:

  POST /auth/register             -> register_user()   (step 1 — sends OTP, returns verification_id)
  POST /auth/verify-otp           -> verify_otp()       (step 2 — completes registration)
  POST /auth/resend-otp           -> resend_otp()
  GET  /misc/states              -> get_states()
  GET  /misc/districts           -> get_districts()
  GET  /courses                  -> get_courses()
  GET  /courses/{slug}           -> get_course_detail()
  GET  /courses/bundles          -> get_bundles()
  GET  /courses/bundles/{slug}   -> get_bundle_detail()
  POST /misc/contact             -> submit_contact()

Every function returns a tuple: (ok: bool, payload, status_code: int)
`payload` is always the parsed JSON body from the API when available,
or {"message": "..."} when the request itself failed (network error,
timeout, non-JSON response, etc).
"""

from typing import Any, Dict, List, Optional, Tuple

import requests

from config import (
    logger,
    ROZZGAAR_API_KEY,
    REQUEST_TIMEOUT,
    EP_REGISTER,
    EP_VERIFY_OTP,
    EP_RESEND_OTP,
    EP_STATES,
    EP_DISTRICTS,
    EP_COURSES,
    EP_BUNDLES,
    EP_CONTACT,
    course_detail_url,
    bundle_detail_url,
)

_HEADERS_JSON = {
    "Authorization": f"Bearer {ROZZGAAR_API_KEY}",
    "Content-Type": "application/json",
}
_HEADERS_PLAIN = {
    "Authorization": f"Bearer {ROZZGAAR_API_KEY}",
}


def _parse_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data
        return {"data": data}
    except ValueError:
        return {"message": resp.text[:500] if resp.text else "Empty response from server."}


def _body_says_error(data: Dict[str, Any]) -> bool:
    """Some endpoints return HTTP 200 but signal failure inside the JSON body
    (e.g. {"status": "error", ...} or {"success": false, ...}). Catch that too."""
    if not isinstance(data, dict):
        return False
    status_val = str(data.get("status", "")).lower()
    if status_val in ("error", "fail", "failed"):
        return True
    if "success" in data and data.get("success") is False:
        return True
    return False


def _post(url: str, body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int]:
    try:
        resp = requests.post(url, json=body, headers=_HEADERS_JSON, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        logger.exception(f"POST {url} failed")
        return False, {"message": f"Network error while calling {url}: {exc}"}, 0
    data = _parse_json(resp)
    ok = (200 <= resp.status_code < 300) and not _body_says_error(data)
    if not ok:
        logger.warning(f"POST {url} -> {resp.status_code} | {data}")
    return ok, data, resp.status_code


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any], int]:
    try:
        resp = requests.get(url, headers=_HEADERS_PLAIN, params=params or {}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        logger.exception(f"GET {url} failed")
        return False, {"message": f"Network error while calling {url}: {exc}"}, 0
    data = _parse_json(resp)
    ok = (200 <= resp.status_code < 300) and not _body_says_error(data)
    if not ok:
        logger.warning(f"GET {url} -> {resp.status_code} | {data}")
    return ok, data, resp.status_code


# ─────────────────────────────────────────────
# REGISTRATION (OTP step intentionally skipped)
# ─────────────────────────────────────────────
def register_user(
    name: str,
    mobile: str,
    email: str,
    password: str,
    referral_code: str = "",
    salutation: str = "",
    state: str = "",
    district: str = "",
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Calls POST /auth/register directly and treats a 2xx response as a
    completed registration. We first try sending the extra profile
    fields too (salutation/state/district) in case the backend stores
    them; if the server rejects the request we automatically retry
    with just the minimal confirmed schema so registration still goes
    through.
    """
    full_payload = {
        "name": name,
        "mobile": mobile,
        "email": email,
        "password": password,
        "referral_code": referral_code or "",
        "salutation": salutation,
        "state": state,
        "district": district,
    }
    ok, data, status = _post(EP_REGISTER, full_payload)
    if ok:
        return ok, data, status

    if status in (400, 422):
        minimal_payload = {
            "name": name,
            "mobile": mobile,
            "email": email,
            "password": password,
            "referral_code": referral_code or "",
        }
        logger.info("Register with extra fields failed, retrying with minimal payload.")
        return _post(EP_REGISTER, minimal_payload)

    return ok, data, status


def verify_otp(verification_id: str, otp: str) -> Tuple[bool, Dict[str, Any], int]:
    """POST /auth/verify-otp — completes registration and creates the account."""
    return _post(EP_VERIFY_OTP, {"verification_id": verification_id, "otp": otp})


def resend_otp(verification_id: str) -> Tuple[bool, Dict[str, Any], int]:
    """POST /auth/resend-otp — sends a fresh OTP for the same verification_id."""
    return _post(EP_RESEND_OTP, {"verification_id": verification_id})


def extract_verification_id(data: Dict[str, Any]) -> Optional[str]:
    """Pulls verification_id out of whatever shape /auth/register responded with."""
    if not isinstance(data, dict):
        return None
    for key in ("verification_id", "ver_id", "verificationId"):
        if data.get(key) not in (None, ""):
            return str(data[key])
    for wrap_key in ("data", "result"):
        val = data.get(wrap_key)
        if isinstance(val, dict):
            for key in ("verification_id", "ver_id", "verificationId"):
                if val.get(key) not in (None, ""):
                    return str(val[key])
    return None


# ─────────────────────────────────────────────
# MISC / LOOKUPS
# ─────────────────────────────────────────────
def get_states() -> Tuple[bool, List[str], int]:
    ok, data, status = _get(EP_STATES)
    return ok, _extract_string_list(data), status


def get_districts(state: str) -> Tuple[bool, List[str], int]:
    ok, data, status = _get(EP_DISTRICTS, params={"state": state})
    return ok, _extract_string_list(data), status


# ─────────────────────────────────────────────
# COURSES / BUNDLES
# ─────────────────────────────────────────────
def get_courses() -> Tuple[bool, List[Dict[str, Any]], int]:
    ok, data, status = _get(EP_COURSES, params={"page": 1, "limit": 50})
    return ok, _extract_list(data), status


def get_course_detail(slug: str) -> Tuple[bool, Dict[str, Any], int]:
    ok, data, status = _get(course_detail_url(slug))
    return ok, _extract_detail(data), status


def get_bundles() -> Tuple[bool, List[Dict[str, Any]], int]:
    ok, data, status = _get(EP_BUNDLES)
    return ok, _extract_list(data), status


def get_bundle_detail(slug: str) -> Tuple[bool, Dict[str, Any], int]:
    ok, data, status = _get(bundle_detail_url(slug))
    return ok, _extract_detail(data), status


# ─────────────────────────────────────────────
# CONTACT
# ─────────────────────────────────────────────
def submit_contact(name: str, mobile: str, email: str, subject: str, message: str) -> Tuple[bool, Dict[str, Any], int]:
    return _post(EP_CONTACT, {
        "name": name,
        "mobile": mobile,
        "email": email,
        "subject": subject,
        "message": message,
    })


# ─────────────────────────────────────────────
# Defensive response-shape helpers
# ─────────────────────────────────────────────
def _extract_list(data: Any) -> List[Any]:
    """Rozzgaar's APIs may wrap the payload as {"data": [...]}, {"result": [...]},
    {"data": {"courses": [...]}}, a bare list, or something else — handle every
    shape we might get back, and log unrecognised shapes instead of silently
    returning an empty list so real API problems are visible in the logs."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        list_keys = ("data", "result", "results", "courses", "bundles", "states", "districts", "items")
        for key in list_keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
        # one extra level of nesting, e.g. {"data": {"courses": [...], "pagination": {...}}}
        for key in ("data", "result"):
            val = data.get(key)
            if isinstance(val, dict):
                for inner_key in list_keys:
                    inner_val = val.get(inner_key)
                    if isinstance(inner_val, list):
                        return inner_val
        logger.warning(f"Could not find a list in response payload: {data}")
    return []


def _extract_detail(data: Any) -> Dict[str, Any]:
    """A course/bundle detail response may be a bare object, or wrapped
    as {"data": {...}}, {"course": {...}}, {"bundle": {...}}."""
    if isinstance(data, dict):
        for key in ("data", "course", "bundle", "result"):
            val = data.get(key)
            if isinstance(val, dict):
                return val
        return data
    return {}


def _extract_string_list(data: Any) -> List[str]:
    raw_list = _extract_list(data)
    out: List[str] = []
    for item in raw_list:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            for key in ("name", "state", "district", "title", "label", "value"):
                if item.get(key):
                    out.append(str(item[key]))
                    break
    return out
