from __future__ import annotations

from unittest import mock

import pytest

from fold_at_scripps.foldapp import upgrade as up
from fold_at_scripps.foldapp.context import resolve_paths


@pytest.fixture
def stub_upgrade(monkeypatch):
    """Stub every external effect of upgrade; return the set_maintenance recorder."""
    maintenance = mock.Mock()
    monkeypatch.setattr(up, "set_maintenance", maintenance)
    monkeypatch.setattr(up, "_current_ref", lambda paths: "old")
    monkeypatch.setattr(up, "_git_pull", lambda paths, ref, *, dry_run: ("old", "new"))
    monkeypatch.setattr(up, "_uv_sync", lambda paths, *, dry_run: None)
    monkeypatch.setattr(up, "_rotate_backups", lambda paths, keep=5: None)
    monkeypatch.setattr(up.postgres, "dump", lambda paths, dest, *, dry_run=False: dest)
    monkeypatch.setattr(up.frontend, "build_frontend", lambda paths, *, dry_run=False: None)
    monkeypatch.setattr(up.frontend, "migrate", lambda paths, *, dry_run=False: None)
    monkeypatch.setattr(up.service, "systemctl", lambda action, target, *, dry_run=False: None)
    return maintenance


def test_upgrade_success_toggles_maintenance_off(tmp_path, stub_upgrade, monkeypatch):
    monkeypatch.setattr(up, "wait_healthy", lambda **kw: True)
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    up.upgrade(paths)
    calls = [c.args for c in stub_upgrade.call_args_list]
    assert calls[0] == (True,)
    assert calls[-1] == (False,)


def test_upgrade_failed_healthcheck_leaves_maintenance_on(tmp_path, stub_upgrade, monkeypatch):
    monkeypatch.setattr(up, "wait_healthy", lambda **kw: False)
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with pytest.raises(RuntimeError):
        up.upgrade(paths)
    calls = [c.args for c in stub_upgrade.call_args_list]
    assert (True,) in calls
    assert (False,) not in calls


def test_db_dump_dry_run_passes_through(tmp_path, monkeypatch):
    """db dump --dry-run passes through to postgres.dump with dry_run=True."""
    from typer.testing import CliRunner

    from fold_at_scripps.foldapp import context, postgres
    from fold_at_scripps.foldapp.cli import app

    paths = context.resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    monkeypatch.setattr(context, "resolve_paths", lambda **kw: paths)
    dump = mock.Mock(side_effect=lambda paths, dest, *, dry_run=False: dest)
    monkeypatch.setattr(postgres, "dump", dump)
    result = CliRunner().invoke(app, ["db", "dump", "--dry-run"])
    assert result.exit_code == 0
    assert dump.call_args.kwargs["dry_run"] is True


def test_db_restore_dry_run_skips_confirm(tmp_path, monkeypatch):
    """db restore --dry-run skips the confirmation prompt."""
    from typer.testing import CliRunner

    from fold_at_scripps.foldapp import context, postgres
    from fold_at_scripps.foldapp.cli import app

    paths = context.resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    monkeypatch.setattr(context, "resolve_paths", lambda **kw: paths)
    restore = mock.Mock()
    monkeypatch.setattr(postgres, "restore", restore)
    result = CliRunner().invoke(app, ["db", "restore", "test.sql.gz", "--dry-run"])
    assert result.exit_code == 0
    assert restore.call_args.kwargs["dry_run"] is True
