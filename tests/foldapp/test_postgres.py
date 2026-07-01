from __future__ import annotations

from pathlib import Path

import pytest

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.postgres import wait_ready
from fold_at_scripps.foldapp.shell import CommandResult


def _paths(tmp_path: Path):
    return resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")


def test_wait_ready_true_when_pg_isready_succeeds(tmp_path: Path):
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=0, stdout="accepting", stderr="")

    assert wait_ready(_paths(tmp_path), runner=fake_runner, sleep=lambda s: None) is True


def test_wait_ready_false_on_timeout(tmp_path: Path):
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=1, stdout="", stderr="no")

    assert (
        wait_ready(_paths(tmp_path), timeout=0.05, runner=fake_runner, sleep=lambda s: None)
        is False
    )


def test_dump_is_dry_run_noop(tmp_path: Path):
    from fold_at_scripps.foldapp.postgres import dump

    dest = tmp_path / "b.sql.gz"
    out = dump(_paths(tmp_path), dest, dry_run=True)
    assert out == dest
    assert not dest.exists()


@pytest.mark.integration
async def test_set_maintenance_mode_roundtrip(db_session):
    from fold_at_scripps.system_settings import get_system_settings, set_maintenance_mode

    await set_maintenance_mode(db_session, True)
    assert (await get_system_settings(db_session)).maintenance_mode is True
    await set_maintenance_mode(db_session, False)
    assert (await get_system_settings(db_session)).maintenance_mode is False
