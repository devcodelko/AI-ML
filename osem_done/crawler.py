import concurrent.futures
import logging
import os
import pickle
import tempfile
import threading

import requests
import urllib3
from bs4 import BeautifulSoup

import config
import http_utils

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

MIN_TEXT_LENGTH = 200

_session = http_utils.build_session(
    config.CRAWL_MAX_RETRIES, status_forcelist=(429, 500, 502, 503, 504)
)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

_cache_lock = threading.Lock()
_cache_state = {"path": None, "mtime": None, "chunks": []}


def _get(url, verify):
    response = _session.get(
        url,
        headers=HEADERS,
        timeout=(config.HTTP_CONNECT_TIMEOUT, config.CRAWL_READ_TIMEOUT),
        verify=verify,
    )
    response.raise_for_status()
    return response.text


def _fetch_static(url):
    try:
        return _get(url, verify=True)
    except requests.exceptions.SSLError:
        if not config.CRAWLER_ALLOW_INSECURE_SSL:
            logger.warning("SSL verification failed for %s; skipping (CRAWLER_ALLOW_INSECURE_SSL is off)", url)
            return ""
        logger.warning("SSL verification failed for %s; retrying without verification", url)
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            return _get(url, verify=False)
        except requests.exceptions.RequestException as exc:
            logger.warning("Insecure retry failed for %s: %s", url, exc)
            return ""
    except requests.exceptions.RequestException as exc:
        logger.warning("Fetch failed for %s: %s", url, exc)
        return ""


def fetch_url(url):
    return _fetch_static(url)


def fetch_url_safe(url, overall_timeout=12):
    future = _executor.submit(fetch_url, url)
    try:
        return future.result(timeout=overall_timeout)
    except concurrent.futures.TimeoutError:
        logger.warning("Fetch timed out for %s", url)
        return ""
    except Exception:
        logger.exception("Unexpected fetch error for %s", url)
        return ""


def extract_text(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    cleaned = " ".join(text.split())
    return cleaned


def chunk_text(text, chunk_size=800, overlap=100):
    chunks = []
    if not text:
        return chunks
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = end - overlap
    return chunks


def crawl_urls(urls, max_workers=6, overall_timeout=20, chunk_size=None, overlap=None):
    """Fetch every URL and return {url: [chunk dicts]}.

    A URL whose page could not be fetched, or produced less than MIN_TEXT_LENGTH
    characters of text, maps to an empty list so callers can treat it as failed.
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    overlap = config.CHUNK_OVERLAP if overlap is None else overlap
    results = {url: [] for url in urls}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_url_safe, url, overall_timeout): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                text = extract_text(future.result())
            except Exception:
                logger.exception("Failed to process %s", url)
                text = ""
            if len(text) < MIN_TEXT_LENGTH:
                continue
            results[url] = [{"url": url, "text": chunk} for chunk in chunk_text(text, chunk_size, overlap)]
    return results


def save_chunk_cache(chunks, cache_path):
    """Atomically replace the chunk cache so readers never see a partial file."""
    directory = os.path.dirname(cache_path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".site_chunks.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as cache_file:
            pickle.dump(chunks, cache_file, protocol=pickle.HIGHEST_PROTOCOL)
            cache_file.flush()
            os.fsync(cache_file.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, cache_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_chunk_cache(cache_path):
    """Return the cached chunks, re-reading the file only when its mtime changes.

    The returned list is shared between callers and must not be mutated.
    """
    try:
        mtime = os.path.getmtime(cache_path)
    except OSError:
        return []
    with _cache_lock:
        if _cache_state["path"] == cache_path and _cache_state["mtime"] == mtime:
            return _cache_state["chunks"]
    try:
        with open(cache_path, "rb") as cache_file:
            chunks = pickle.load(cache_file)
    except (OSError, pickle.PickleError, EOFError, AttributeError, ImportError):
        return []
    if not isinstance(chunks, list):
        return []
    with _cache_lock:
        _cache_state["path"] = cache_path
        _cache_state["mtime"] = mtime
        _cache_state["chunks"] = chunks
    return chunks
