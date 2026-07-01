"""Tests for the request body-size-limit middleware."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app
from fold_at_scripps.middleware import BodySizeLimitMiddleware


def _request_with_content_length(value: str) -> Request:
    """Build a minimal HTTP Request carrying a raw Content-Length header."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/x",
            "headers": [(b"content-length", value.encode())],
        }
    )


async def _passthrough(_request: Request) -> Response:
    return PlainTextResponse("ok")


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


async def test_malformed_content_length_rejected():
    # A non-numeric Content-Length must NOT bypass the cap: reject with 400,
    # never call downstream.
    mw = BodySizeLimitMiddleware(app=None, max_bytes=1000)  # type: ignore[arg-type]
    called = False

    async def call_next(request: Request) -> Response:
        nonlocal called
        called = True
        return await _passthrough(request)

    resp = await mw.dispatch(_request_with_content_length("not-a-number"), call_next)
    assert resp.status_code == 400
    assert called is False


async def test_negative_content_length_rejected():
    mw = BodySizeLimitMiddleware(app=None, max_bytes=1000)  # type: ignore[arg-type]
    resp = await mw.dispatch(_request_with_content_length("-5"), _passthrough)
    assert resp.status_code == 400
