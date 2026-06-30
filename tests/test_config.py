"""Tests for application settings."""

from __future__ import annotations

import pytest

from fold_at_scripps.config import get_settings


def test_settings_defaults() -> None:
    settings = get_settings()
    assert settings.app_name == "fold@Scripps"
    assert settings.debug is False


def test_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLD_DEBUG", "true")
    monkeypatch.setenv("FOLD_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/test")
    settings = get_settings()
    assert settings.debug is True
    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/test"


def test_settings_session_defaults() -> None:
    settings = get_settings()
    assert settings.secret_key  # non-empty default for dev
    assert settings.session_https_only is False
