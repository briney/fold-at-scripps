"""Foreground entry points invoked by the systemd user units."""

from __future__ import annotations

import uvicorn

from fold_at_scripps.config import get_settings
from fold_at_scripps.logging_config import configure_logging


def serve(host: str = "0.0.0.0", port: int | None = None) -> None:
    """Run the API with uvicorn in the foreground."""
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run("fold_at_scripps.main:app", host=host, port=port or settings.api_port)


def scheduler() -> None:
    """Run the scheduler daemon in the foreground."""
    from fold_at_scripps.scheduler.main import main as scheduler_main

    scheduler_main()
