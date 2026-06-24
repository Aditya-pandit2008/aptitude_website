"""
config.py
Application configuration for different environments.
Easily switch between SQLite (dev) and MySQL/Postgres (prod) via DATABASE_URL.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration shared across all environments."""

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY     = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-in-production")

    JWT_ACCESS_TOKEN_EXPIRES  = timedelta(hours=1)      # tightened from 12h
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # JWT token blocklist (logout support)
    JWT_BLACKLIST_ENABLED      = True
    JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]

    # Secure session cookies
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = "Lax"
    SESSION_COOKIE_SECURE    = os.getenv("FLASK_ENV") == "production"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    # Set RATELIMIT_STORAGE_URI=redis://localhost:6379/0 in production
    # Falls back to in-memory (fine for single-worker dev, not multi-worker prod)
    RATELIMIT_STORAGE_URI    = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT        = "200 per hour"
    RATELIMIT_HEADERS_ENABLED = True

    # ── Database ──────────────────────────────────────────────────────────────
    _raw_db_url = os.getenv("DATABASE_URL", "sqlite:///placement_prep.db").split("#")[0].strip()
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS  = {
        "pool_pre_ping": True,    # reconnect on stale connections
        "pool_recycle":  300,     # recycle connections every 5 min
    }

    # ── Groq AI ───────────────────────────────────────────────────────────────
    GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL        = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama3-8b-8192")

    # AI response cache TTL (seconds)
    AI_CACHE_TTL     = int(os.getenv("AI_CACHE_TTL", "3600"))   # 1 hour
    AI_CACHE_MAXSIZE = int(os.getenv("AI_CACHE_MAXSIZE", "256"))

    # ── XP / Gamification ─────────────────────────────────────────────────────
    XP_PER_CORRECT_ANSWER    = 10
    XP_PER_TEST_COMPLETION   = 25
    XP_STREAK_BONUS          = 5
    PASSING_ACCURACY_THRESHOLD = 70


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False    # set True to log SQL queries during dev
    RATELIMIT_ENABLED = False  # disable rate limiting in development


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI   = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES  = timedelta(minutes=5)
    RATELIMIT_ENABLED         = False   # disable rate limiting in tests
    WTF_CSRF_ENABLED          = False


class ProductionConfig(Config):
    DEBUG = False

    def __init__(self):
        # Enforce that secret keys are explicitly set in production
        if self.SECRET_KEY == "dev-secret-key-change-in-production":
            raise RuntimeError(
                "SECRET_KEY env variable must be set in production. "
                "Do not use the default dev key."
            )
        if self.JWT_SECRET_KEY == "dev-jwt-secret-change-in-production":
            raise RuntimeError(
                "JWT_SECRET_KEY env variable must be set in production."
            )

    SESSION_COOKIE_SECURE = True


# Map string names → config classes (used in app.py)
config_map = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
