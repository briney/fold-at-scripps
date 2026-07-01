from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_uninstall_disables_units(monkeypatch, tmp_path):
    from fold_at_scripps.foldapp import context, service

    paths = context.resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    paths.user_unit_dir.mkdir(parents=True)
    paths.api_unit.write_text("x")
    paths.scheduler_unit.write_text("x")
    monkeypatch.setattr(context, "resolve_paths", lambda **kw: paths)
    calls = []
    monkeypatch.setattr(service, "systemctl", lambda action, target, **kw: calls.append(action))
    result = runner.invoke(app, ["uninstall", "--yes"])
    assert result.exit_code == 0
    assert "disable" in calls
    assert not paths.api_unit.exists()


def test_dev_up_starts_postgres_and_processes(monkeypatch):
    from fold_at_scripps.foldapp import postgres

    monkeypatch.setattr(postgres, "compose_up", lambda paths, **kw: None)
    monkeypatch.setattr(postgres, "wait_ready", lambda paths, **kw: True)
    with mock.patch("fold_at_scripps.foldapp.cli._run_dev_processes") as procs:
        result = runner.invoke(app, ["dev", "up"])
    assert result.exit_code == 0
    procs.assert_called_once()
