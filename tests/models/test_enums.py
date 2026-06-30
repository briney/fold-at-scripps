"""Tests for model enums."""

from __future__ import annotations

from fold_at_scripps.models import RunStatus, UserRole, UserStatus, UserTier


def test_enum_values() -> None:
    assert UserRole.ADMIN == "admin"
    assert UserTier.POWER == "power"
    assert [s.value for s in UserStatus] == ["pending", "active", "disabled"]
    assert [s.value for s in RunStatus] == [
        "queued",
        "running",
        "succeeded",
        "failed",
        "canceled",
    ]
