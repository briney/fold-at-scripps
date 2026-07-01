"""Auth request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from fold_at_scripps.models import UserRole, UserStatus, UserTier


class RegisterRequest(BaseModel):
    """Payload for creating a new (pending) account."""

    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    """Payload for logging in."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Public representation of a user account."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    tier: UserTier
    status: UserStatus


class PasswordResetRedeem(BaseModel):
    """Payload to redeem a password-reset token."""

    token: str
    new_password: str = Field(min_length=8)
