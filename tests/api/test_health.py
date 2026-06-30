"""Tests for health endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from fold_at_scripps.db import get_session
from fold_at_scripps.main import create_app


async def test_liveness() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.integration
async def test_readiness() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


async def test_readiness_db_unavailable() -> None:
    app = create_app()

    async def _failing_session():
        class _FailingSession:
            async def execute(self, *args, **kwargs):
                raise SQLAlchemyError("simulated outage")

        yield _FailingSession()

    app.dependency_overrides[get_session] = _failing_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "database unavailable"}
