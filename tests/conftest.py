"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fold_at_scripps.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Ensure each test sees freshly-loaded settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
