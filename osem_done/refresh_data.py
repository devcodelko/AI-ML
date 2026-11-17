import fcntl
import logging
import os
import sys

import config
import crawler

MIN_KEEP_RATIO = 0.5

logger = logging.getLogger("refresh_data")


def _acquire_lock(lock_path):
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _release_lock(handle):
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


def _ordered(chunks, urls):
    position = {url: index for index, url in enumerate(urls)}
    return sorted(chunks, key=lambda chunk: position.get(chunk.get("url"), len(position)))


def refresh(urls=None, cache_path=None, lock_path=None):
    """Re-crawl the configured sites and atomically replace the chunk cache.

    Returns a process exit code: 0 on success (or when another refresh already
    holds the lock), 1 when the cache was deliberately left untouched.
    """
    urls = list(urls if urls is not None else config.SITE_URLS)
    cache_path = cache_path or config.CACHE_PATH
    lock_path = lock_path or config.REFRESH_LOCK_PATH

    lock = _acquire_lock(lock_path)
    if lock is None:
        logger.info("Another refresh is already running; exiting without changes")
        return 0
    try:
        previous = list(crawler.load_chunk_cache(cache_path))
        results = crawler.crawl_urls(urls)

        fresh_urls = [url for url in urls if results.get(url)]
        failed_urls = [url for url in urls if not results.get(url)]
        if not fresh_urls:
            logger.error("Crawl produced no content from any of %d URLs; cache left untouched", len(urls))
            return 1

        new_chunks = [chunk for url in fresh_urls for chunk in results[url]]
        retained = [chunk for chunk in previous if chunk.get("url") in set(failed_urls)]
        merged = _ordered(new_chunks + retained, urls)

        if previous and len(merged) < len(previous) * MIN_KEEP_RATIO:
            logger.error(
                "Refreshed cache would shrink from %d to %d chunks (below %.0f%%); cache left untouched",
                len(previous),
                len(merged),
                MIN_KEEP_RATIO * 100,
            )
            return 1

        crawler.save_chunk_cache(merged, cache_path)
        logger.info(
            "Cache refreshed: %d chunks (%d new, %d retained) from %d/%d URLs; failed: %s",
            len(merged),
            len(new_chunks),
            len(retained),
            len(fresh_urls),
            len(urls),
            ", ".join(failed_urls) if failed_urls else "none",
        )
        return 0
    except Exception:
        logger.exception("Refresh failed; cache left untouched")
        return 1
    finally:
        _release_lock(lock)


def main():
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return refresh()


if __name__ == "__main__":
    sys.exit(main())
