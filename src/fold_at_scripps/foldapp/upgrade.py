"""Guarded upgrade, rollback, and refresh flows."""

from __future__ import annotations

import asyncio
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

import rich

from fold_at_scripps.config import get_settings
from fold_at_scripps.foldapp import frontend, postgres, service
from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run
from fold_at_scripps.foldapp.state import DeployState, read_state, write_state


def _current_ref(paths: FoldappPaths) -> str:
    """Current git HEAD (full sha)."""
    return run(["git", "rev-parse", "HEAD"], cwd=paths.app_dir).stdout.strip()


def _git_pull(paths: FoldappPaths, ref: str | None, *, dry_run: bool) -> tuple[str, str]:
    """Update the checkout; return (old_ref, new_ref)."""
    old = _current_ref(paths)
    if ref:
        run(["git", "fetch", "origin"], cwd=paths.app_dir, dry_run=dry_run)
        run(["git", "checkout", ref], cwd=paths.app_dir, dry_run=dry_run)
    else:
        run(["git", "pull", "--ff-only"], cwd=paths.app_dir, dry_run=dry_run)
    new = old if dry_run else _current_ref(paths)
    return old, new


def _uv_sync(paths: FoldappPaths, *, dry_run: bool) -> None:
    """Sync Python dependencies."""
    run(["uv", "sync"], cwd=paths.app_dir, dry_run=dry_run)


def set_maintenance(enabled: bool, *, dry_run: bool = False) -> None:
    """Toggle DB-backed maintenance_mode (no-op on dry-run)."""
    if dry_run:
        rich.print(f"[dim]+ maintenance_mode = {enabled}[/dim]")
        return

    async def _toggle() -> None:
        from fold_at_scripps.db import dispose_engine, get_sessionmaker
        from fold_at_scripps.system_settings import set_maintenance_mode

        try:
            async with get_sessionmaker()() as session:
                await set_maintenance_mode(session, enabled)
        finally:
            await dispose_engine()

    asyncio.run(_toggle())


def wait_healthy(port: int | None = None, timeout: float = 60.0) -> bool:
    """Poll GET /health until 200 or timeout."""
    if port is None:
        port = get_settings().api_port
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2.0)
    return False


def _rotate_backups(paths: FoldappPaths, keep: int = 5) -> None:
    """Delete all but the newest ``keep`` pre-upgrade snapshots."""
    snaps = sorted(paths.backups_dir.glob("pre-upgrade-*.sql.gz"))
    for old in snaps[:-keep]:
        old.unlink()


def upgrade(paths: FoldappPaths, *, ref: str | None = None, dry_run: bool = False) -> None:
    """Backed-up, health-gated upgrade. On failure, leave maintenance ON and stop."""
    old_ref = _current_ref(paths)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = paths.backups_dir / f"pre-upgrade-{stamp}.sql.gz"
    set_maintenance(True, dry_run=dry_run)
    postgres.dump(paths, backup, dry_run=dry_run)
    if not dry_run:
        _rotate_backups(paths)
    old_ref, new_ref = _git_pull(paths, ref, dry_run=dry_run)
    write_state(
        paths.deploy_state_file,
        DeployState(prev_ref=old_ref, new_ref=new_ref, backup_path=str(backup), timestamp=stamp),
    )
    _uv_sync(paths, dry_run=dry_run)
    frontend.build_frontend(paths, dry_run=dry_run)
    frontend.migrate(paths, dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)
    if not dry_run and not wait_healthy():
        raise RuntimeError(
            "post-upgrade health check failed; maintenance_mode left ON. "
            "Recover with: foldapp rollback (add --db if a migration is at fault)."
        )
    set_maintenance(False, dry_run=dry_run)
    rich.print(f"[green]upgraded[/] {old_ref[:8]} -> {new_ref[:8]} (backup {backup})")


def refresh(paths: FoldappPaths, *, dry_run: bool = False) -> None:
    """Light re-apply: rebuild frontend, sync catalog, restart (no pull/migrate)."""
    frontend.build_frontend(paths, dry_run=dry_run)
    run(["uv", "run", "foldapp", "catalog", "sync"], cwd=paths.app_dir, dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)


def rollback(paths: FoldappPaths, *, restore_db: bool = False, dry_run: bool = False) -> None:
    """Restore the previous git ref (and optionally the DB snapshot)."""
    st = read_state(paths.deploy_state_file)
    if st is None or st.prev_ref is None:
        raise RuntimeError("no recorded deploy state to roll back to")
    set_maintenance(True, dry_run=dry_run)
    run(["git", "checkout", st.prev_ref], cwd=paths.app_dir, dry_run=dry_run)
    _uv_sync(paths, dry_run=dry_run)
    frontend.build_frontend(paths, dry_run=dry_run)
    if restore_db and st.backup_path:
        from pathlib import Path

        postgres.restore(paths, Path(st.backup_path), dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)
    if not dry_run and not wait_healthy():
        raise RuntimeError("rollback health check failed; maintenance_mode left ON")
    set_maintenance(False, dry_run=dry_run)
    rich.print(f"[green]rolled back[/] to {st.prev_ref[:8]}")
