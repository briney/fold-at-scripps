"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from fold_at_scripps.api.admin import router as admin_router
from fold_at_scripps.api.auth import router as auth_router
from fold_at_scripps.api.health import router as health_router
from fold_at_scripps.api.runs import router as runs_router
from fold_at_scripps.api.tools import router as tools_router
from fold_at_scripps.config import Settings, get_settings
from fold_at_scripps.db import dispose_engine
from fold_at_scripps.logging_config import configure_logging
from fold_at_scripps.middleware import BodySizeLimitMiddleware

_DEV_SECRET_KEY = "dev-insecure-secret-change-me"


def _require_production_secret(settings: Settings) -> None:
    """Refuse to boot with the insecure dev secret outside debug mode."""
    if not settings.debug and settings.secret_key == _DEV_SECRET_KEY:
        raise RuntimeError(
            "FOLD_SECRET_KEY is the insecure development default. Set a real "
            "FOLD_SECRET_KEY in production (or FOLD_DEBUG=true for local dev)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the database engine cleanly on application shutdown."""
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)
    _require_production_secret(settings)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.session_https_only,
        same_site="lax",
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(tools_router)
    app.include_router(runs_router)
    app.include_router(admin_router)
    _mount_spa(app, Path(settings.frontend_dist))
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: real files, else index.html (client-side routing)."""
    if not dist.is_dir():
        return
    index_file = dist / "index.html"
    dist_root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index_file)


app = create_app()
