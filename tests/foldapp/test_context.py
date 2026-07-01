from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths


def test_resolve_paths_defaults_under_home(tmp_path: Path):
    app = tmp_path / "app"
    home = tmp_path / "home"
    paths = resolve_paths(app_dir=app, home=home, env={}, user="fold")
    assert paths.app_dir == app
    assert paths.env_file == app / ".env"
    assert paths.state_dir == home / ".local" / "share" / "fold"
    assert paths.data_dir == paths.state_dir / "data"
    assert paths.backups_dir == paths.state_dir / "backups"
    assert paths.deploy_state_file == paths.state_dir / "state" / "last_deploy.json"
    assert paths.user_unit_dir == home / ".config" / "systemd" / "user"
    assert paths.user == "fold"


def test_resolve_paths_honors_state_dir_override(tmp_path: Path):
    paths = resolve_paths(
        app_dir=tmp_path, home=tmp_path, env={"FOLDAPP_STATE_DIR": str(tmp_path / "s")}, user="x"
    )
    assert paths.state_dir == tmp_path / "s"


def test_unit_path_properties(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="x")
    assert paths.api_unit.name == "fold-api.service"
    assert paths.scheduler_unit.name == "fold-scheduler.service"
