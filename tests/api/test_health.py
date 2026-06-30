"""Tests for health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from fold_at_scripps.main import create_app


def test_liveness() -> None:
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
