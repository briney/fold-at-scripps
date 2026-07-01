"""Tests for the admin bootstrap CLI."""

from __future__ import annotations

import asyncio
import shutil

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app
from fold_at_scripps.models import AllowedEmail, Tool, User, UserRole, UserStatus

pytestmark = pytest.mark.integration

runner = CliRunner()


async def test_create_admin_creates_active_admin(db_session: AsyncSession) -> None:
    result = await asyncio.to_thread(
        runner.invoke,
        app,
        [
            "admin",
            "create-admin",
            "--email",
            "boss@scripps.edu",
            "--password",
            "supersecret",
            "--display-name",
            "Boss",
        ],
    )
    assert result.exit_code == 0, result.output

    user = await db_session.scalar(select(User).where(User.email == "boss@scripps.edu"))
    assert user is not None
    assert user.role is UserRole.ADMIN
    assert user.status is UserStatus.ACTIVE
    allowed = await db_session.scalar(
        select(AllowedEmail).where(AllowedEmail.email == "boss@scripps.edu")
    )
    assert allowed is not None


async def test_create_admin_rejects_duplicate(db_session: AsyncSession) -> None:
    args = [
        "admin",
        "create-admin",
        "--email",
        "boss@scripps.edu",
        "--password",
        "supersecret",
        "--display-name",
        "Boss",
    ]
    first = await asyncio.to_thread(runner.invoke, app, args)
    assert first.exit_code == 0
    second = await asyncio.to_thread(runner.invoke, app, args)
    assert second.exit_code == 1


@pytest.mark.skipif(shutil.which("autobio") is None, reason="autobio CLI not on PATH")
async def test_sync_catalog_populates_tools(db_session: AsyncSession) -> None:
    result = await asyncio.to_thread(runner.invoke, app, ["catalog", "sync"])
    assert result.exit_code == 0, result.output
    count = await db_session.scalar(select(func.count()).select_from(Tool))
    assert count > 0
