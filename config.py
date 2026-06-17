"""
config.py
Application configuration for different environments.
Easily switch between SQLite (dev) and MySQL (prod) by changing SQLALCHEMY_DATABASE_URI.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration shared across all environments."""

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-key-change-in-production"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "dev-jwt-secret-change-in-production"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite is used only as a local-dev fallback. It will NOT work on Vercel
    # (read-only filesystem) — set DATABASE_URL in the Vercel dashboard to a
    # hosted Postgres connection string in production.
    _raw_db_url = os.getenv("DATABASE_URL", "sqlite:///placement_prep.db")
    # Some providers (Heroku-style, some copy/paste Postgres strings) hand out
    # "postgres://", but SQLAlchemy 1.4+ requires "postgresql://".
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,           # reconnect on stale connections
        "pool_recycle": 300,             # recycle connections every 5 min
    }

    # ── Groq AI ───────────────────────────────────────────────────────────────
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # ── XP / Gamification ─────────────────────────────────────────────────────
    XP_PER_CORRECT_ANSWER = 10
    XP_PER_TEST_COMPLETION = 25
    XP_STREAK_BONUS = 5          # bonus per day of active streak
    PASSING_ACCURACY_THRESHOLD = 70   # % accuracy considered "strong" topic


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False       # set True to log SQL queries


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


class ProductionConfig(Config):
    DEBUG = False
    # Override with env variables in production


# Map string names → config classes (used in app.py)
config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
