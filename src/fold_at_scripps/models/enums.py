"""Categorical constants for ORM models."""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    """Whether a user can access the admin console."""

    USER = "user"
    ADMIN = "admin"


class UserTier(enum.StrEnum):
    """Quota tier determining a user's default quota profile."""

    STANDARD = "standard"
    POWER = "power"


class UserStatus(enum.StrEnum):
    """Account lifecycle state."""

    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class RunStatus(enum.StrEnum):
    """Lifecycle state of a run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
