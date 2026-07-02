"""Unit tests for the conftest test-database URL helpers."""

from __future__ import annotations

from tests.conftest import _derive_test_url, _maintenance_url

_BASE = "postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps"


def test_derive_test_url_suffixes_db_name() -> None:
    assert _derive_test_url(_BASE) == (
        "postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps_test"
    )


def test_derive_test_url_is_idempotent() -> None:
    once = _derive_test_url(_BASE)
    assert _derive_test_url(once) == once


def test_maintenance_url_targets_postgres_db() -> None:
    assert _maintenance_url(_BASE) == "postgresql+asyncpg://fold:fold@localhost:5432/postgres"
