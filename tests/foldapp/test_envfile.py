from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.envfile import generate_secret_key, redact_settings, scaffold_env


def test_generate_secret_key_is_long_and_unique():
    a, b = generate_secret_key(), generate_secret_key()
    assert a != b
    assert len(a) >= 40


def test_scaffold_creates_env_with_generated_secret(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    created = scaffold_env(paths)
    assert created is True
    text = paths.env_file.read_text()
    assert "FOLD_SECRET_KEY=" in text
    assert "CHANGE-ME" not in text
    assert str(paths.data_dir) in text


def test_scaffold_never_overwrites(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    paths.env_file.write_text("FOLD_SECRET_KEY=keepme\n")
    created = scaffold_env(paths)
    assert created is False
    assert paths.env_file.read_text() == "FOLD_SECRET_KEY=keepme\n"


def test_redact_masks_secret_and_password():
    out = redact_settings(
        {
            "secret_key": "supersecret",
            "database_url": "postgresql+asyncpg://fold:pw@localhost/db",
            "gpu_count": 8,
        }
    )
    assert out["secret_key"] == "***"
    assert "pw" not in out["database_url"]
    assert out["gpu_count"] == 8


def test_redact_masks_password_containing_at_symbol():
    out = redact_settings({"database_url": "postgresql+asyncpg://fold:p@ss@localhost:5432/db"})
    assert "ss" not in out["database_url"]
    assert "p@ss" not in out["database_url"]
    assert out["database_url"].startswith("postgresql+asyncpg://fold:***@localhost:5432/db")
