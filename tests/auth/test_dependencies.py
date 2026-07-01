"""Unit tests for auth dependencies."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fold_at_scripps.auth.dependencies import require_admin
from fold_at_scripps.models import User, UserRole


async def test_require_admin_allows_admin():
    admin = User(email="a@x.io", display_name="A", hashed_password="x", role=UserRole.ADMIN)
    assert await require_admin(current_user=admin) is admin


async def test_require_admin_rejects_non_admin():
    user = User(email="u@x.io", display_name="U", hashed_password="x", role=UserRole.USER)
    with pytest.raises(HTTPException) as exc:
        await require_admin(current_user=user)
    assert exc.value.status_code == 403
