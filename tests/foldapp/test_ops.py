from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_status_reports_unit_activity(monkeypatch):
    from fold_at_scripps.foldapp import service

    monkeypatch.setattr(service, "is_active", lambda unit, **kw: True)
    with mock.patch("fold_at_scripps.foldapp.cli._api_healthy", return_value=True):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "fold-api" in result.output


def test_restart_invokes_systemctl(monkeypatch):
    calls = []
    from fold_at_scripps.foldapp import service

    monkeypatch.setattr(
        service, "systemctl", lambda action, target, **kw: calls.append((action, target))
    )
    result = runner.invoke(app, ["restart", "all"])
    assert result.exit_code == 0
    assert ("restart", "all") in calls
