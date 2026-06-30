"""Account registration domain logic (transport-agnostic)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.models import AllowedEmail, User, UserStatus


class RegistrationError(Exception):
    """Base class for registration failures."""


class RegistrationNotAllowed(RegistrationError):
    """Raised when an email is not on the registration allowlist."""


class EmailAlreadyRegistered(RegistrationError):
    """Raised when an account already exists for the email."""


async def register_user(
    session: AsyncSession, *, email: str, password: str, display_name: str
) -> User:
    """Register a new account (gated by the allowlist), created as ``pending``.

    Raises:
        RegistrationNotAllowed: the email is not on the allowlist.
        EmailAlreadyRegistered: an account already exists for the email.
    """
    allowed = await session.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
    if allowed is None:
        raise RegistrationNotAllowed(f"{email} is not approved for registration")

    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailAlreadyRegistered(f"{email} is already registered")

    user = User(
        email=email,
        display_name=display_name,
        hashed_password=hash_password(password),
        status=UserStatus.PENDING,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
