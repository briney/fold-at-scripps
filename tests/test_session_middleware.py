"""Tests that the app installs session middleware."""

from __future__ import annotations

from starlette.middleware.sessions import SessionMiddleware

from fold_at_scripps.main import create_app


def test_session_middleware_installed() -> None:
    app = create_app()
    assert any(m.cls is SessionMiddleware for m in app.user_middleware)
