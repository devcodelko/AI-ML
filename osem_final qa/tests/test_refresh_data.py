import os
import pickle

import crawler
import refresh_data


def _chunks(url, count):
    return [{"url": url, "text": f"{url} chunk {index}"} for index in range(count)]


def _write_cache(path, chunks):
    with open(path, "wb") as cache_file:
        pickle.dump(chunks, cache_file)


def _read_cache(path):
    with open(path, "rb") as cache_file:
        return pickle.load(cache_file)


def test_refresh_replaces_cache_and_keeps_failed_urls(tmp_path, monkeypatch):
    cache = str(tmp_path / "site_chunks.pkl")
    lock = str(tmp_path / ".refresh.lock")
    urls = ["https://a.example/", "https://b.example/"]
    _write_cache(cache, _chunks(urls[0], 3) + _chunks(urls[1], 3))
    monkeypatch.setattr(
        crawler, "crawl_urls", lambda u: {urls[0]: _chunks(urls[0], 4), urls[1]: []}
    )

    assert refresh_data.refresh(urls, cache, lock) == 0

    result = _read_cache(cache)
    assert [c["url"] for c in result].count(urls[0]) == 4
    assert [c["url"] for c in result].count(urls[1]) == 3
    assert result[0]["url"] == urls[0]


def test_refresh_refuses_when_nothing_was_crawled(tmp_path, monkeypatch):
    cache = str(tmp_path / "site_chunks.pkl")
    urls = ["https://a.example/"]
    original = _chunks(urls[0], 3)
    _write_cache(cache, original)
    monkeypatch.setattr(crawler, "crawl_urls", lambda u: {urls[0]: []})

    assert refresh_data.refresh(urls, cache, str(tmp_path / ".lock")) == 1
    assert _read_cache(cache) == original


def test_refresh_refuses_drastic_shrink(tmp_path, monkeypatch):
    cache = str(tmp_path / "site_chunks.pkl")
    urls = ["https://a.example/"]
    original = _chunks(urls[0], 10)
    _write_cache(cache, original)
    monkeypatch.setattr(crawler, "crawl_urls", lambda u: {urls[0]: _chunks(urls[0], 2)})

    assert refresh_data.refresh(urls, cache, str(tmp_path / ".lock")) == 1
    assert _read_cache(cache) == original


def test_refresh_creates_cache_when_missing(tmp_path, monkeypatch):
    cache = str(tmp_path / "nested" / "site_chunks.pkl")
    urls = ["https://a.example/"]
    monkeypatch.setattr(crawler, "crawl_urls", lambda u: {urls[0]: _chunks(urls[0], 2)})

    assert refresh_data.refresh(urls, cache, str(tmp_path / ".lock")) == 0
    assert len(_read_cache(cache)) == 2
    assert oct(os.stat(cache).st_mode & 0o777) == "0o644"


def test_concurrent_refresh_exits_cleanly_without_changes(tmp_path, monkeypatch):
    cache = str(tmp_path / "site_chunks.pkl")
    lock_path = str(tmp_path / ".refresh.lock")
    urls = ["https://a.example/"]
    original = _chunks(urls[0], 3)
    _write_cache(cache, original)
    monkeypatch.setattr(
        crawler, "crawl_urls", lambda u: (_ for _ in ()).throw(AssertionError("must not crawl"))
    )

    held = refresh_data._acquire_lock(lock_path)
    try:
        assert refresh_data.refresh(urls, cache, lock_path) == 0
    finally:
        refresh_data._release_lock(held)
    assert _read_cache(cache) == original


def test_refresh_leaves_no_temp_files(tmp_path, monkeypatch):
    cache = str(tmp_path / "site_chunks.pkl")
    urls = ["https://a.example/"]
    monkeypatch.setattr(crawler, "crawl_urls", lambda u: {urls[0]: _chunks(urls[0], 2)})
    refresh_data.refresh(urls, cache, str(tmp_path / ".lock"))
    assert [name for name in os.listdir(tmp_path) if name.endswith(".tmp")] == []


def test_load_chunk_cache_picks_up_new_file(tmp_path):
    cache = str(tmp_path / "site_chunks.pkl")
    assert crawler.load_chunk_cache(cache) == []
    crawler.save_chunk_cache(_chunks("https://a.example/", 2), cache)
    assert len(crawler.load_chunk_cache(cache)) == 2
    crawler.save_chunk_cache(_chunks("https://a.example/", 5), cache)
    os.utime(cache, (os.path.getmtime(cache) + 5, os.path.getmtime(cache) + 5))
    assert len(crawler.load_chunk_cache(cache)) == 5
