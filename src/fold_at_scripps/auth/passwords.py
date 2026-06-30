"""Password hashing and verification (Argon2 via pwdlib)."""

from __future__ import annotations

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Return a salted hash of ``password``."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Return True if ``password`` matches the stored ``hashed`` value."""
    return _password_hash.verify(password, hashed)
