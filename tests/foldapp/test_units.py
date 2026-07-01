from __future__ import annotations

from pathlib import Path

import pytest

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.units import render_unit


def test_render_api_unit_has_expected_fields(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path / "app", home=tmp_path, env={}, user="fold")
    text = render_unit(
        "api", paths, port=8000, uv_path="/opt/uv/uv", autobio_dir="/opt/autobio/bin"
    )
    assert f"WorkingDirectory={paths.app_dir}" in text
    assert f"EnvironmentFile={paths.env_file}" in text
    assert "/opt/uv/uv run alembic upgrade head" in text
    assert "/opt/uv/uv run foldapp serve --port 8000" in text
    assert "/opt/autobio/bin" in text  # autobio dir folded into PATH
    assert "WantedBy=default.target" in text


def test_render_scheduler_unit_has_no_migration_and_runs_scheduler(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path / "app", home=tmp_path, env={}, user="fold")
    text = render_unit("scheduler", paths, uv_path="/opt/uv/uv", autobio_dir="/opt/autobio/bin")
    assert "foldapp scheduler" in text
    assert "alembic upgrade head" not in text


def test_render_unknown_kind_raises(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with pytest.raises(ValueError):
        render_unit("bogus", paths)
