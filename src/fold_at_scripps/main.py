"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fold_at_scripps.api.health import router as health_router
from fold_at_scripps.config import get_settings
from fold_at_scripps.db import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the database engine cleanly on application shutdown."""
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
