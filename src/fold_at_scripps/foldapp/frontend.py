"""Frontend build and DB migration shell-outs."""

from __future__ import annotations

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run


def build_frontend(paths: FoldappPaths, *, dry_run: bool = False, runner=run) -> None:
    """Build the SPA via the Docker ``dist`` stage into ``frontend/dist``."""
    runner(
        [
            "docker",
            "build",
            "--target",
            "dist",
            "--output",
            "type=local,dest=frontend/dist",
            ".",
        ],
        cwd=paths.app_dir,
        dry_run=dry_run,
    )


def migrate(paths: FoldappPaths, *, dry_run: bool = False, runner=run) -> None:
    """Apply Alembic migrations to head."""
    runner(["uv", "run", "alembic", "upgrade", "head"], cwd=paths.app_dir, dry_run=dry_run)
