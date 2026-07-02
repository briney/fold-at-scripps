"""Shared pytest fixtures."""

from __future__ import annotations

import os

# The Plan 10 secret-key guard refuses the dev-default secret when not in debug.
# Provide a non-dev test secret at collection time so `create_app()` (run at
# import of fold_at_scripps.main) does not raise during the test suite.
os.environ.setdefault("FOLD_SECRET_KEY", "test-secret-not-for-production")

import asyncio
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import fold_at_scripps.db as _db_module
from fold_at_scripps.config import get_settings
from fold_at_scripps.models import Base


def _derive_test_url(base_url: str) -> str:
    """Return the isolated test-database URL (db name suffixed with ``_test``)."""
    parts = urlsplit(base_url)
    name = parts.path.lstrip("/")
    if name.endswith("_test"):
        return base_url
    return urlunsplit(parts._replace(path=f"/{name}_test"))


def _maintenance_url(base_url: str) -> str:
    """Return a URL to the ``postgres`` maintenance DB on the same server."""
    return urlunsplit(urlsplit(base_url)._replace(path="/postgres"))


# Redirect ALL database access (fixtures, Alembic via migrations/env.py, the
# scheduler-lock test) to an isolated ``*_test`` database so the suite never
# touches — or wipes — the developer's live database. The override must be set
# before anything reads Settings; get_settings() is cache-cleared per test.
os.environ["FOLD_DATABASE_URL"] = _derive_test_url(get_settings().database_url)
get_settings.cache_clear()


async def _ensure_database(maintenance_url: str, db_name: str) -> None:
    """Create ``db_name`` on the server if it does not already exist."""
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await engine.dispose()


def pytest_configure(config: pytest.Config) -> None:
    """Guard against a non-test DB and create the isolated test database."""
    get_settings.cache_clear()
    url = get_settings().database_url
    db_name = urlsplit(url).path.lstrip("/")
    if not db_name.endswith("_test"):
        raise pytest.UsageError(
            f"Refusing to run: integration tests must target a *_test database, but "
            f"settings resolve to {db_name!r}. Check FOLD_DATABASE_URL / .env."
        )
    try:
        asyncio.run(_ensure_database(_maintenance_url(url), db_name))
    except (SQLAlchemyError, OSError):
        # Server unreachable: skip creation; integration tests get skipped below.
        pass


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
