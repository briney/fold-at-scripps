"""Identity-provider boundary and the local-accounts implementation."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import verify_password
from fold_at_scripps.models import User


class IdentityProvider(Protocol):
    """Verifies a credential and returns the matching user (or None)."""

    async def authenticate(
        self, session: AsyncSession, email: str, password: str
    ) -> User | None: ...


class LocalIdentityProvider:
    """Authenticates against locally-stored Argon2 password hashes."""

    async def authenticate(self, session: AsyncSession, email: str, password: str) -> User | None:
        """Return the user if the email exists and the password verifies, else None.

        Account status is NOT checked here; the login endpoint and
        ``get_current_user`` enforce it.
        """
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user


def get_identity_provider() -> IdentityProvider:
    """FastAPI dependency returning the configured identity provider."""
    return LocalIdentityProvider()
