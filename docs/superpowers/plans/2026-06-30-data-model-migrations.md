# Data Model & Migrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the SQLAlchemy 2.0 ORM models for every fold@Scripps entity (User, Tool, Run, Artifact, AllowedEmail, PasswordResetToken, AuditLog, SystemSettings) and an async-aware Alembic migration that creates the schema, plus carry-forward fixes deferred from Plan 1.

**Architecture:** A `fold_at_scripps.models` package with a shared declarative `Base` (with an Alembic-friendly constraint-naming convention), reusable mixins (UUID primary key, timestamps), and one module per entity (related entities grouped). Categorical fields use `StrEnum` stored as VARCHAR+CHECK (non-native, evolvable). Alembic uses an async `env.py` driven by the app's `Settings.database_url` and `Base.metadata`. Model behavior is tested against a real Postgres via a fresh-schema-per-test fixture; the migration is tested for apply/rollback and zero drift from the models.

**Tech Stack:** SQLAlchemy 2.0 (asyncio, `Mapped`/`mapped_column`), Alembic, Postgres 16 (JSONB, ARRAY, UUID), asyncpg, pytest + pytest-asyncio, uv, ruff.

## Global Constraints

- Python `>=3.11`; ruff `target-version = "py311"`; max line length **100**.
- `src/` layout; package **`fold_at_scripps`**; `uv` for all commands (`uv run ...`).
- Type hints on all signatures; `from __future__ import annotations` in **every** module; Google-style docstrings on public classes/functions.
- Absolute imports only; first-party package `fold_at_scripps`.
- Categorical constants are `enum.StrEnum`, stored via a non-native SQLAlchemy `Enum` (VARCHAR + CHECK) that persists enum **values** (e.g. `"admin"`, not `"ADMIN"`).
- Primary keys are client-generated `uuid.UUID` (via `uuid.uuid4`) for all entities **except** `SystemSettings` (a single-row table keyed `id = 1`).
- Timestamps are timezone-aware (`DateTime(timezone=True)`), server-defaulted with `func.now()`.
- Tests use `pytest` (TDD: failing test first). DB-touching tests are marked `@pytest.mark.integration` and run against the Compose Postgres (`docker compose up -d postgres`).
- No secrets in code. Frequent commits — one per task minimum.

---

### Task 1: Declarative base, mixins, enums

**Files:**
- Create: `src/fold_at_scripps/models/__init__.py`
- Create: `src/fold_at_scripps/models/base.py`
- Create: `src/fold_at_scripps/models/enums.py`
- Create: `tests/models/__init__.py`
- Create: `tests/models/test_enums.py`
- Create: `tests/models/test_base.py`

**Interfaces:**
- Consumes: nothing new (stdlib + SQLAlchemy).
- Produces:
  - `fold_at_scripps.models.base.Base` — `DeclarativeBase` subclass with a constraint-naming-convention `MetaData`.
  - `fold_at_scripps.models.base.UUIDPKMixin` (`id: Mapped[uuid.UUID]`), `TimestampMixin` (`created_at`, `updated_at`).
  - `fold_at_scripps.models.base.str_enum(enum_cls) -> sqlalchemy.Enum` — non-native enum storing values.
  - `fold_at_scripps.models.enums`: `UserRole`, `UserTier`, `UserStatus`, `RunStatus` (all `StrEnum`).
  - These are re-exported from `fold_at_scripps.models`.

- [ ] **Step 1: Write the failing tests**

Create `tests/models/__init__.py` (empty file).

Create `tests/models/test_enums.py`:

```python
"""Tests for model enums."""

from __future__ import annotations

from fold_at_scripps.models import RunStatus, UserRole, UserStatus, UserTier


def test_enum_values() -> None:
    assert UserRole.ADMIN == "admin"
    assert UserTier.POWER == "power"
    assert [s.value for s in UserStatus] == ["pending", "active", "disabled"]
    assert [s.value for s in RunStatus] == [
        "queued",
        "running",
        "succeeded",
        "failed",
        "canceled",
    ]
```

Create `tests/models/test_base.py`:

```python
"""Tests for the declarative base helpers."""

from __future__ import annotations

from fold_at_scripps.models import Base
from fold_at_scripps.models.base import str_enum
from fold_at_scripps.models.enums import UserStatus


def test_metadata_naming_convention() -> None:
    keys = set(Base.metadata.naming_convention)
    assert keys == {"ix", "uq", "ck", "fk", "pk"}


def test_str_enum_stores_values_non_native() -> None:
    enum_type = str_enum(UserStatus)
    assert enum_type.native_enum is False
    assert enum_type.enums == ["pending", "active", "disabled"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/models/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.models'`.

- [ ] **Step 3: Implement `enums.py`**

Create `src/fold_at_scripps/models/enums.py`:

```python
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
```

- [ ] **Step 4: Implement `base.py`**

Create `src/fold_at_scripps/models/base.py`:

```python
"""Declarative base, common mixins, and column helpers for ORM models."""

from __future__ import annotations

import datetime
import enum
import uuid

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with a stable constraint-naming convention for Alembic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPKMixin:
    """Mixin adding a client-generated UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Mixin adding server-managed created/updated timestamps."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def str_enum(enum_cls: type[enum.StrEnum]) -> SAEnum:
    """Return a non-native (VARCHAR + CHECK) SQLAlchemy Enum that stores enum values."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=max(len(member.value) for member in enum_cls),
        values_callable=lambda cls: [member.value for member in cls],
    )
```

- [ ] **Step 5: Implement `models/__init__.py`**

Create `src/fold_at_scripps/models/__init__.py`:

```python
"""ORM models and declarative base for fold@Scripps."""

from __future__ import annotations

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus, UserRole, UserStatus, UserTier

__all__ = [
    "Base",
    "RunStatus",
    "TimestampMixin",
    "UUIDPKMixin",
    "UserRole",
    "UserStatus",
    "UserTier",
    "str_enum",
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/models/ -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && docker compose up -d postgres && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/fold_at_scripps/models/__init__.py src/fold_at_scripps/models/base.py src/fold_at_scripps/models/enums.py tests/models/__init__.py tests/models/test_enums.py tests/models/test_base.py
git commit -m "feat: add ORM base, mixins, and enums"
```

---

### Task 2: Model test fixtures and User model

**Files:**
- Create: `tests/models/conftest.py`
- Create: `src/fold_at_scripps/models/user.py`
- Modify: `src/fold_at_scripps/models/__init__.py`
- Create: `tests/models/test_user.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPKMixin`, `TimestampMixin`, `str_enum` (Task 1); `UserRole`, `UserStatus`, `UserTier` (Task 1); `fold_at_scripps.config.get_settings`.
- Produces:
  - `tests/models/conftest.py::db_session` — async fixture yielding an `AsyncSession` against a freshly-created-and-dropped schema (requires Postgres).
  - `fold_at_scripps.models.user.User` with columns `email`, `display_name`, `hashed_password`, `role`, `tier`, `status`, `max_concurrent_runs_override`. **No relationships yet** — `User.runs` is added in Task 4, once `Run` exists. (SQLAlchemy resolves relationship target classes at mapper-configuration time, which the first ORM query triggers; a relationship to a not-yet-defined model raises `InvalidRequestError` and breaks the User tests.)

- [ ] **Step 1: Create the model-test fixture**

Create `tests/models/conftest.py`:

```python
"""Fixtures for model tests: a fresh schema and session per test (requires Postgres)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fold_at_scripps.config import get_settings
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

- [ ] **Step 2: Write the failing User tests**

Create `tests/models/test_user.py`:

```python
"""Tests for the User model."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import User, UserRole, UserStatus, UserTier

pytestmark = pytest.mark.integration


async def test_user_defaults(db_session: AsyncSession) -> None:
    user = User(email="a@scripps.edu", display_name="Researcher A", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    assert user.role is UserRole.USER
    assert user.tier is UserTier.STANDARD
    assert user.status is UserStatus.PENDING
    assert user.max_concurrent_runs_override is None
    assert user.created_at is not None


async def test_user_email_unique(db_session: AsyncSession) -> None:
    db_session.add(User(email="dup@scripps.edu", display_name="A", hashed_password="x"))
    await db_session.commit()
    db_session.add(User(email="dup@scripps.edu", display_name="B", hashed_password="y"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_role_round_trips_as_value(db_session: AsyncSession) -> None:
    db_session.add(
        User(
            email="admin@scripps.edu",
            display_name="Admin",
            hashed_password="x",
            role=UserRole.ADMIN,
        )
    )
    await db_session.commit()
    stmt = select(User).where(User.email == "admin@scripps.edu")
    fetched = (await db_session.execute(stmt)).scalar_one()
    assert fetched.role is UserRole.ADMIN
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/models/test_user.py -v`
Expected: FAIL — `ImportError: cannot import name 'User' from 'fold_at_scripps.models'`.

- [ ] **Step 4: Implement the User model**

Create `src/fold_at_scripps/models/user.py`:

```python
"""User account model."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import UserRole, UserStatus, UserTier


class User(UUIDPKMixin, TimestampMixin, Base):
    """A user account (local authentication in v1)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        str_enum(UserRole), default=UserRole.USER, nullable=False
    )
    tier: Mapped[UserTier] = mapped_column(
        str_enum(UserTier), default=UserTier.STANDARD, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus), default=UserStatus.PENDING, nullable=False
    )
    max_concurrent_runs_override: Mapped[int | None] = mapped_column(nullable=True)

# NOTE: the `runs` relationship is intentionally NOT defined here yet; it is added
# in Task 4 (once `Run` exists), together with `Run.user`.
```

- [ ] **Step 5: Register the model in `models/__init__.py`**

Replace `src/fold_at_scripps/models/__init__.py` with:

```python
"""ORM models and declarative base for fold@Scripps."""

from __future__ import annotations

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus, UserRole, UserStatus, UserTier
from fold_at_scripps.models.user import User

__all__ = [
    "Base",
    "RunStatus",
    "TimestampMixin",
    "UUIDPKMixin",
    "User",
    "UserRole",
    "UserStatus",
    "UserTier",
    "str_enum",
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/models/test_user.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add tests/models/conftest.py src/fold_at_scripps/models/user.py src/fold_at_scripps/models/__init__.py tests/models/test_user.py
git commit -m "feat: add User model and model test fixtures"
```

---

### Task 3: Tool model

**Files:**
- Create: `src/fold_at_scripps/models/tool.py`
- Modify: `src/fold_at_scripps/models/__init__.py`
- Create: `tests/models/test_tool.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPKMixin`, `TimestampMixin` (Task 1); `db_session` (Task 2).
- Produces: `fold_at_scripps.models.tool.Tool` with `name`, `version`, `category`, `gpu_count`, `input_schema` (JSONB), `enabled`, a unique `(name, version)` constraint. **No relationships yet** — `Tool.runs` is added in Task 4, once `Run` exists (same mapper-configuration reason as `User.runs`).

- [ ] **Step 1: Write the failing Tool tests**

Create `tests/models/test_tool.py`:

```python
"""Tests for the Tool model."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Tool

pytestmark = pytest.mark.integration


async def test_tool_defaults_and_schema_round_trip(db_session: AsyncSession) -> None:
    schema = {"properties": {"num_sequences": {"type": "integer"}}}
    tool = Tool(name="proteinmpnn", version="1.0.0", category="inverse_folding", input_schema=schema)
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    assert tool.id is not None
    assert tool.gpu_count == 1
    assert tool.enabled is True
    assert tool.input_schema == schema


async def test_tool_name_version_unique(db_session: AsyncSession) -> None:
    db_session.add(Tool(name="esmfold", version="1.0.0", category="structure", input_schema={}))
    await db_session.commit()
    db_session.add(Tool(name="esmfold", version="1.0.0", category="structure", input_schema={}))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_tool_same_name_different_version_allowed(db_session: AsyncSession) -> None:
    db_session.add(Tool(name="boltz", version="1.0.0", category="structure", input_schema={}))
    db_session.add(Tool(name="boltz", version="2.0.0", category="structure", input_schema={}))
    await db_session.commit()
    count = len((await db_session.execute(select(Tool))).scalars().all())
    assert count == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/models/test_tool.py -v`
Expected: FAIL — `ImportError: cannot import name 'Tool' from 'fold_at_scripps.models'`.

- [ ] **Step 3: Implement the Tool model**

Create `src/fold_at_scripps/models/tool.py`:

```python
"""Tool catalog model — one row per autobio tool version."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin


class Tool(UUIDPKMixin, TimestampMixin, Base):
    """A specific version of an autobio tool, synced into the catalog."""

    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    gpu_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

# NOTE: the `runs` relationship is added in Task 4 (once `Run` exists), with `Run.tool`.
```

- [ ] **Step 4: Register the model in `models/__init__.py`**

Replace `src/fold_at_scripps/models/__init__.py` with:

```python
"""ORM models and declarative base for fold@Scripps."""

from __future__ import annotations

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus, UserRole, UserStatus, UserTier
from fold_at_scripps.models.tool import Tool
from fold_at_scripps.models.user import User

__all__ = [
    "Base",
    "RunStatus",
    "TimestampMixin",
    "Tool",
    "UUIDPKMixin",
    "User",
    "UserRole",
    "UserStatus",
    "UserTier",
    "str_enum",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/models/test_tool.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/models/tool.py src/fold_at_scripps/models/__init__.py tests/models/test_tool.py
git commit -m "feat: add Tool catalog model"
```

---

### Task 4: Run model

**Files:**
- Create: `src/fold_at_scripps/models/run.py`
- Modify: `src/fold_at_scripps/models/__init__.py`
- Create: `tests/models/test_run.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPKMixin`, `TimestampMixin`, `str_enum` (Task 1); `RunStatus` (Task 1); `User` (Task 2), `Tool` (Task 3); `db_session` (Task 2).
- Produces: `fold_at_scripps.models.run.Run` with `user_id`/`tool_id` FKs, `status`, `params` (JSONB), `assigned_gpu_ids` (int array, nullable), `started_at`/`finished_at`/`wall_time_seconds`/`gpu_seconds`/`error`/`output_dir`/`hidden_at` (all nullable), `user`/`tool` relationships, and a `(user_id, hidden_at)` composite index. This task also **wires the inverse relationships** `User.runs` and `Tool.runs` (modifying `user.py` and `tool.py`). The `Run.artifacts` relationship is deferred to Task 5, when `Artifact` exists.

- [ ] **Step 1: Write the failing Run tests**

Create `tests/models/test_run.py`:

```python
"""Tests for the Run model."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Run, Tool, User

pytestmark = pytest.mark.integration


async def _make_user_and_tool(session: AsyncSession) -> tuple[User, Tool]:
    user = User(email="r@scripps.edu", display_name="R", hashed_password="x")
    tool = Tool(name="proteinmpnn", version="1.0.0", category="inverse_folding", input_schema={})
    session.add_all([user, tool])
    await session.commit()
    await session.refresh(user)
    await session.refresh(tool)
    return user, tool


async def test_run_defaults_and_relationships(db_session: AsyncSession) -> None:
    user, tool = await _make_user_and_tool(db_session)
    run = Run(user_id=user.id, tool_id=tool.id, params={"num_sequences": 8})
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    assert run.id is not None
    assert run.status is RunStatus.QUEUED
    assert run.assigned_gpu_ids is None
    assert run.started_at is None
    assert run.hidden_at is None
    assert run.params == {"num_sequences": 8}
    assert run.user.email == "r@scripps.edu"
    assert run.tool.name == "proteinmpnn"


async def test_run_assigned_gpu_ids_array(db_session: AsyncSession) -> None:
    user, tool = await _make_user_and_tool(db_session)
    run = Run(
        user_id=user.id,
        tool_id=tool.id,
        params={},
        status=RunStatus.RUNNING,
        assigned_gpu_ids=[0, 3],
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    assert run.assigned_gpu_ids == [0, 3]
    assert run.status is RunStatus.RUNNING
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/models/test_run.py -v`
Expected: FAIL — `ImportError: cannot import name 'Run' from 'fold_at_scripps.models'`.

- [ ] **Step 3: Implement the Run model and wire inverse relationships**

Create `src/fold_at_scripps/models/run.py` (the `artifacts` relationship is deferred to Task 5, when `Artifact` exists):

```python
"""Run model — one submission of a tool by a user."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus

if TYPE_CHECKING:
    from fold_at_scripps.models.tool import Tool
    from fold_at_scripps.models.user import User


class Run(UUIDPKMixin, TimestampMixin, Base):
    """A single run of a tool: queued, scheduled onto GPUs, executed, recorded."""

    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_user_id_hidden_at", "user_id", "hidden_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), index=True, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus), default=RunStatus.QUEUED, index=True, nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assigned_gpu_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wall_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="runs")
    tool: Mapped[Tool] = relationship(back_populates="runs")
```

Now wire the inverse relationships. Replace `src/fold_at_scripps/models/user.py` with (adds the `runs` relationship):

```python
"""User account model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import UserRole, UserStatus, UserTier

if TYPE_CHECKING:
    from fold_at_scripps.models.run import Run


class User(UUIDPKMixin, TimestampMixin, Base):
    """A user account (local authentication in v1)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        str_enum(UserRole), default=UserRole.USER, nullable=False
    )
    tier: Mapped[UserTier] = mapped_column(
        str_enum(UserTier), default=UserTier.STANDARD, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus), default=UserStatus.PENDING, nullable=False
    )
    max_concurrent_runs_override: Mapped[int | None] = mapped_column(nullable=True)

    runs: Mapped[list[Run]] = relationship(back_populates="user")
```

And replace `src/fold_at_scripps/models/tool.py` with (adds the `runs` relationship):

```python
"""Tool catalog model — one row per autobio tool version."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from fold_at_scripps.models.run import Run


class Tool(UUIDPKMixin, TimestampMixin, Base):
    """A specific version of an autobio tool, synced into the catalog."""

    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    gpu_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    runs: Mapped[list[Run]] = relationship(back_populates="tool")
```

- [ ] **Step 4: Register the model in `models/__init__.py`**

Replace `src/fold_at_scripps/models/__init__.py` with:

```python
"""ORM models and declarative base for fold@Scripps."""

from __future__ import annotations

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus, UserRole, UserStatus, UserTier
from fold_at_scripps.models.run import Run
from fold_at_scripps.models.tool import Tool
from fold_at_scripps.models.user import User

__all__ = [
    "Base",
    "Run",
    "RunStatus",
    "TimestampMixin",
    "Tool",
    "UUIDPKMixin",
    "User",
    "UserRole",
    "UserStatus",
    "UserTier",
    "str_enum",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/models/test_run.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/models/run.py src/fold_at_scripps/models/__init__.py tests/models/test_run.py
git commit -m "feat: add Run model"
```

---

### Task 5: Artifact model

**Files:**
- Create: `src/fold_at_scripps/models/artifact.py`
- Modify: `src/fold_at_scripps/models/__init__.py`
- Create: `tests/models/test_artifact.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPKMixin` (Task 1); `Run` (Task 4); `db_session` (Task 2).
- Produces: `fold_at_scripps.models.artifact.Artifact` with `run_id` FK (`ON DELETE CASCADE`), `name`, `path`, `content_type` (nullable), `size_bytes` (nullable), `created_at`, and a `run` relationship. This task also **wires the inverse relationship** `Run.artifacts` (`cascade="all, delete-orphan"`, modifying `run.py`). Deleting a `Run` deletes its artifacts.

- [ ] **Step 1: Write the failing Artifact tests**

Create `tests/models/test_artifact.py`:

```python
"""Tests for the Artifact model."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Artifact, Run, Tool, User

pytestmark = pytest.mark.integration


async def _make_run(session: AsyncSession) -> Run:
    user = User(email="a@scripps.edu", display_name="A", hashed_password="x")
    tool = Tool(name="esmfold", version="1.0.0", category="structure", input_schema={})
    session.add_all([user, tool])
    await session.commit()
    run = Run(user_id=user.id, tool_id=tool.id, params={})
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_artifact_creation(db_session: AsyncSession) -> None:
    run = await _make_run(db_session)
    artifact = Artifact(run_id=run.id, name="design_0.pdb", path="outputs/design_0.pdb", size_bytes=2048)
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    assert artifact.id is not None
    assert artifact.content_type is None
    assert artifact.size_bytes == 2048
    assert artifact.run.id == run.id


async def test_artifact_cascade_delete_with_run(db_session: AsyncSession) -> None:
    run = await _make_run(db_session)
    db_session.add(Artifact(run_id=run.id, name="a.txt", path="outputs/a.txt"))
    await db_session.commit()
    fetched_run = await db_session.get(Run, run.id)
    await db_session.delete(fetched_run)
    await db_session.commit()
    remaining = (await db_session.execute(select(func.count()).select_from(Artifact))).scalar_one()
    assert remaining == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/models/test_artifact.py -v`
Expected: FAIL — `ImportError: cannot import name 'Artifact' from 'fold_at_scripps.models'`.

- [ ] **Step 3: Implement the Artifact model and wire the back-reference**

Create `src/fold_at_scripps/models/artifact.py`:

```python
"""Artifact model — a file produced by a run."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from fold_at_scripps.models.run import Run


class Artifact(UUIDPKMixin, Base):
    """A single output file produced by a run, indexed for listing and download."""

    __tablename__ = "artifacts"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="artifacts")
```

Now wire the inverse relationship. Replace `src/fold_at_scripps/models/run.py` with (adds the `artifacts` relationship and its `Artifact` type-check import):

```python
"""Run model — one submission of a tool by a user."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus

if TYPE_CHECKING:
    from fold_at_scripps.models.artifact import Artifact
    from fold_at_scripps.models.tool import Tool
    from fold_at_scripps.models.user import User


class Run(UUIDPKMixin, TimestampMixin, Base):
    """A single run of a tool: queued, scheduled onto GPUs, executed, recorded."""

    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_user_id_hidden_at", "user_id", "hidden_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), index=True, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus), default=RunStatus.QUEUED, index=True, nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assigned_gpu_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wall_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="runs")
    tool: Mapped[Tool] = relationship(back_populates="runs")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
```

- [ ] **Step 4: Register the model in `models/__init__.py`**

Replace `src/fold_at_scripps/models/__init__.py` with:

```python
"""ORM models and declarative base for fold@Scripps."""

from __future__ import annotations

from fold_at_scripps.models.artifact import Artifact
from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus, UserRole, UserStatus, UserTier
from fold_at_scripps.models.run import Run
from fold_at_scripps.models.tool import Tool
from fold_at_scripps.models.user import User

__all__ = [
    "Artifact",
    "Base",
    "Run",
    "RunStatus",
    "TimestampMixin",
    "Tool",
    "UUIDPKMixin",
    "User",
    "UserRole",
    "UserStatus",
    "UserTier",
    "str_enum",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/models/test_artifact.py -v`
Expected: PASS (2 passed). (The cascade test relies on the ORM `cascade="all, delete-orphan"` on `Run.artifacts`, defined in Task 4.)

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/models/artifact.py src/fold_at_scripps/models/__init__.py tests/models/test_artifact.py
git commit -m "feat: add Artifact model"
```

---

### Task 6: Supporting entities (allowlist, reset tokens, audit log, system settings)

**Files:**
- Create: `src/fold_at_scripps/models/access.py`
- Create: `src/fold_at_scripps/models/audit.py`
- Create: `src/fold_at_scripps/models/system.py`
- Modify: `src/fold_at_scripps/models/__init__.py`
- Create: `tests/models/test_access.py`
- Create: `tests/models/test_audit_system.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPKMixin` (Task 1); `User` (Task 2); `db_session` (Task 2).
- Produces:
  - `access.AllowedEmail` (`email` unique, `invited_by_id` FK nullable `SET NULL`, `invite_token` unique nullable, `created_at`).
  - `access.PasswordResetToken` (`user_id` FK `CASCADE`, `token_hash` unique, `expires_at`, `used_at` nullable, `created_at`).
  - `audit.AuditLog` (`actor_id` FK nullable `SET NULL`, `action`, `target_type`/`target_id` nullable, `details` JSONB nullable, `created_at` indexed).
  - `system.SystemSettings` (singleton: `id` int PK with `CHECK (id = 1)`, `maintenance_mode` bool default False, `updated_at`).

- [ ] **Step 1: Write the failing tests**

Create `tests/models/test_access.py`:

```python
"""Tests for AllowedEmail and PasswordResetToken models."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import AllowedEmail, PasswordResetToken, User

pytestmark = pytest.mark.integration


async def test_allowed_email_unique(db_session: AsyncSession) -> None:
    db_session.add(AllowedEmail(email="ok@scripps.edu"))
    await db_session.commit()
    db_session.add(AllowedEmail(email="ok@scripps.edu"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_password_reset_token_cascades_with_user(db_session: AsyncSession) -> None:
    user = User(email="u@scripps.edu", display_name="U", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    token = PasswordResetToken(
        user_id=user.id,
        token_hash="hash123",
        expires_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
    )
    db_session.add(token)
    await db_session.commit()
    fetched_user = await db_session.get(User, user.id)
    await db_session.delete(fetched_user)
    await db_session.commit()
    remaining = (
        await db_session.execute(select(func.count()).select_from(PasswordResetToken))
    ).scalar_one()
    assert remaining == 0
```

Create `tests/models/test_audit_system.py`:

```python
"""Tests for AuditLog and SystemSettings models."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import AuditLog, SystemSettings

pytestmark = pytest.mark.integration


async def test_audit_log_allows_null_actor(db_session: AsyncSession) -> None:
    entry = AuditLog(action="system.startup", details={"note": "boot"})
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    assert entry.id is not None
    assert entry.actor_id is None
    assert entry.details == {"note": "boot"}


async def test_system_settings_default(db_session: AsyncSession) -> None:
    settings = SystemSettings()
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(settings)
    assert settings.id == 1
    assert settings.maintenance_mode is False


async def test_system_settings_rejects_second_row(db_session: AsyncSession) -> None:
    db_session.add(SystemSettings(id=1))
    await db_session.commit()
    db_session.add(SystemSettings(id=2))
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/models/test_access.py tests/models/test_audit_system.py -v`
Expected: FAIL — `ImportError: cannot import name 'AllowedEmail' from 'fold_at_scripps.models'`.

- [ ] **Step 3: Implement `access.py`**

Create `src/fold_at_scripps/models/access.py`:

```python
"""Registration allowlist and password-reset tokens (local-auth support)."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base, UUIDPKMixin


class AllowedEmail(UUIDPKMixin, Base):
    """An email approved (or invited) to register. Gates account creation."""

    __tablename__ = "allowed_emails"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(UUIDPKMixin, Base):
    """A one-time, expiring password-reset token (admin-initiated)."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Implement `audit.py`**

Create `src/fold_at_scripps/models/audit.py`:

```python
"""Audit log of administrative actions."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base, UUIDPKMixin


class AuditLog(UUIDPKMixin, Base):
    """An append-only record of an administrative action."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
```

- [ ] **Step 5: Implement `system.py`**

Create `src/fold_at_scripps/models/system.py`:

```python
"""Singleton system settings (operational flags)."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base


class SystemSettings(Base):
    """A single-row table of global operational flags (e.g. maintenance mode)."""

    __tablename__ = "system_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 6: Register the models in `models/__init__.py`**

Replace `src/fold_at_scripps/models/__init__.py` with:

```python
"""ORM models and declarative base for fold@Scripps."""

from __future__ import annotations

from fold_at_scripps.models.access import AllowedEmail, PasswordResetToken
from fold_at_scripps.models.artifact import Artifact
from fold_at_scripps.models.audit import AuditLog
from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus, UserRole, UserStatus, UserTier
from fold_at_scripps.models.run import Run
from fold_at_scripps.models.system import SystemSettings
from fold_at_scripps.models.tool import Tool
from fold_at_scripps.models.user import User

__all__ = [
    "AllowedEmail",
    "Artifact",
    "AuditLog",
    "Base",
    "PasswordResetToken",
    "Run",
    "RunStatus",
    "SystemSettings",
    "TimestampMixin",
    "Tool",
    "UUIDPKMixin",
    "User",
    "UserRole",
    "UserStatus",
    "UserTier",
    "str_enum",
]
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/models/test_access.py tests/models/test_audit_system.py -v`
Expected: PASS (5 passed).

- [ ] **Step 8: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/fold_at_scripps/models/access.py src/fold_at_scripps/models/audit.py src/fold_at_scripps/models/system.py src/fold_at_scripps/models/__init__.py tests/models/test_access.py tests/models/test_audit_system.py
git commit -m "feat: add allowlist, reset-token, audit-log, and settings models"
```

---

### Task 7: Alembic setup and initial migration

**Files:**
- Modify: `pyproject.toml` (add `alembic` dependency)
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/` (directory; the autogenerated revision lands here)
- Create: `tests/test_migrations.py`
- Modify: `README.md` (append a "Database migrations" subsection)

**Interfaces:**
- Consumes: `fold_at_scripps.config.get_settings`, `fold_at_scripps.models.Base` (with every model registered, Tasks 2–6).
- Produces: a working `alembic` setup whose `upgrade head` creates the full schema and whose autogenerate reports zero drift from the models. `tests/test_migrations.py` enforces this in CI.

- [ ] **Step 1: Add the alembic dependency**

In `pyproject.toml`, add `"alembic>=1.13"` to the `[project]` `dependencies` list (keep the list alphabetically tidy: it goes after `"asyncpg>=0.29"`). Then run:

Run: `uv sync`
Expected: alembic installed, `uv.lock` updated.

- [ ] **Step 2: Write the failing migration test**

Create `tests/test_migrations.py`:

```python
"""Verify Alembic migrations apply, roll back, and match the models (no drift)."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import AutogenerateDiffsDetected

pytestmark = pytest.mark.integration


def test_migrations_apply_and_match_models() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    try:
        # Raises AutogenerateDiffsDetected if the models drift from the migrated schema.
        command.check(config)
    finally:
        command.downgrade(config, "base")


def test_migration_check_is_clean() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    try:
        command.check(config)
    except AutogenerateDiffsDetected as exc:  # pragma: no cover - failure path
        command.downgrade(config, "base")
        pytest.fail(f"Models drifted from migrations: {exc}")
    else:
        command.downgrade(config, "base")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: FAIL — Alembic cannot find `alembic.ini` / migrations env (e.g. `FileNotFoundError` / `No config file 'alembic.ini' found`).

- [ ] **Step 4: Create `alembic.ini`**

Create `alembic.ini`:

```ini
[alembic]
script_location = migrations
prepend_sys_path = .
path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 5: Create `migrations/script.py.mako`**

Create `migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Create `migrations/env.py`**

Create `migrations/env.py`:

```python
"""Alembic environment — async-aware, driven by the app's Settings and models."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from fold_at_scripps.config import get_settings
from fold_at_scripps.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure context against a live connection and run migrations."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync-wrapped connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for 'online' migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 7: Generate the initial migration against a clean database**

Reset the dev database so autogenerate produces a complete, from-scratch migration:

Run: `docker compose down -v && docker compose up -d postgres`
Wait for healthy: `docker compose ps` shows `postgres` healthy.

Generate the revision:

Run: `uv run alembic revision --autogenerate -m "initial schema"`
Expected: a new file under `migrations/versions/` (e.g. `<hash>_initial_schema.py`).

Inspect the generated file and confirm its `upgrade()` creates **all eight** tables: `users`, `tools`, `runs`, `artifacts`, `allowed_emails`, `password_reset_tokens`, `audit_logs`, `system_settings`, and that `downgrade()` drops them. Confirm constraint names follow the convention (e.g. `pk_users`, `uq_tools_name`, `fk_runs_user_id_users`, `ck_system_settings_single_row`). If any table is missing, a model is not imported in `models/__init__.py` — fix that and regenerate.

- [ ] **Step 8: Run the migration tests to verify they pass**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: PASS (2 passed) — `upgrade head` builds the schema, `command.check` finds no drift, `downgrade base` tears it down.

- [ ] **Step 9: Document migration usage**

Append to `README.md`:

```markdown

## Database migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/).

```bash
uv run alembic upgrade head          # apply all migrations
uv run alembic revision --autogenerate -m "describe change"  # after editing models
uv run alembic downgrade -1          # roll back one revision
```
```

- [ ] **Step 10: Lint, format, full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass. (Note: `migrations/versions/*.py` and `migrations/env.py` are linted too; ensure the generated revision passes ruff — reformat it with `uv run ruff format .` if needed.)

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml uv.lock alembic.ini migrations/ tests/test_migrations.py README.md
git commit -m "feat: add Alembic setup and initial schema migration"
```

---

### Task 8: Carry-forward fixes (lifespan engine disposal, integration auto-skip)

**Files:**
- Modify: `src/fold_at_scripps/db.py` (add `dispose_engine`)
- Modify: `src/fold_at_scripps/main.py` (add a `lifespan` that disposes the engine on shutdown)
- Modify: `tests/conftest.py` (auto-skip `integration` tests when Postgres is unreachable)
- Create: `tests/test_lifespan.py`

**Interfaces:**
- Consumes: `get_engine` (Plan 1, `db.py`); `get_settings`.
- Produces: `fold_at_scripps.db.dispose_engine()` (async, idempotent — disposes and clears the engine/sessionmaker singletons); a FastAPI `lifespan` on the app; and a collection hook that skips `integration`-marked tests when the database cannot be reached.

These two fixes were explicitly deferred from Plan 1's final review to this plan.

- [ ] **Step 1: Write the failing lifespan test**

Create `tests/test_lifespan.py`:

```python
"""Tests for application lifespan and engine disposal."""

from __future__ import annotations

import fold_at_scripps.db as db
from fold_at_scripps.db import dispose_engine, get_engine


async def test_dispose_engine_is_idempotent() -> None:
    # No engine created yet: dispose is a no-op and must not raise.
    db._engine = None
    db._sessionmaker = None
    await dispose_engine()
    assert db._engine is None

    # After creating one, dispose clears the singletons.
    engine = get_engine()
    assert engine is not None
    await dispose_engine()
    assert db._engine is None
    assert db._sessionmaker is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_lifespan.py -v`
Expected: FAIL — `ImportError: cannot import name 'dispose_engine' from 'fold_at_scripps.db'`.

- [ ] **Step 3: Add `dispose_engine` to `db.py`**

Append this function to `src/fold_at_scripps/db.py` (after `get_session`):

```python
async def dispose_engine() -> None:
    """Dispose the process-wide engine and clear the singletons, if one exists."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
```

- [ ] **Step 4: Run the lifespan test to verify it passes**

Run: `uv run pytest tests/test_lifespan.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Add the `lifespan` to the app**

Replace `src/fold_at_scripps/main.py` with:

```python
"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    app.include_router(health_router)
    return app


app = create_app()
```

- [ ] **Step 6: Add the integration auto-skip hook to `tests/conftest.py`**

Append to `tests/conftest.py`:

```python
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from fold_at_scripps.config import get_settings


def _database_reachable() -> bool:
    """Return True if the configured Postgres accepts a connection."""

    async def _probe() -> bool:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False
        finally:
            await engine.dispose()

    return asyncio.run(_probe())


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip integration-marked tests when the database is unreachable."""
    if _database_reachable():
        return
    skip_integration = pytest.mark.skip(
        reason="Postgres unreachable; run `docker compose up -d postgres` to include integration tests"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
```

- [ ] **Step 7: Verify behavior both ways**

With Postgres up, the full suite runs (nothing skipped):

Run: `docker compose up -d postgres && uv run pytest -v`
Expected: all tests pass, none skipped.

With Postgres down, integration tests skip (unit tests still run):

Run: `docker compose stop postgres && uv run pytest -v`
Expected: integration tests show `SKIPPED`, unit tests (config, base, enums, liveness, db-unavailable readiness, lifespan) still pass. Then restart it: `docker compose up -d postgres`.

- [ ] **Step 8: Lint, format, full suite**

Run: `docker compose up -d postgres && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass, none skipped.

- [ ] **Step 9: Commit**

```bash
git add src/fold_at_scripps/db.py src/fold_at_scripps/main.py tests/conftest.py tests/test_lifespan.py
git commit -m "feat: dispose engine on shutdown; auto-skip integration tests without DB"
```

---

## Self-Review

**1. Spec coverage (against `docs/ARCHITECTURE.md` data model):**
- User (role/tier/status + per-user quota override) → Task 2. ✓
- Tool (name/version/category/gpu_count/input_schema snapshot/enabled, version-pinned via unique (name,version)) → Task 3. ✓
- Run (user/tool FKs, status, params, assigned GPU IDs, timestamps, wall time, gpu-seconds, error, output-dir, `hidden_at` soft-delete) → Task 4. ✓
- Artifact (run FK + cascade, name/path/type/size) → Task 5. ✓
- AllowedEmail/Invitation, PasswordResetToken, AuditLog, SystemSettings (maintenance_mode) → Task 6. ✓
- Migrations (async Alembic, initial schema, no-drift test) → Task 7. ✓
- Deferred Plan-1 carry-forwards (lifespan `engine.dispose()`, integration auto-skip) → Task 8. ✓
- Out of scope (later plans): quota *enforcement* logic, catalog *sync*, auth/session logic, the scheduler — this plan defines structure only.

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases". Every code/command step shows concrete content. The one generated artifact (the autogenerated migration in Task 7) is produced by an explicit command and verified by `tests/test_migrations.py` (`command.check` drift detection) — not a placeholder.

**3. Type/name consistency:** `Base`, `UUIDPKMixin`, `TimestampMixin`, `str_enum`, the four enums, and each model class (`User`, `Tool`, `Run`, `Artifact`, `AllowedEmail`, `PasswordResetToken`, `AuditLog`, `SystemSettings`) are named identically where produced and consumed. Relationship pairs match: `User.runs`↔`Run.user`, `Tool.runs`↔`Run.tool`, `Run.artifacts`↔`Artifact.run`. The `db_session` fixture (Task 2) is used by every model test. `dispose_engine` (Task 8) matches its use in `main.lifespan` and `tests/test_lifespan.py`. Every model is registered in `models/__init__.py` before Task 7's autogenerate relies on `Base.metadata`.
