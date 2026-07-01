from __future__ import annotations

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_help_lists_command_group():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.output.lower()


def test_doctor_runs_and_reports(monkeypatch, tmp_path):
    from fold_at_scripps.foldapp import preflight

    fake = [preflight.CheckResult("uv", preflight.Status.OK, "ok", None)]
    monkeypatch.setattr(preflight, "run_checks", lambda paths, context="deploy": fake)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "uv" in result.output


def test_doctor_exit_nonzero_on_failure(monkeypatch):
    from fold_at_scripps.foldapp import preflight

    fake = [preflight.CheckResult("uv", preflight.Status.FAIL, "missing", "install uv")]
    monkeypatch.setattr(preflight, "run_checks", lambda paths, context="deploy": fake)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1


def test_config_init_creates_env(tmp_path, monkeypatch):
    from fold_at_scripps.foldapp import context

    paths = context.resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    monkeypatch.setattr(context, "resolve_paths", lambda **kw: paths)
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert paths.env_file.is_file()


def test_version_smoke():
    assert runner.invoke(app, ["version"]).exit_code == 0
