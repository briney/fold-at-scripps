"""Postgres lifecycle helpers (compose up, readiness, dump/restore)."""

from __future__ import annotations

import gzip
import subprocess
import time
from pathlib import Path

import rich

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run

_SERVICE = "postgres"
_DB_USER = "fold"
_DB_NAME = "fold_at_scripps"


def compose_up(paths: FoldappPaths, *, dry_run: bool = False) -> None:
    """Start the Postgres container via docker compose."""
    run(["docker", "compose", "up", "-d", _SERVICE], cwd=paths.app_dir, dry_run=dry_run)


def wait_ready(
    paths: FoldappPaths,
    *,
    timeout: float = 30.0,
    dry_run: bool = False,
    runner=run,
    sleep=time.sleep,
) -> bool:
    """Poll ``pg_isready`` inside the container until ready or ``timeout``."""
    if dry_run:
        return True
    deadline = time.monotonic() + timeout
    while True:
        result = runner(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                _SERVICE,
                "pg_isready",
                "-U",
                _DB_USER,
                "-d",
                _DB_NAME,
            ],
            cwd=paths.app_dir,
            check=False,
        )
        if result.returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(1.0)


def dump(paths: FoldappPaths, dest: Path, *, dry_run: bool = False) -> Path:
    """Write a gzipped pg_dump to ``dest`` and return the path."""
    if dry_run:
        rich.print(f"[dim]+ pg_dump -> {dest}[/dim]")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = run(
        ["docker", "compose", "exec", "-T", _SERVICE, "pg_dump", "-U", _DB_USER, _DB_NAME],
        cwd=paths.app_dir,
    )
    with gzip.open(dest, "wt", encoding="utf-8") as fh:
        fh.write(result.stdout)
    return dest


def restore(paths: FoldappPaths, src: Path, *, dry_run: bool = False) -> None:
    """Restore a gzipped pg_dump from ``src`` (destructive).

    The shared ``run`` helper does not stream stdin, so this pipes the SQL to
    ``psql`` via ``subprocess.run`` directly (still list args, never a shell).
    """
    if dry_run:
        rich.print(f"[dim]+ psql < {src}[/dim]")
        return
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        sql = fh.read()
    proc = subprocess.run(  # noqa: S603 - list args, no shell
        ["docker", "compose", "exec", "-T", _SERVICE, "psql", "-U", _DB_USER, "-d", _DB_NAME],
        cwd=str(paths.app_dir),
        input=sql,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"restore failed: {proc.stderr.strip()[-2000:]}")
