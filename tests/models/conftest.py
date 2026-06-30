"""Fixtures for model tests: a fresh schema and session per test (requires Postgres)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fold_at_scripps.config import get_settings
from fold_at_scripps.models import Base


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
