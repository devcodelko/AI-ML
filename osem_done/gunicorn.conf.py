import os

bind = f"0.0.0.0:{os.environ.get('PORT') or '8000'}"
workers = int(os.environ.get("WEB_CONCURRENCY") or 2)
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS") or 4)
timeout = 90
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = (os.environ.get("LOG_LEVEL") or "info").lower()
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None
