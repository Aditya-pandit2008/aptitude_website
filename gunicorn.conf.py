"""
gunicorn.conf.py
Gunicorn WSGI server configuration for production.

Usage:
    gunicorn -c gunicorn.conf.py "app:create_app()"
"""

import multiprocessing
import os

# ── Binding ──────────────────────────────────────────────────────────────────
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")

# ── Workers ───────────────────────────────────────────────────────────────────
# Rule of thumb: (2 × CPU cores) + 1
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"           # use 'gevent' or 'gthread' for async workloads
threads = int(os.getenv("GUNICORN_THREADS", 2))

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))
keepalive = 5
graceful_timeout = 30

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = "-"           # stdout
errorlog  = "-"           # stderr
loglevel  = os.getenv("LOG_LEVEL", "info")
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'
)

# ── Process naming ────────────────────────────────────────────────────────────
proc_name = "aptitude-api"

# ── Security ──────────────────────────────────────────────────────────────────
limit_request_line   = 4094
limit_request_fields = 100

# ── Reload (dev only) ────────────────────────────────────────────────────────
reload = os.getenv("FLASK_ENV") == "development"
