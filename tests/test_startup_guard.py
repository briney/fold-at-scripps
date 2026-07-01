"""Tests for the secret-key startup guard and logging configuration."""

from __future__ import annotations

import logging

import pytest

from fold_at_scripps.config import get_settings
from fold_at_scripps.logging_config import configure_logging
from fold_at_scripps.main import create_app


def test_create_app_rejects_dev_secret_when_not_debug(monkeypatch):
    monkeypatch.setenv("FOLD_SECRET_KEY", "dev-insecure-secret-change-me")
    monkeypatch.setenv("FOLD_DEBUG", "false")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="FOLD_SECRET_KEY"):
        create_app()


def test_create_app_allows_dev_secret_in_debug(monkeypatch):
    monkeypatch.setenv("FOLD_SECRET_KEY", "dev-insecure-secret-change-me")
    monkeypatch.setenv("FOLD_DEBUG", "true")
    get_settings.cache_clear()
    assert create_app() is not None


def test_create_app_allows_real_secret(monkeypatch):
    monkeypatch.setenv("FOLD_SECRET_KEY", "a-real-long-secret")
    monkeypatch.setenv("FOLD_DEBUG", "false")
    get_settings.cache_clear()
    assert create_app() is not None


def test_configure_logging_sets_level():
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging("INFO")
    assert logging.getLogger().level == logging.INFO
