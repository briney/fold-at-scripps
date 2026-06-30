"""Tests for the Artifact model."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Artifact, Run, Tool, User

pytestmark = pytest.mark.integration


async def _make_run(session: AsyncSession) -> Run:
    user = User(email="a@scripps.edu", display_name="A", hashed_password="x")
    tool = Tool(name="esmfold", version="1.0.0", category="structure", input_schema={})
    session.add_all([user, tool])
    await session.commit()
    run = Run(user_id=user.id, tool_id=tool.id, params={})
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_artifact_creation(db_session: AsyncSession) -> None:
    run = await _make_run(db_session)
    artifact = Artifact(
        run_id=run.id, name="design_0.pdb", path="outputs/design_0.pdb", size_bytes=2048
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    assert artifact.id is not None
    assert artifact.content_type is None
    assert artifact.size_bytes == 2048
    await db_session.refresh(artifact, attribute_names=["run"])
    assert artifact.run.id == run.id


async def test_artifact_cascade_delete_with_run(db_session: AsyncSession) -> None:
    run = await _make_run(db_session)
    db_session.add(Artifact(run_id=run.id, name="a.txt", path="outputs/a.txt"))
    await db_session.commit()
    fetched_run = await db_session.get(Run, run.id)
    await db_session.delete(fetched_run)
    await db_session.commit()
    remaining = (await db_session.execute(select(func.count()).select_from(Artifact))).scalar_one()
    assert remaining == 0
