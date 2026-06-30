"""Tests for the async database engine."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from fold_at_scripps.db import get_sessionmaker


@pytest.mark.integration
async def test_engine_connects() -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
