"""Tests for the request body-size-limit middleware."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app


def _client(monkeypatch, max_bytes: int) -> AsyncClient:
    monkeypatch.setenv("FOLD_SECRET_KEY", "a-real-long-secret")
    monkeypatch.setenv("FOLD_MAX_UPLOAD_BYTES", str(max_bytes))
    get_settings.cache_clear()
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_rejects_over_limit_body(monkeypatch):
    async with _client(monkeypatch, max_bytes=10) as client:
        # POST to an unknown route with a body over the cap -> 413 before routing/DB.
        resp = await client.post("/nope", content=b"x" * 100)
        assert resp.status_code == 413
        assert resp.json()["detail"]


async def test_allows_under_limit_body(monkeypatch):
    async with _client(monkeypatch, max_bytes=1_000_000) as client:
        # Small body to an unknown route -> passes the middleware -> 404 (not 413).
        resp = await client.post("/nope", content=b"small")
        assert resp.status_code == 404
