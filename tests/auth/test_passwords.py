"""Tests for password hashing."""

from __future__ import annotations

from fold_at_scripps.auth.passwords import hash_password, verify_password


def test_hash_is_not_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert len(hashed) > 0


def test_verify_accepts_correct_password() -> None:
    hashed = hash_password("s3cret-pw")
    assert verify_password("s3cret-pw", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("s3cret-pw")
    assert verify_password("wrong-pw", hashed) is False


def test_hashes_are_salted() -> None:
    assert hash_password("same-pw") != hash_password("same-pw")
