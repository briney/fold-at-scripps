"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import fold_at_scripps.db as _db_module
from fold_at_scripps.config import get_settings
from fold_at_scripps.models import Base


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


def _database_reachable() -> bool:
    """Return True if the configured Postgres accepts a connection."""

    async def _probe() -> bool:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except (SQLAlchemyError, OSError):
            return False
        finally:
            await engine.dispose()

    return asyncio.run(_probe())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration-marked tests when the database is unreachable."""
    if _database_reachable():
        return
    _reason = (
        "Postgres unreachable; run `docker compose up -d postgres` to enable integration tests"
    )
    skip_integration = pytest.mark.skip(reason=_reason)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session against a freshly-created schema; drop all tables afterward."""
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            yield session
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
