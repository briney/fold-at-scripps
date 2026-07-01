"""Admin request/response schemas."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from fold_at_scripps.models import RunStatus, UserRole, UserStatus, UserTier
from fold_at_scripps.schemas.runs import ArtifactRead, ToolRef


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


class AllowedEmailRead(BaseModel):
    """An allowlisted email."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime.datetime


class AllowedEmailCreate(BaseModel):
    """Payload to allowlist an email."""

    email: EmailStr


class PasswordResetResponse(BaseModel):
    """A freshly-created reset token (shown once to the admin)."""

    token: str
    expires_at: datetime.datetime


class SystemSettingsRead(BaseModel):
    """Editable operational settings."""

    model_config = ConfigDict(from_attributes=True)

    maintenance_mode: bool
    standard_max_concurrent_runs: int
    power_max_concurrent_runs: int
    updated_at: datetime.datetime


class SystemSettingsUpdate(BaseModel):
    """Partial update to the operational settings."""

    maintenance_mode: bool | None = None
    standard_max_concurrent_runs: int | None = Field(default=None, ge=0)
    power_max_concurrent_runs: int | None = Field(default=None, ge=0)


class ToolAdminRead(BaseModel):
    """Full tool representation for admin views (includes disabled tools)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    category: str
    enabled: bool
    gpu_count: int
    description: str | None
    image_tag: str | None
    default_timeout: int | None
    supports_batch: bool


class ToolEnabledUpdate(BaseModel):
    """Toggle a tool's enabled flag."""

    enabled: bool


class CatalogSyncResult(BaseModel):
    """Result of a catalog sync."""

    added: int
    updated: int


class UserRef(BaseModel):
    """Compact reference to a run's owner."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str


class AdminRunSummary(BaseModel):
    """Compact run representation for admin oversight (includes owner)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool: ToolRef
    user: UserRef
    status: RunStatus
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None


class AdminRunRead(AdminRunSummary):
    """Full run representation for admin oversight."""

    params: dict[str, Any]
    assigned_gpu_ids: list[int] | None
    wall_time_seconds: float | None
    gpu_seconds: float | None
    error: str | None
    artifacts: list[ArtifactRead]


class AuditLogRead(BaseModel):
    """An audit-log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any] | None
    created_at: datetime.datetime
