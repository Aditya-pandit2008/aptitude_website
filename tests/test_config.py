import importlib
import os

import os

import pytest

import config


def test_default_sqlite_path_uses_instance_dir(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")
    importlib.reload(config)

    expected = os.path.join("instance", "placement_prep.db")
    actual = os.path.normpath(config.Config.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", ""))
    assert actual.endswith(expected)


def test_production_requires_external_database(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "prod-jwt-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        config.ProductionConfig()
