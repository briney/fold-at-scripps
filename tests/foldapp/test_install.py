from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from fold_at_scripps.foldapp import install as install_mod
from fold_at_scripps.foldapp.context import resolve_paths


def test_deploy_dry_run_orders_steps(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with (
        mock.patch.object(install_mod.postgres, "compose_up") as compose_up,
        mock.patch.object(install_mod.postgres, "wait_ready", return_value=True) as wait_ready,
        mock.patch.object(install_mod.frontend, "migrate") as migrate,
        mock.patch.object(install_mod.frontend, "build_frontend") as build,
        mock.patch.object(install_mod.units, "install_units") as install_units,
        mock.patch.object(install_mod.service, "systemctl") as systemctl,
    ):
        install_mod.deploy(paths, dry_run=True)
    compose_up.assert_called_once()
    wait_ready.assert_called_once()
    migrate.assert_called_once()
    build.assert_called_once()
    install_units.assert_called_once()
    assert systemctl.call_count >= 1


def test_deploy_threads_configured_port_to_install_units(tmp_path: Path, monkeypatch):
    """FOLD_API_PORT (via Settings.api_port) must reach units.install_units, not 8000."""
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    stub_settings = mock.Mock(api_port=9000)
    monkeypatch.setattr(install_mod, "get_settings", lambda: stub_settings)
    with (
        mock.patch.object(install_mod.postgres, "compose_up"),
        mock.patch.object(install_mod.postgres, "wait_ready", return_value=True),
        mock.patch.object(install_mod.frontend, "migrate"),
        mock.patch.object(install_mod.frontend, "build_frontend"),
        mock.patch.object(install_mod.units, "install_units") as install_units,
        mock.patch.object(install_mod.service, "systemctl"),
    ):
        install_mod.deploy(paths, dry_run=True)
    install_units.assert_called_once_with(paths, port=9000, dry_run=True)


def test_deploy_raises_when_postgres_never_ready(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with (
        mock.patch.object(install_mod.postgres, "compose_up"),
        mock.patch.object(install_mod.postgres, "wait_ready", return_value=False),
    ):
        with pytest.raises(RuntimeError, match="(?i)postgres"):
            install_mod.deploy(paths)
