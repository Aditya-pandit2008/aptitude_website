"""
utils/logging_config.py
Structured JSON logging for production environments.

Usage in app.py:
    from utils.logging_config import configure_logging
    configure_logging(app)
"""

import json
import logging
import time
import uuid
from flask import Flask, g, request


class JSONFormatter(logging.Formatter):
    """
    Format log records as single-line JSON objects.
    Compatible with gunicorn's error log and most cloud logging ingestion pipelines.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }

        # Attach request context if available
        try:
            log_entry["request_id"] = g.get("request_id", "-")
            log_entry["path"]       = request.path
            log_entry["method"]     = request.method
        except RuntimeError:
            pass   # outside request context

        # Attach exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging(app: Flask) -> None:
    """
    Attach a JSON formatter to the Flask app logger and register
    before/after request hooks for structured request-level logging.
    """
    # Only apply JSON logging in non-debug mode (use plain logging in dev)
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        app.logger.handlers = [handler]
        app.logger.setLevel(logging.INFO)
        app.logger.propagate = False

    @app.before_request
    def _before_request():
        """Assign a unique request ID and record start time."""
        g.request_id  = str(uuid.uuid4())
        g.request_start = time.perf_counter()

    @app.after_request
    def _after_request(response):
        """Log method, path, status, and duration after each response."""
        duration_ms = round((time.perf_counter() - g.get("request_start", 0)) * 1000, 2)
        app.logger.info(
            "%s %s → %d  [%.2fms]  req_id=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            g.get("request_id", "-"),
        )
        # Expose request ID to clients for debugging
        response.headers["X-Request-ID"] = g.get("request_id", "-")
        return response
