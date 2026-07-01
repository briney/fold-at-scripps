from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.frontend import build_frontend, migrate
from fold_at_scripps.foldapp.shell import CommandResult


def _paths(tmp_path: Path):
    return resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")


def test_build_frontend_invokes_docker_dist_stage(tmp_path: Path):
    calls = []

    def fake_runner(args, **kw):
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    build_frontend(_paths(tmp_path), runner=fake_runner)
    assert calls and calls[0][0] == "docker" and "--target" in calls[0] and "dist" in calls[0]


def test_migrate_invokes_alembic(tmp_path: Path):
    calls = []

    def fake_runner(args, **kw):
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    migrate(_paths(tmp_path), runner=fake_runner)
    assert ["uv", "run", "alembic", "upgrade", "head"] == calls[0]
