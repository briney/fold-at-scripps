"""Tests for the Tool model."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Tool

pytestmark = pytest.mark.integration


async def test_tool_defaults_and_schema_round_trip(db_session: AsyncSession) -> None:
    schema = {"properties": {"num_sequences": {"type": "integer"}}}
    tool = Tool(
        name="proteinmpnn", version="1.0.0", category="inverse_folding", input_schema=schema
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    assert tool.id is not None
    assert tool.gpu_count == 1
    assert tool.enabled is True
    assert tool.input_schema == schema


async def test_tool_name_version_unique(db_session: AsyncSession) -> None:
    db_session.add(Tool(name="esmfold", version="1.0.0", category="structure", input_schema={}))
    await db_session.commit()
    db_session.add(Tool(name="esmfold", version="1.0.0", category="structure", input_schema={}))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_tool_same_name_different_version_allowed(db_session: AsyncSession) -> None:
    db_session.add(Tool(name="boltz", version="1.0.0", category="structure", input_schema={}))
    db_session.add(Tool(name="boltz", version="2.0.0", category="structure", input_schema={}))
    await db_session.commit()
    count = len((await db_session.execute(select(Tool))).scalars().all())
    assert count == 2
