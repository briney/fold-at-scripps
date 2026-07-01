"""Tests for SPA static serving + API-route precedence."""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>fold@Scripps</title>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    return dist


def _client(dist: str, monkeypatch) -> AsyncClient:
    monkeypatch.setenv("FOLD_SECRET_KEY", "a-real-long-secret")
    monkeypatch.setenv("FOLD_FRONTEND_DIST", dist)
    get_settings.cache_clear()
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_serves_index_for_unknown_client_route(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    async with _client(str(dist), monkeypatch) as client:
        # /dashboard/x is a client-side route with no API handler; must fall back
        # to index.html (a /runs/... path would match /runs/{id} and hit the DB).
        resp = await client.get("/dashboard/x")
        assert resp.status_code == 200
        assert "fold@Scripps" in resp.text


async def test_serves_real_asset(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    async with _client(str(dist), monkeypatch) as client:
        resp = await client.get("/assets/app.js")
        assert resp.status_code == 200
        assert "console.log" in resp.text


async def test_api_route_not_shadowed(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    async with _client(str(dist), monkeypatch) as client:
        # openapi.json is a framework route with no DB dependency; must stay JSON.
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")


async def test_boots_without_dist(tmp_path, monkeypatch):
    async with _client(str(tmp_path / "missing"), monkeypatch) as client:
        assert (await client.get("/openapi.json")).status_code == 200
        # No SPA fallback registered -> unknown GET is a 404, not index.html.
        assert (await client.get("/nope")).status_code == 404
