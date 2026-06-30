"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import fold_at_scripps.db as _db_module
from fold_at_scripps.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Ensure each test sees freshly-loaded settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_db_singletons() -> Iterator[None]:
    """Reset the module-level engine/sessionmaker between tests.

    The async engine is bound to the event loop at creation time.  pytest-asyncio
    creates a new loop per test function, so any engine created in a previous test
    would be attached to a closed loop.  Resetting the globals forces re-creation
    on the next call within the fresh loop.
    """
    _db_module._engine = None
    _db_module._sessionmaker = None
    yield
    _db_module._engine = None
    _db_module._sessionmaker = None
