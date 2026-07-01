"""Admin request/response schemas."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from fold_at_scripps.models import UserRole, UserStatus, UserTier


class AdminUserRead(BaseModel):
    """Full user representation for admin views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    tier: UserTier
    status: UserStatus
    max_concurrent_runs_override: int | None
    created_at: datetime.datetime


class AdminUserUpdate(BaseModel):
    """Partial update to a user (only provided fields are applied)."""

    status: UserStatus | None = None
    tier: UserTier | None = None
    max_concurrent_runs_override: int | None = None
