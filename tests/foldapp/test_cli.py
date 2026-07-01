from __future__ import annotations

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_help_lists_command_group():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "foldapp" in result.output.lower()
