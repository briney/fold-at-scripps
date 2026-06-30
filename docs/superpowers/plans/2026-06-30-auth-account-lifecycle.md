# Auth & Account Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement local-account authentication for fold@Scripps — password hashing, cookie sessions, an identity-provider boundary, allowlist-gated registration that creates `pending` accounts, a `get_current_user` dependency, the `/auth` API (register / login / logout / me), and a first-admin bootstrap CLI.

**Architecture:** Domain logic lives in a transport-agnostic `fold_at_scripps.auth` package (password hashing, an `IdentityProvider` boundary with a `LocalIdentityProvider`, and a registration service); the FastAPI layer is thin routers over it. Sessions are signed httpOnly cookies via Starlette's `SessionMiddleware` (no session table, no Redis) — the cookie carries only `user_id`, and every authenticated request re-loads the user and checks `status == active`, so disabling a user immediately invalidates their access. A Typer CLI seeds the first admin.

**Tech Stack:** FastAPI, Starlette `SessionMiddleware`, Pydantic v2 (`EmailStr`), `pwdlib[argon2]` (password hashing), Typer (CLI), SQLAlchemy 2.0 async, Postgres, pytest + httpx.

## Global Constraints

- Python `>=3.11`; ruff `target-version = "py311"`; max line length **100**.
- `src/` layout; package **`fold_at_scripps`**; `uv` for all commands (`uv run ...`).
- Type hints on all signatures; `from __future__ import annotations` in **every** module; Google-style docstrings on public classes/functions.
- Absolute imports only; first-party package `fold_at_scripps`.
- Auth is lightweight by design (intranet; attribution/quotas, not hardened security). All domain logic is transport-agnostic and sits behind clean seams: an `IdentityProvider` boundary (swappable to SSO/LDAP later) and a password-hashing module (swappable algorithm).
- Registration is **gated**: an email must be on the `AllowedEmail` allowlist to register, and a new account is created with `status = pending` (an admin activates it later — Plan 8).
- Sessions are signed httpOnly cookies carrying only `user_id`; status is enforced on every request (so disable/suspend takes effect immediately).
- Tests use `pytest` (TDD: failing test first). DB-touching tests are marked `@pytest.mark.integration` and use the shared `db_session` fixture against the Compose Postgres (`docker compose up -d postgres`); when Postgres is unreachable they auto-skip (Plan 2 hook).
- No secrets in code. The session secret key and bootstrap admin credentials come from the environment / CLI options.

## Out of scope (later plans)

- Admin actions (activate/suspend users, set tier/quota, **initiate** password resets) → Plan 8 (admin console). This plan creates `pending` users and the `get_current_user` dependency; it does **not** add admin endpoints or a `require_admin` dependency.
- Password-reset **redemption** flow → Plan 8 (kept with admin-initiated reset, since the whole feature is admin-mediated). The `PasswordResetToken` model already exists (Plan 2).
- SSO / LDAP providers (the `IdentityProvider` boundary makes them additive later).

---

### Task 1: Password hashing

**Files:**
- Modify: `pyproject.toml` (add `pwdlib[argon2]` dependency)
- Create: `src/fold_at_scripps/auth/__init__.py`
- Create: `src/fold_at_scripps/auth/passwords.py`
- Create: `tests/auth/__init__.py`
- Create: `tests/auth/test_passwords.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `fold_at_scripps.auth.passwords.hash_password(password: str) -> str` and `verify_password(password: str, hashed: str) -> bool`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"pwdlib[argon2]>=0.2"` to the `[project]` `dependencies` list (keep it alphabetically tidy). Then run:

Run: `uv sync`
Expected: `pwdlib` and `argon2-cffi` installed; `uv.lock` updated.

- [ ] **Step 2: Write the failing test**

Create `tests/auth/__init__.py` (empty file).

Create `tests/auth/test_passwords.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/auth/test_passwords.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.auth'`.

- [ ] **Step 4: Implement the package and hashing module**

Create `src/fold_at_scripps/auth/__init__.py`:

```python
"""Authentication: password hashing, identity providers, and registration."""
```

Create `src/fold_at_scripps/auth/passwords.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/auth/test_passwords.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `docker compose up -d postgres && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/fold_at_scripps/auth/__init__.py src/fold_at_scripps/auth/passwords.py tests/auth/__init__.py tests/auth/test_passwords.py
git commit -m "feat: add password hashing"
```

---

### Task 2: Session config and middleware

**Files:**
- Modify: `src/fold_at_scripps/config.py` (add `secret_key`, `session_https_only`)
- Modify: `src/fold_at_scripps/main.py` (add `SessionMiddleware`)
- Modify: `tests/test_config.py` (assert new settings)
- Create: `tests/test_session_middleware.py`

**Interfaces:**
- Consumes: `get_settings` (config).
- Produces: `Settings.secret_key: str`, `Settings.session_https_only: bool`; `create_app()` now installs `starlette.middleware.sessions.SessionMiddleware` (signed httpOnly cookie, `same_site="lax"`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py` (a new test function):

```python
def test_settings_session_defaults() -> None:
    settings = get_settings()
    assert settings.secret_key  # non-empty default for dev
    assert settings.session_https_only is False
```

Create `tests/test_session_middleware.py`:

```python
"""Tests that the app installs session middleware."""

from __future__ import annotations

from starlette.middleware.sessions import SessionMiddleware

from fold_at_scripps.main import create_app


def test_session_middleware_installed() -> None:
    app = create_app()
    assert any(m.cls is SessionMiddleware for m in app.user_middleware)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_session_middleware.py tests/test_config.py::test_settings_session_defaults -v`
Expected: FAIL — `AttributeError`/assertion on missing `secret_key`, and no `SessionMiddleware` installed.

- [ ] **Step 3: Add the settings**

In `src/fold_at_scripps/config.py`, add two fields to `Settings` (after `database_url`):

```python
    secret_key: str = "dev-insecure-secret-change-me"
    session_https_only: bool = False
```

(The default `secret_key` is for local dev only; production sets `FOLD_SECRET_KEY`. `session_https_only` should be `True` in production.)

- [ ] **Step 4: Install the middleware**

In `src/fold_at_scripps/main.py`, import and add the middleware inside `create_app()`. The function becomes:

```python
"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from fold_at_scripps.api.health import router as health_router
from fold_at_scripps.config import get_settings
from fold_at_scripps.db import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the database engine cleanly on application shutdown."""
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.session_https_only,
        same_site="lax",
    )
    app.include_router(health_router)
    return app


app = create_app()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_session_middleware.py tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/config.py src/fold_at_scripps/main.py tests/test_config.py tests/test_session_middleware.py
git commit -m "feat: add session secret config and middleware"
```

---

### Task 3: Identity provider and shared test fixture

**Files:**
- Create: `src/fold_at_scripps/auth/providers.py`
- Modify: `tests/conftest.py` (add the shared `db_session` fixture)
- Delete: `tests/models/conftest.py` (fixture moves up so all tests can use it)
- Create: `tests/auth/test_providers.py`

**Interfaces:**
- Consumes: `verify_password` (Task 1); `fold_at_scripps.models.User`, `UserStatus`; `get_session`.
- Produces:
  - `fold_at_scripps.auth.providers.IdentityProvider` (Protocol with `async authenticate(session, email, password) -> User | None`).
  - `LocalIdentityProvider` — verifies the password against the stored hash; returns the matching `User` regardless of status (status is enforced by the login endpoint / `get_current_user`), or `None` if the email is unknown or the password is wrong.
  - `get_identity_provider() -> IdentityProvider` (FastAPI dependency; returns `LocalIdentityProvider()`).
  - The `db_session` fixture now lives in `tests/conftest.py` (available to every test package).

- [ ] **Step 1: Move the `db_session` fixture up to the shared conftest**

Append the fixture to `tests/conftest.py`:

```python
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fold_at_scripps.models import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session against a freshly-created schema; drop all tables afterward."""
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            yield session
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
```

(`get_settings` is already imported in `tests/conftest.py`. Place the new imports with the existing import block; `uv run ruff check --fix .` will sort them.)

Then delete the now-redundant `tests/models/conftest.py`:

```bash
git rm tests/models/conftest.py
```

- [ ] **Step 2: Verify the model tests still get the fixture**

Run: `docker compose up -d postgres && uv run pytest tests/models/ -v`
Expected: PASS (the model tests resolve `db_session` from the parent `tests/conftest.py`).

- [ ] **Step 3: Write the failing provider tests**

Create `tests/auth/test_providers.py`:

```python
"""Tests for the local identity provider."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.auth.providers import LocalIdentityProvider
from fold_at_scripps.models import User, UserStatus

pytestmark = pytest.mark.integration


async def _add_user(session: AsyncSession, *, status: UserStatus = UserStatus.ACTIVE) -> User:
    user = User(
        email="r@scripps.edu",
        display_name="R",
        hashed_password=hash_password("good-pw"),
        status=status,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_authenticate_correct_credentials(db_session: AsyncSession) -> None:
    await _add_user(db_session)
    provider = LocalIdentityProvider()
    user = await provider.authenticate(db_session, "r@scripps.edu", "good-pw")
    assert user is not None
    assert user.email == "r@scripps.edu"


async def test_authenticate_wrong_password(db_session: AsyncSession) -> None:
    await _add_user(db_session)
    provider = LocalIdentityProvider()
    assert await provider.authenticate(db_session, "r@scripps.edu", "bad-pw") is None


async def test_authenticate_unknown_email(db_session: AsyncSession) -> None:
    provider = LocalIdentityProvider()
    assert await provider.authenticate(db_session, "nobody@scripps.edu", "x") is None


async def test_authenticate_returns_inactive_user(db_session: AsyncSession) -> None:
    # Provider verifies credentials only; status is enforced upstream.
    await _add_user(db_session, status=UserStatus.PENDING)
    provider = LocalIdentityProvider()
    user = await provider.authenticate(db_session, "r@scripps.edu", "good-pw")
    assert user is not None
    assert user.status is UserStatus.PENDING
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/auth/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.auth.providers'`.

- [ ] **Step 5: Implement the providers**

Create `src/fold_at_scripps/auth/providers.py`:

```python
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

    async def authenticate(
        self, session: AsyncSession, email: str, password: str
    ) -> User | None:
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/auth/test_providers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass (none skipped with Postgres up).

- [ ] **Step 8: Commit**

```bash
git add src/fold_at_scripps/auth/providers.py tests/conftest.py tests/auth/test_providers.py
git rm tests/models/conftest.py
git commit -m "feat: add local identity provider; share db_session fixture"
```

---

### Task 4: Registration service (allowlist-gated)

**Files:**
- Create: `src/fold_at_scripps/auth/service.py`
- Create: `tests/auth/test_service.py`

**Interfaces:**
- Consumes: `hash_password` (Task 1); `User`, `UserStatus`, `AllowedEmail`; `get_session` (indirectly via callers).
- Produces:
  - Exceptions `RegistrationError` (base), `RegistrationNotAllowed`, `EmailAlreadyRegistered`.
  - `async register_user(session, *, email, password, display_name) -> User` — rejects non-allowlisted emails and duplicates; otherwise creates a `pending` user with a hashed password.

- [ ] **Step 1: Write the failing tests**

Create `tests/auth/test_service.py`:

```python
"""Tests for the registration service."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.service import (
    EmailAlreadyRegistered,
    RegistrationNotAllowed,
    register_user,
)
from fold_at_scripps.models import AllowedEmail, UserStatus

pytestmark = pytest.mark.integration


async def _allow(session: AsyncSession, email: str) -> None:
    session.add(AllowedEmail(email=email))
    await session.commit()


async def test_register_allowlisted_creates_pending_user(db_session: AsyncSession) -> None:
    await _allow(db_session, "new@scripps.edu")
    user = await register_user(
        db_session, email="new@scripps.edu", password="s3cret-pw", display_name="New User"
    )
    assert user.id is not None
    assert user.status is UserStatus.PENDING
    assert user.hashed_password != "s3cret-pw"


async def test_register_rejects_non_allowlisted_email(db_session: AsyncSession) -> None:
    with pytest.raises(RegistrationNotAllowed):
        await register_user(
            db_session, email="stranger@scripps.edu", password="s3cret-pw", display_name="X"
        )


async def test_register_rejects_duplicate_email(db_session: AsyncSession) -> None:
    await _allow(db_session, "dup@scripps.edu")
    await register_user(
        db_session, email="dup@scripps.edu", password="s3cret-pw", display_name="A"
    )
    with pytest.raises(EmailAlreadyRegistered):
        await register_user(
            db_session, email="dup@scripps.edu", password="other-pw", display_name="B"
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/auth/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.auth.service'`.

- [ ] **Step 3: Implement the service**

Create `src/fold_at_scripps/auth/service.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/auth/test_service.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/auth/service.py tests/auth/test_service.py
git commit -m "feat: add allowlist-gated registration service"
```

---

### Task 5: Auth API and current-user dependency

**Files:**
- Modify: `pyproject.toml` (add `email-validator` dependency)
- Create: `src/fold_at_scripps/schemas/__init__.py`
- Create: `src/fold_at_scripps/schemas/auth.py`
- Create: `src/fold_at_scripps/auth/dependencies.py`
- Create: `src/fold_at_scripps/api/auth.py`
- Modify: `src/fold_at_scripps/main.py` (include the auth router)
- Create: `tests/api/test_auth.py`

**Interfaces:**
- Consumes: `register_user` + its exceptions (Task 4); `get_identity_provider` (Task 3); `get_session`; `User`, `UserStatus`.
- Produces:
  - `fold_at_scripps.schemas.auth`: `RegisterRequest`, `LoginRequest`, `UserRead`.
  - `fold_at_scripps.auth.dependencies.get_current_user(request, session) -> User` — reads the session cookie, loads the user, requires `status == active` (401 otherwise).
  - `fold_at_scripps.api.auth.router` with `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.

- [ ] **Step 1: Add the email-validator dependency**

In `pyproject.toml`, add `"email-validator>=2.1"` to `[project]` `dependencies` (for Pydantic `EmailStr`). Then:

Run: `uv sync`
Expected: installed; `uv.lock` updated.

- [ ] **Step 2: Write the failing end-to-end auth tests**

Create `tests/api/test_auth.py`:

```python
"""End-to-end tests for the auth API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, User, UserStatus

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _allow(session: AsyncSession, email: str) -> None:
    session.add(AllowedEmail(email=email))
    await session.commit()


async def _register(client: AsyncClient, email: str = "u@scripps.edu") -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": "s3cret-pw", "display_name": "U"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


async def _activate(session: AsyncSession, email: str) -> None:
    user = await session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.status = UserStatus.ACTIVE
    await session.commit()


async def test_register_requires_allowlist(db_session: AsyncSession) -> None:
    async with _client() as client:
        resp = await client.post(
            "/auth/register",
            json={"email": "stranger@scripps.edu", "password": "s3cret-pw", "display_name": "X"},
        )
    assert resp.status_code == 403


async def test_login_pending_is_forbidden(db_session: AsyncSession) -> None:
    await _allow(db_session, "u@scripps.edu")
    async with _client() as client:
        await _register(client)
        resp = await client.post(
            "/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"}
        )
    assert resp.status_code == 403


async def test_login_wrong_password(db_session: AsyncSession) -> None:
    await _allow(db_session, "u@scripps.edu")
    async with _client() as client:
        await _register(client)
        await _activate(db_session, "u@scripps.edu")
        resp = await client.post(
            "/auth/login", json={"email": "u@scripps.edu", "password": "nope"}
        )
    assert resp.status_code == 401


async def test_full_login_me_logout_flow(db_session: AsyncSession) -> None:
    await _allow(db_session, "u@scripps.edu")
    async with _client() as client:
        await _register(client)
        await _activate(db_session, "u@scripps.edu")

        # Not authenticated yet.
        assert (await client.get("/auth/me")).status_code == 401

        login = await client.post(
            "/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"}
        )
        assert login.status_code == 200
        assert login.json()["email"] == "u@scripps.edu"

        me = await client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["status"] == "active"

        assert (await client.post("/auth/logout")).status_code == 204
        assert (await client.get("/auth/me")).status_code == 401
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/api/test_auth.py -v`
Expected: FAIL — register returns 404 (no `/auth` routes yet), so the assertions fail.

- [ ] **Step 4: Create the schemas**

Create `src/fold_at_scripps/schemas/__init__.py`:

```python
"""Pydantic request/response schemas for the API."""
```

Create `src/fold_at_scripps/schemas/auth.py`:

```python
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
```

- [ ] **Step 5: Create the current-user dependency**

Create `src/fold_at_scripps/auth/dependencies.py`:

```python
"""FastAPI dependencies for authentication."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.db import get_session
from fold_at_scripps.models import User, UserStatus

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
)


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    """Return the active user identified by the session cookie, or raise 401."""
    raw_id = request.session.get("user_id")
    if raw_id is None:
        raise _UNAUTHENTICATED
    try:
        user_id = uuid.UUID(raw_id)
    except (ValueError, TypeError) as exc:
        raise _UNAUTHENTICATED from exc
    user = await session.get(User, user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise _UNAUTHENTICATED
    return user
```

- [ ] **Step 6: Create the auth router**

Create `src/fold_at_scripps/api/auth.py`:

```python
"""Authentication endpoints: register, login, logout, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.auth.providers import IdentityProvider, get_identity_provider
from fold_at_scripps.auth.service import (
    EmailAlreadyRegistered,
    RegistrationNotAllowed,
    register_user,
)
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User, UserStatus
from fold_at_scripps.schemas.auth import LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> User:
    """Register a new account (allowlist-gated; created pending)."""
    try:
        return await register_user(
            session,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except RegistrationNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=UserRead)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> User:
    """Verify credentials, enforce active status, and start a session."""
    user = await provider.authenticate(session, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if user.status is not UserStatus.ACTIVE:
        detail = (
            "Account is pending approval"
            if user.status is UserStatus.PENDING
            else "Account is disabled"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    request.session["user_id"] = str(user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    """Clear the session."""
    request.session.clear()


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently-authenticated user."""
    return current_user
```

- [ ] **Step 7: Register the router**

In `src/fold_at_scripps/main.py`, import the auth router and include it (alongside the health router):

```python
from fold_at_scripps.api.auth import router as auth_router
```

and inside `create_app()`, after `app.include_router(health_router)`:

```python
    app.include_router(auth_router)
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/api/test_auth.py -v`
Expected: PASS (4 passed).

- [ ] **Step 9: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock src/fold_at_scripps/schemas src/fold_at_scripps/auth/dependencies.py src/fold_at_scripps/api/auth.py src/fold_at_scripps/main.py tests/api/test_auth.py
git commit -m "feat: add auth API and current-user dependency"
```

---

### Task 6: First-admin bootstrap CLI

**Files:**
- Modify: `pyproject.toml` (add `typer` dependency and a `[project.scripts]` entry)
- Create: `src/fold_at_scripps/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `hash_password` (Task 1); `get_sessionmaker` (db); `User`, `UserRole`, `UserStatus`, `AllowedEmail`.
- Produces: a Typer app (`fold_at_scripps.cli.app`) with a `create-admin` command that creates an **active admin** user and allowlists their email; exits non-zero if the email already has an account. Console script: `fold-admin`.

- [ ] **Step 1: Add the dependency and console script**

In `pyproject.toml`, add `"typer>=0.12"` to `[project]` `dependencies`. Add a scripts table (top-level, e.g. after `[project]`'s dependencies or near the build-system block):

```toml
[project.scripts]
fold-admin = "fold_at_scripps.cli:main"
```

Run: `uv sync`
Expected: `typer` installed; `uv.lock` updated; the `fold-admin` entry point registered.

- [ ] **Step 2: Write the failing CLI tests**

Create `tests/test_cli.py`:

```python
"""Tests for the admin bootstrap CLI."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from fold_at_scripps.cli import app
from fold_at_scripps.models import AllowedEmail, User, UserRole, UserStatus

pytestmark = pytest.mark.integration

runner = CliRunner()


async def test_create_admin_creates_active_admin(db_session: AsyncSession) -> None:
    result = runner.invoke(
        app,
        [
            "create-admin",
            "--email",
            "boss@scripps.edu",
            "--password",
            "supersecret",
            "--display-name",
            "Boss",
        ],
    )
    assert result.exit_code == 0, result.output

    user = await db_session.scalar(select(User).where(User.email == "boss@scripps.edu"))
    assert user is not None
    assert user.role is UserRole.ADMIN
    assert user.status is UserStatus.ACTIVE
    allowed = await db_session.scalar(
        select(AllowedEmail).where(AllowedEmail.email == "boss@scripps.edu")
    )
    assert allowed is not None


async def test_create_admin_rejects_duplicate(db_session: AsyncSession) -> None:
    args = [
        "create-admin",
        "--email",
        "boss@scripps.edu",
        "--password",
        "supersecret",
        "--display-name",
        "Boss",
    ]
    assert runner.invoke(app, args).exit_code == 0
    second = runner.invoke(app, args)
    assert second.exit_code == 1
```

Note: `db_session` creates the schema; the CLI opens its own connection to the same Postgres, so its committed writes are visible to the fixture's session (read-committed).

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.cli'`.

- [ ] **Step 4: Implement the CLI**

Create `src/fold_at_scripps/cli.py`:

```python
"""Administrative CLI for fold@Scripps (e.g. first-admin bootstrap)."""

from __future__ import annotations

import asyncio

import typer
from sqlalchemy import select

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.db import get_sessionmaker
from fold_at_scripps.models import AllowedEmail, User, UserRole, UserStatus

app = typer.Typer(help="fold@Scripps administrative CLI.")


async def _create_admin(email: str, password: str, display_name: str) -> None:
    async with get_sessionmaker()() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            typer.echo(f"Error: a user with email {email} already exists.", err=True)
            raise typer.Exit(code=1)
        allowed = await session.scalar(
            select(AllowedEmail).where(AllowedEmail.email == email)
        )
        if allowed is None:
            session.add(AllowedEmail(email=email))
        session.add(
            User(
                email=email,
                display_name=display_name,
                hashed_password=hash_password(password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
        )
        await session.commit()
    typer.echo(f"Created admin user {email}.")


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., help="Admin email address."),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Admin password."
    ),
    display_name: str = typer.Option(..., help="Admin display name."),
) -> None:
    """Create an active admin account and allowlist its email."""
    asyncio.run(_create_admin(email, password, display_name))


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/test_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/fold_at_scripps/cli.py tests/test_cli.py
git commit -m "feat: add first-admin bootstrap CLI"
```

---

## Self-Review

**1. Spec coverage (against the architecture's Auth section + roadmap):**
- Local accounts + password hashing → Tasks 1, 4. ✓
- Identity-provider boundary (swappable to SSO/LDAP) → Task 3. ✓
- Cookie sessions (httpOnly, signed; status enforced per-request) → Tasks 2, 5. ✓
- Gated registration (allowlist + `pending` status) → Task 4 (service), Task 5 (endpoint). ✓
- `get_current_user` dependency → Task 5. ✓
- Auth API (register/login/logout/me) → Task 5. ✓
- First-admin bootstrap (env/CLI) → Task 6. ✓
- Deferred (documented): admin actions incl. activate/suspend + password-reset (Plan 8); `require_admin` (Plan 8); SSO/LDAP providers (future).

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases". Every code and command step has concrete content.

**3. Type/name consistency:** `hash_password`/`verify_password` (Task 1) are used identically in Tasks 3, 4, 6. `IdentityProvider`/`LocalIdentityProvider`/`get_identity_provider` (Task 3) match their use in Task 5. `register_user` + `RegistrationNotAllowed`/`EmailAlreadyRegistered` (Task 4) match Task 5's imports and HTTP mapping. `get_current_user` (Task 5) matches `/auth/me`. `UserRead`/`RegisterRequest`/`LoginRequest` (Task 5 schemas) match the router. The shared `db_session` fixture (Task 3) is used by every integration test in Tasks 3–6. `get_sessionmaker` (Plan 1 db) is reused by the CLI (Task 6). Session key `"user_id"` is written by `login` (Task 5) and read by `get_current_user` (Task 5) consistently.
