"""Tests for the declarative base helpers."""

from __future__ import annotations

from fold_at_scripps.models import Base
from fold_at_scripps.models.base import str_enum
from fold_at_scripps.models.enums import UserStatus


def test_metadata_naming_convention() -> None:
    keys = set(Base.metadata.naming_convention)
    assert keys == {"ix", "uq", "ck", "fk", "pk"}


def test_str_enum_stores_values_non_native() -> None:
    enum_type = str_enum(UserStatus)
    assert enum_type.native_enum is False
    assert enum_type.enums == ["pending", "active", "disabled"]
