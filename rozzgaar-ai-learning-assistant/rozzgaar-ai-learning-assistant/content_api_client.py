"""
content_api_client.py
─────────────────────────────────────────────────────────────
Fetches real chapter content from the live Rozzgaar.in API:

  GET {ROZZGAAR_API_BASE}/courses/{course_slug}/contents
  Authorization: Bearer <ROZZGAAR_API_KEY>

Response shape (confirmed from a real sample response):

{
  "status": "success",
  "message": "Success",
  "data": {
    "Module 1": [
      {
        "id": 1,
        "module_name": "Module 1",
        "chapter_name": "Chapter 1: Building the Founder's Mind ...",
        "chapter_content": "<h4>...</h4><p>...</p>...",
        "pdf_path": null,
        "video_path": "m1c1.mp4",
        "video_url": "https://.../m1c1.mp4",
        "pdf_url": null
      },
      ...
    ],
    "Module 2": [ ... ],
    ...
  }
}

`id` is globally unique across the whole course (not reset per module).
`chapter_content` is raw HTML and must be converted to plain text before
being sent to the LLM.
"""

import threading
import time
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException

from config import (
    logger,
    ROZZGAAR_API_KEY,
    REQUEST_TIMEOUT,
    CONTENT_CACHE_TTL_SECONDS,
    course_contents_url,
)

_HEADERS = {"Authorization": f"Bearer {ROZZGAAR_API_KEY}"}


def html_to_text(html: Optional[str]) -> str:
    """Converts the chapter's HTML content into clean, structured plain text
    (headings, paragraphs, bullet lists, and tables) suitable for an LLM prompt."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    lines = []

    for node in soup.contents:
        name = getattr(node, "name", None)

        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"\n{text}\n")

        elif name == "p":
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(text + "\n")

        elif name in ("ul", "ol"):
            for li in node.find_all("li", recursive=False):
                text = li.get_text(" ", strip=True)
                if text:
                    lines.append(f"- {text}")
            lines.append("")

        elif name == "table":
            for row in node.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
                if cells:
                    lines.append(" | ".join(cells))
            lines.append("")

        elif name is not None:
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(text)

        else:
            text = str(node).strip()
            if text:
                lines.append(text)

    return "\n".join(lines).strip()


class ContentApiClient:
    def __init__(self, cache_ttl_seconds: int):
        self._cache_ttl = cache_ttl_seconds
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _fetch_course(self, course_slug: str) -> Dict[str, Any]:
        """Returns the raw `data` dict for a course: {module_name: [chapters...]}."""
        with self._lock:
            cached = self._cache.get(course_slug)
            if cached and (time.time() - cached["fetched_at"]) < self._cache_ttl:
                return cached["data"]

        url = course_contents_url(course_slug)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.exception(f"GET {url} failed")
            raise HTTPException(status_code=502, detail=f"Could not reach course content API: {exc}")

        if resp.status_code != 200:
            logger.warning(f"GET {url} -> {resp.status_code} | {resp.text[:300]}")
            raise HTTPException(status_code=502, detail=f"Course content API returned {resp.status_code}")

        try:
            body = resp.json()
        except ValueError:
            raise HTTPException(status_code=502, detail="Course content API returned invalid JSON")

        if str(body.get("status", "")).lower() != "success":
            raise HTTPException(status_code=502, detail=f"Course content API error: {body.get('message')}")

        data = body.get("data", {})
        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="Unexpected course content API response shape")

        with self._lock:
            self._cache[course_slug] = {"data": data, "fetched_at": time.time()}

        return data

    def get_chapter(self, course_id: str, module_id: str, chapter_id: str) -> Dict[str, str]:
        data = self._fetch_course(course_id)

        chapters = data.get(module_id)
        if chapters is None:
            raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found in course '{course_id}'")

        chapter = next((c for c in chapters if str(c.get("id")) == str(chapter_id)), None)
        if chapter is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter id '{chapter_id}' not found in module '{module_id}' of course '{course_id}'",
            )

        return {
            "module_name": chapter.get("module_name", module_id),
            "chapter_name": chapter.get("chapter_name", ""),
            "content": html_to_text(chapter.get("chapter_content", "")),
        }

    def invalidate(self, course_id: str):
        with self._lock:
            self._cache.pop(course_id, None)


content_api_client = ContentApiClient(cache_ttl_seconds=CONTENT_CACHE_TTL_SECONDS)
