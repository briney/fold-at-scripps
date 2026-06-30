# Service Layer, Storage & Run Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the transport-agnostic core of fold@Scripps — a `Storage` boundary (local-FS impl), an `Executor` boundary (fake impl), DB-backed quota config + enforcement, and the run-lifecycle service (submit with param-validation + quota, list/get/cancel/soft-delete, and execute-via-executor) — all callable without HTTP or GPUs.

**Architecture:** Domain logic lives in plain async Python with no FastAPI imports; the HTTP API (Plan 7) and the scheduler (Plan 6) will be thin layers over it. Two swappable boundaries — `Storage` (per-run `inputs/config/outputs/` dirs; local FS now, object storage later) and `Executor` (the seam Plan 6's real autobio executor implements; a `FakeExecutor` drives tests) — keep the lifecycle testable without GPUs. Quota caps live in the `SystemSettings` singleton (admin-editable in Plan 8), not env. Param validation uses the tool's stored autobio JSON Schema.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, Pydantic v2, `jsonschema`, pytest (+ `tmp_path`), Postgres.

## Global Constraints

- Python `>=3.11`; ruff `target-version = "py311"`; max line length **100**.
- `src/` layout; package **`fold_at_scripps`**; `uv` for all commands.
- Type hints on all signatures; `from __future__ import annotations` in **every** module (docstring-only `__init__.py` exempt); Google-style docstrings on public classes/functions.
- Absolute imports only; catch specific exceptions (no bare `except`).
- **No HTTP in this plan** — it is the service layer; endpoints come in Plan 7. Services are tested by direct calls.
- **Config that is policy/operational lives in the DB** (`SystemSettings` singleton), admin-editable later — NOT env. Only infra/bootstrap stays in `Settings` (the storage root path is infra, so it stays in `Settings`). Quota defaults: **standard 3 / power 12** concurrent (queued+running) runs.
- **Relationship loading:** queries that need related rows use explicit `selectinload`/`joinedload`; models keep default lazy loading (no `lazy="raise_on_sql"`).
- Tests: pytest, TDD. Filesystem-only tests use `tmp_path` (no marker). DB-touching tests are `@pytest.mark.integration` and use the shared `db_session` fixture.

## Boundaries between this plan and neighbors

- **Plan 6 (scheduler/executor):** owns GPU allocation, the dispatch loop, the *real* autobio `Executor`, crash recovery, and maintenance mode. It will call this plan's `execute_run` with the real executor and a run whose `assigned_gpu_ids` it has set.
- **Plan 7 (user API):** wraps these services in `/runs` endpoints (incl. input-file uploads via `Storage.input_path`).
- **Plan 8 (admin console):** edits `SystemSettings` (quota caps, maintenance mode) and per-user overrides.

---

### Task 1: Storage boundary and local filesystem implementation

**Files:**
- Modify: `src/fold_at_scripps/config.py` (add `storage_root`)
- Create: `src/fold_at_scripps/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: `get_settings`.
- Produces:
  - `fold_at_scripps.storage.StoredFile` (dataclass: `name`, `relative_path`, `size_bytes`, `content_type`).
  - `Storage` (Protocol): `create_run_dir(run_id)`, `write_config(run_id, config) -> str`, `config_path(run_id) -> Path`, `input_path(run_id, filename) -> Path`, `outputs_dir(run_id) -> Path`, `run_root(run_id) -> Path`, `list_outputs(run_id) -> list[StoredFile]`.
  - `LocalStorage(root: Path)` implementing it; `get_storage() -> Storage` (reads `Settings.storage_root`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_storage.py`:

```python
"""Tests for local filesystem storage."""

from __future__ import annotations

import uuid
from pathlib import Path

from fold_at_scripps.storage import LocalStorage


def test_create_run_dir_makes_subdirs(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    root = storage.run_root(run_id)
    assert (root / "inputs").is_dir()
    assert (root / "config").is_dir()
    assert (root / "outputs").is_dir()


def test_write_config_round_trips(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    rel = storage.write_config(run_id, {"num_sequences": 8})
    assert rel == "config/config.json"
    import json

    assert json.loads(storage.config_path(run_id).read_text()) == {"num_sequences": 8}


def test_list_outputs_indexes_files(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    (storage.outputs_dir(run_id) / "design.pdb").write_text("ATOM\n")
    outputs = storage.list_outputs(run_id)
    assert len(outputs) == 1
    assert outputs[0].name == "design.pdb"
    assert outputs[0].relative_path == "design.pdb"
    assert outputs[0].size_bytes == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.storage'`.

- [ ] **Step 3: Add the storage-root setting**

In `src/fold_at_scripps/config.py`, add to `Settings` (after `session_https_only`):

```python
    storage_root: str = "./data"
```

- [ ] **Step 4: Implement `storage.py`**

Create `src/fold_at_scripps/storage.py`:

```python
"""Run artifact storage: a Storage boundary and a local-filesystem implementation."""

from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fold_at_scripps.config import get_settings


@dataclass
class StoredFile:
    """A file discovered in a run's output directory."""

    name: str
    relative_path: str
    size_bytes: int
    content_type: str | None


class Storage(Protocol):
    """Per-run file storage for inputs, the tool config, and outputs."""

    def create_run_dir(self, run_id: uuid.UUID) -> None: ...
    def write_config(self, run_id: uuid.UUID, config: dict[str, Any]) -> str: ...
    def config_path(self, run_id: uuid.UUID) -> Path: ...
    def input_path(self, run_id: uuid.UUID, filename: str) -> Path: ...
    def outputs_dir(self, run_id: uuid.UUID) -> Path: ...
    def run_root(self, run_id: uuid.UUID) -> Path: ...
    def list_outputs(self, run_id: uuid.UUID) -> list[StoredFile]: ...


class LocalStorage:
    """Stores run files under ``<root>/runs/<run_id>/{inputs,config,outputs}``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def run_root(self, run_id: uuid.UUID) -> Path:
        """Return the run's root directory."""
        return self._root / "runs" / str(run_id)

    def create_run_dir(self, run_id: uuid.UUID) -> None:
        """Create the run's inputs/config/outputs directories."""
        root = self.run_root(run_id)
        for sub in ("inputs", "config", "outputs"):
            (root / sub).mkdir(parents=True, exist_ok=True)

    def config_path(self, run_id: uuid.UUID) -> Path:
        """Return the path to the run's config JSON."""
        return self.run_root(run_id) / "config" / "config.json"

    def write_config(self, run_id: uuid.UUID, config: dict[str, Any]) -> str:
        """Write the tool config JSON; return its path relative to the run root."""
        path = self.config_path(run_id)
        path.write_text(json.dumps(config, indent=2))
        return "config/config.json"

    def input_path(self, run_id: uuid.UUID, filename: str) -> Path:
        """Return the path for an uploaded input file."""
        return self.run_root(run_id) / "inputs" / filename

    def outputs_dir(self, run_id: uuid.UUID) -> Path:
        """Return the run's outputs directory."""
        return self.run_root(run_id) / "outputs"

    def list_outputs(self, run_id: uuid.UUID) -> list[StoredFile]:
        """Index every file under the run's outputs directory."""
        outputs = self.outputs_dir(run_id)
        files: list[StoredFile] = []
        for path in sorted(p for p in outputs.rglob("*") if p.is_file()):
            rel = path.relative_to(outputs)
            files.append(
                StoredFile(
                    name=path.name,
                    relative_path=str(rel),
                    size_bytes=path.stat().st_size,
                    content_type=mimetypes.guess_type(path.name)[0],
                )
            )
        return files


def get_storage() -> Storage:
    """Return the configured storage backend."""
    return LocalStorage(Path(get_settings().storage_root))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && docker compose up -d postgres && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/config.py src/fold_at_scripps/storage.py tests/test_storage.py
git commit -m "feat: add storage boundary and local filesystem implementation"
```

---

### Task 2: Executor boundary and fake implementation

**Files:**
- Create: `src/fold_at_scripps/executor.py`
- Create: `tests/test_executor.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `ExecutionRequest` (dataclass: `tool_name`, `tool_version`, `image_tag`, `config_path`, `outputs_dir`, `gpu_ids`, `timeout`).
  - `ExecutionResult` (dataclass: `succeeded`, `wall_time_seconds`, `gpu_seconds`, `error`).
  - `Executor` (Protocol): `execute(self, request: ExecutionRequest) -> ExecutionResult`.
  - `FakeExecutor(succeeded=True, error=None, wall_time_seconds=0.01, gpu_seconds=None, write_output=True)` implementing it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_executor.py`:

```python
"""Tests for the executor boundary and its fake."""

from __future__ import annotations

import uuid
from pathlib import Path

from fold_at_scripps.executor import ExecutionRequest, FakeExecutor


def _request(tmp_path: Path) -> ExecutionRequest:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    return ExecutionRequest(
        tool_name="proteinmpnn",
        tool_version="1.0.0",
        image_tag="proteinmpnn:1.0.0",
        config_path=tmp_path / "config.json",
        outputs_dir=outputs,
        gpu_ids=[0],
        timeout=600,
    )


def test_fake_executor_success_writes_output(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = FakeExecutor().execute(request)
    assert result.succeeded is True
    assert result.error is None
    assert any(request.outputs_dir.iterdir())


def test_fake_executor_failure(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = FakeExecutor(succeeded=False, error="boom", write_output=False).execute(request)
    assert result.succeeded is False
    assert result.error == "boom"
    assert not any(request.outputs_dir.iterdir())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.executor'`.

- [ ] **Step 3: Implement `executor.py`**

Create `src/fold_at_scripps/executor.py`:

```python
"""Execution boundary: the interface a tool runner implements, plus a fake."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ExecutionRequest:
    """Everything an executor needs to run one tool invocation."""

    tool_name: str
    tool_version: str
    image_tag: str | None
    config_path: Path
    outputs_dir: Path
    gpu_ids: list[int]
    timeout: int | None


@dataclass
class ExecutionResult:
    """The outcome of an execution."""

    succeeded: bool
    wall_time_seconds: float
    gpu_seconds: float | None
    error: str | None


class Executor(Protocol):
    """Runs a tool invocation and reports the result."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...


class FakeExecutor:
    """A deterministic executor for tests (no Docker, no GPUs)."""

    def __init__(
        self,
        *,
        succeeded: bool = True,
        error: str | None = None,
        wall_time_seconds: float = 0.01,
        gpu_seconds: float | None = None,
        write_output: bool = True,
    ) -> None:
        self._succeeded = succeeded
        self._error = error
        self._wall_time_seconds = wall_time_seconds
        self._gpu_seconds = gpu_seconds
        self._write_output = write_output

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Optionally write a dummy output file, then return the configured result."""
        if self._write_output:
            (request.outputs_dir / "result.txt").write_text("fake output\n")
        return ExecutionResult(
            succeeded=self._succeeded,
            wall_time_seconds=self._wall_time_seconds,
            gpu_seconds=self._gpu_seconds,
            error=self._error,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_executor.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/executor.py tests/test_executor.py
git commit -m "feat: add executor boundary and fake implementation"
```

---

### Task 3: DB-backed quota settings and singleton accessor

**Files:**
- Modify: `src/fold_at_scripps/models/system.py` (add quota cap columns)
- Create: `src/fold_at_scripps/system_settings.py` (get-or-create accessor)
- Create: `migrations/versions/<generated>_add_quota_settings.py` (autogenerate)
- Modify: `tests/models/test_audit_system.py` (assert new defaults)
- Create: `tests/test_system_settings.py`

**Interfaces:**
- Consumes: `SystemSettings` model; `get_session`/`db_session`.
- Produces:
  - `SystemSettings` gains `standard_max_concurrent_runs: int` (default 3) and `power_max_concurrent_runs: int` (default 12).
  - `fold_at_scripps.system_settings.get_system_settings(session) -> SystemSettings` — returns the singleton row, creating it (id=1, defaults) if absent.
  - Migration adding the two columns.

- [ ] **Step 1: Write the failing tests**

Add to `tests/models/test_audit_system.py`:

```python
async def test_system_settings_quota_defaults(db_session: AsyncSession) -> None:
    settings = SystemSettings(id=1)
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(settings)
    assert settings.standard_max_concurrent_runs == 3
    assert settings.power_max_concurrent_runs == 12
```

Create `tests/test_system_settings.py`:

```python
"""Tests for the SystemSettings singleton accessor."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import SystemSettings
from fold_at_scripps.system_settings import get_system_settings

pytestmark = pytest.mark.integration


async def test_get_system_settings_creates_singleton(db_session: AsyncSession) -> None:
    settings = await get_system_settings(db_session)
    assert settings.id == 1
    assert settings.standard_max_concurrent_runs == 3
    count = await db_session.scalar(select(func.count()).select_from(SystemSettings))
    assert count == 1


async def test_get_system_settings_returns_existing(db_session: AsyncSession) -> None:
    first = await get_system_settings(db_session)
    first.power_max_concurrent_runs = 99
    await db_session.commit()
    second = await get_system_settings(db_session)
    assert second.power_max_concurrent_runs == 99
    count = await db_session.scalar(select(func.count()).select_from(SystemSettings))
    assert count == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose up -d postgres && uv run pytest tests/test_system_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.system_settings'`.

- [ ] **Step 3: Add the columns to the model**

In `src/fold_at_scripps/models/system.py`, add to `SystemSettings` (after `maintenance_mode`):

```python
    standard_max_concurrent_runs: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    power_max_concurrent_runs: Mapped[int] = mapped_column(
        Integer, default=12, server_default="12", nullable=False
    )
```

(`Integer` is already imported in `system.py`.)

- [ ] **Step 4: Implement the accessor**

Create `src/fold_at_scripps/system_settings.py`:

```python
"""Accessor for the SystemSettings singleton (DB-backed operational config)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import SystemSettings

_SINGLETON_ID = 1


async def get_system_settings(session: AsyncSession) -> SystemSettings:
    """Return the SystemSettings row, creating it with defaults if it does not exist."""
    settings = await session.get(SystemSettings, _SINGLETON_ID)
    if settings is None:
        settings = SystemSettings(id=_SINGLETON_ID)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings
```

- [ ] **Step 5: Generate the migration**

Run: `uv run alembic upgrade head`
Then: `uv run alembic revision --autogenerate -m "add quota settings"`
Expected: a new revision adding `standard_max_concurrent_runs` and `power_max_concurrent_runs` to `system_settings` (with `server_default`). Confirm it adds exactly those two columns; run `uv run ruff format .` on it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_system_settings.py tests/models/test_audit_system.py tests/test_migrations.py -v`
Expected: PASS (singleton accessor tests, the new defaults test, and the no-drift migration test).

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/fold_at_scripps/models/system.py src/fold_at_scripps/system_settings.py migrations/versions/ tests/models/test_audit_system.py tests/test_system_settings.py
git commit -m "feat: add DB-backed quota settings"
```

---

### Task 4: Quota service

**Files:**
- Create: `src/fold_at_scripps/runs/__init__.py`
- Create: `src/fold_at_scripps/runs/quota.py`
- Create: `tests/runs/__init__.py`
- Create: `tests/runs/test_quota.py`

**Interfaces:**
- Consumes: `get_system_settings` (Task 3); `User`, `UserTier`, `Run`, `RunStatus`; `db_session`.
- Produces:
  - `fold_at_scripps.runs.quota.QuotaExceeded` (exception).
  - `effective_concurrency_limit(user, settings) -> int`.
  - `async count_in_flight_runs(session, user_id) -> int` (statuses `queued`/`running`).
  - `async check_quota(session, user) -> None` (raises `QuotaExceeded` when in-flight ≥ limit).

- [ ] **Step 1: Write the failing tests**

Create `tests/runs/__init__.py` (empty file).

Create `tests/runs/test_quota.py`:

```python
"""Tests for quota enforcement."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Run, Tool, User, UserTier
from fold_at_scripps.runs.quota import QuotaExceeded, check_quota, effective_concurrency_limit
from fold_at_scripps.system_settings import get_system_settings

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession, *, tier: UserTier = UserTier.STANDARD) -> User:
    user = User(email="q@scripps.edu", display_name="Q", hashed_password="x", tier=tier)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema={})
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def _add_runs(session: AsyncSession, user: User, tool: Tool, n: int) -> None:
    for _ in range(n):
        session.add(Run(user_id=user.id, tool_id=tool.id, params={}, status=RunStatus.QUEUED))
    await session.commit()


async def test_effective_limit_by_tier(db_session: AsyncSession) -> None:
    settings = await get_system_settings(db_session)
    standard = await _user(db_session)
    assert effective_concurrency_limit(standard, settings) == 3


async def test_effective_limit_override(db_session: AsyncSession) -> None:
    settings = await get_system_settings(db_session)
    user = await _user(db_session)
    user.max_concurrent_runs_override = 1
    assert effective_concurrency_limit(user, settings) == 1


async def test_check_quota_under_limit(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    await _add_runs(db_session, user, tool, 2)
    await check_quota(db_session, user)  # 2 < 3, no raise


async def test_check_quota_at_limit_raises(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    await _add_runs(db_session, user, tool, 3)
    with pytest.raises(QuotaExceeded):
        await check_quota(db_session, user)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/runs/test_quota.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.runs'`.

- [ ] **Step 3: Implement the quota module**

Create `src/fold_at_scripps/runs/__init__.py`:

```python
"""Run lifecycle: quota, validation, and the run service."""
```

Create `src/fold_at_scripps/runs/quota.py`:

```python
"""Per-user concurrency quota enforcement."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, SystemSettings, User, UserTier
from fold_at_scripps.system_settings import get_system_settings

_IN_FLIGHT = (RunStatus.QUEUED, RunStatus.RUNNING)


class QuotaExceeded(Exception):
    """Raised when a user is at their concurrent-run limit."""


def effective_concurrency_limit(user: User, settings: SystemSettings) -> int:
    """Return the user's concurrency cap: per-user override, else the tier default."""
    if user.max_concurrent_runs_override is not None:
        return user.max_concurrent_runs_override
    if user.tier is UserTier.POWER:
        return settings.power_max_concurrent_runs
    return settings.standard_max_concurrent_runs


async def count_in_flight_runs(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Count the user's queued or running runs."""
    stmt = (
        select(func.count())
        .select_from(Run)
        .where(Run.user_id == user_id, Run.status.in_(_IN_FLIGHT))
    )
    return await session.scalar(stmt) or 0


async def check_quota(session: AsyncSession, user: User) -> None:
    """Raise QuotaExceeded if the user is at or above their concurrency limit."""
    settings = await get_system_settings(session)
    limit = effective_concurrency_limit(user, settings)
    in_flight = await count_in_flight_runs(session, user.id)
    if in_flight >= limit:
        raise QuotaExceeded(f"Concurrency limit of {limit} reached")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/runs/test_quota.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/runs/__init__.py src/fold_at_scripps/runs/quota.py tests/runs/__init__.py tests/runs/test_quota.py
git commit -m "feat: add quota enforcement service"
```

---

### Task 5: Run submission (validation + quota + storage)

**Files:**
- Modify: `pyproject.toml` (add `jsonschema`)
- Create: `src/fold_at_scripps/runs/validation.py`
- Create: `src/fold_at_scripps/runs/service.py`
- Create: `tests/runs/test_submit.py`

**Interfaces:**
- Consumes: `validate_params` (below); `check_quota`/`QuotaExceeded` (Task 4); `Storage` (Task 1); `Tool`, `User`, `Run`, `RunStatus`.
- Produces:
  - `fold_at_scripps.runs.validation.InvalidParams` (exception) and `validate_params(params, schema) -> None`.
  - `fold_at_scripps.runs.service.submit_run(session, *, user, tool, params, storage) -> Run` — validates params, enforces quota, writes the config to storage, creates a `queued` run.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"jsonschema>=4.21"` to `[project]` dependencies. Then:

Run: `uv sync`
Expected: installed; `uv.lock` updated.

- [ ] **Step 2: Write the failing tests**

Create `tests/runs/test_submit.py`:

```python
"""Tests for run submission."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Run, Tool, User, UserStatus
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import submit_run
from fold_at_scripps.runs.validation import InvalidParams
from fold_at_scripps.storage import LocalStorage

pytestmark = pytest.mark.integration

_SCHEMA = {
    "type": "object",
    "properties": {"num_sequences": {"type": "integer"}},
    "required": ["num_sequences"],
}


async def _user(session: AsyncSession) -> User:
    user = User(
        email="s@scripps.edu", display_name="S", hashed_password="x", status=UserStatus.ACTIVE
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema=_SCHEMA)
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def test_submit_creates_queued_run(tmp_path: Path, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    storage = LocalStorage(tmp_path)
    run = await submit_run(
        db_session, user=user, tool=tool, params={"num_sequences": 8}, storage=storage
    )
    assert run.status is RunStatus.QUEUED
    assert run.user_id == user.id
    assert run.tool_id == tool.id
    assert storage.config_path(run.id).exists()


async def test_submit_rejects_invalid_params(tmp_path: Path, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    with pytest.raises(InvalidParams):
        await submit_run(
            db_session, user=user, tool=tool, params={}, storage=LocalStorage(tmp_path)
        )


async def test_submit_enforces_quota(tmp_path: Path, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    user.max_concurrent_runs_override = 1
    await db_session.commit()
    tool = await _tool(db_session)
    storage = LocalStorage(tmp_path)
    await submit_run(db_session, user=user, tool=tool, params={"num_sequences": 1}, storage=storage)
    with pytest.raises(QuotaExceeded):
        await submit_run(
            db_session, user=user, tool=tool, params={"num_sequences": 2}, storage=storage
        )
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/runs/test_submit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.runs.validation'`.

- [ ] **Step 4: Implement param validation**

Create `src/fold_at_scripps/runs/validation.py`:

```python
"""Validation of submitted run parameters against a tool's JSON Schema."""

from __future__ import annotations

from typing import Any

import jsonschema


class InvalidParams(Exception):
    """Raised when submitted params do not satisfy the tool's input schema."""


def validate_params(params: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate ``params`` against the tool's JSON Schema; raise InvalidParams if invalid."""
    try:
        jsonschema.validate(instance=params, schema=schema)
    except jsonschema.ValidationError as exc:
        raise InvalidParams(exc.message) from exc
```

- [ ] **Step 5: Implement the submit service**

Create `src/fold_at_scripps/runs/service.py`:

```python
"""Run lifecycle service (transport-agnostic)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.runs.quota import check_quota
from fold_at_scripps.runs.validation import validate_params
from fold_at_scripps.storage import Storage


async def submit_run(
    session: AsyncSession,
    *,
    user: User,
    tool: Tool,
    params: dict,
    storage: Storage,
) -> Run:
    """Validate params, enforce the quota, persist the config, and queue a run.

    Raises:
        InvalidParams: params do not satisfy the tool's input schema.
        QuotaExceeded: the user is at their concurrency limit.
    """
    validate_params(params, tool.input_schema)
    await check_quota(session, user)

    run = Run(user_id=user.id, tool_id=tool.id, params=params, status=RunStatus.QUEUED)
    session.add(run)
    await session.flush()  # assign run.id

    storage.create_run_dir(run.id)
    storage.write_config(run.id, params)
    run.output_dir = str(storage.run_root(run.id))

    await session.commit()
    await session.refresh(run)
    return run
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/runs/test_submit.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/fold_at_scripps/runs/validation.py src/fold_at_scripps/runs/service.py tests/runs/test_submit.py
git commit -m "feat: add run submission with validation and quota"
```

---

### Task 6: Run query and lifecycle (list / get / cancel / soft-delete)

**Files:**
- Modify: `src/fold_at_scripps/runs/service.py`
- Create: `tests/runs/test_lifecycle.py`

**Interfaces:**
- Consumes: `Run`, `RunStatus`, `Tool`, `User`; `db_session`.
- Produces (appended to `runs.service`):
  - `async list_runs(session, user) -> list[Run]` — the user's non-hidden runs, newest first, with `tool` eager-loaded.
  - `async get_run(session, user, run_id) -> Run | None` — the user's non-hidden run by id (with `tool` and `artifacts` eager-loaded), else None.
  - `RunNotCancelable` (exception); `async cancel_run(session, user, run_id) -> Run` — cancels a `queued` run.
  - `async soft_delete_run(session, user, run_id) -> Run | None` — sets `hidden_at`.

- [ ] **Step 1: Write the failing tests**

Create `tests/runs/test_lifecycle.py`:

```python
"""Tests for run query and lifecycle operations."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Run, Tool, User
from fold_at_scripps.runs.service import (
    RunNotCancelable,
    cancel_run,
    get_run,
    list_runs,
    soft_delete_run,
)

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession, email: str = "l@scripps.edu") -> User:
    user = User(email=email, display_name="L", hashed_password="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema={})
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def _run(session: AsyncSession, user: User, tool: Tool, **kw) -> Run:
    run = Run(user_id=user.id, tool_id=tool.id, params={}, status=RunStatus.QUEUED, **kw)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_list_excludes_hidden_and_other_users(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    other = await _user(db_session, email="other@scripps.edu")
    tool = await _tool(db_session)
    await _run(db_session, user, tool)
    await _run(db_session, user, tool, hidden_at=datetime.datetime.now(datetime.UTC))
    await _run(db_session, other, tool)
    runs = await list_runs(db_session, user)
    assert len(runs) == 1
    assert runs[0].tool.name == "t"  # eager-loaded


async def test_get_run_ownership(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    other = await _user(db_session, email="other@scripps.edu")
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool)
    assert (await get_run(db_session, user, run.id)) is not None
    assert (await get_run(db_session, other, run.id)) is None


async def test_cancel_queued_run(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool)
    cancelled = await cancel_run(db_session, user, run.id)
    assert cancelled.status is RunStatus.CANCELED


async def test_cancel_non_queued_raises(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool, status=RunStatus.RUNNING)
    with pytest.raises(RunNotCancelable):
        await cancel_run(db_session, user, run.id)


async def test_soft_delete_hides_run(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool)
    await soft_delete_run(db_session, user, run.id)
    assert await list_runs(db_session, user) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/runs/test_lifecycle.py -v`
Expected: FAIL — `ImportError: cannot import name 'list_runs' from 'fold_at_scripps.runs.service'`.

- [ ] **Step 3: Implement the lifecycle functions**

Append to `src/fold_at_scripps/runs/service.py` (and add the imports shown to the top import block — `datetime`, `uuid`, `select`, `selectinload`):

```python
import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload


class RunNotCancelable(Exception):
    """Raised when a run cannot be canceled from its current state."""


async def list_runs(session: AsyncSession, user: User) -> list[Run]:
    """Return the user's non-hidden runs, newest first, with tool eager-loaded."""
    stmt = (
        select(Run)
        .where(Run.user_id == user.id, Run.hidden_at.is_(None))
        .options(selectinload(Run.tool))
        .order_by(Run.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run | None:
    """Return the user's non-hidden run by id (tool + artifacts loaded), or None."""
    stmt = (
        select(Run)
        .where(Run.id == run_id, Run.user_id == user.id, Run.hidden_at.is_(None))
        .options(selectinload(Run.tool), selectinload(Run.artifacts))
    )
    return await session.scalar(stmt)


async def cancel_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run:
    """Cancel a queued run. Raises RunNotCancelable if it is not queued (or not found)."""
    run = await get_run(session, user, run_id)
    if run is None or run.status is not RunStatus.QUEUED:
        raise RunNotCancelable("Only queued runs can be canceled")
    run.status = RunStatus.CANCELED
    await session.commit()
    await session.refresh(run)
    return run


async def soft_delete_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run | None:
    """Hide a run from the user's history (soft delete); return it, or None if not found."""
    run = await get_run(session, user, run_id)
    if run is None:
        return None
    run.hidden_at = datetime.datetime.now(datetime.UTC)
    await session.commit()
    await session.refresh(run)
    return run
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/runs/test_lifecycle.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/runs/service.py tests/runs/test_lifecycle.py
git commit -m "feat: add run query and lifecycle operations"
```

---

### Task 7: Execute a run via the executor

**Files:**
- Modify: `src/fold_at_scripps/runs/service.py`
- Create: `tests/runs/test_execute.py`

**Interfaces:**
- Consumes: `Executor`/`ExecutionRequest` (Task 2); `Storage` (Task 1); `Run`, `RunStatus`, `Tool`, `Artifact`.
- Produces (appended to `runs.service`): `async execute_run(session, run, executor, storage) -> Run` — marks the run running, invokes the executor (off the event loop), indexes outputs to `Artifact` rows on success, records timing, and marks the run succeeded/failed.

- [ ] **Step 1: Write the failing tests**

Create `tests/runs/test_execute.py`:

```python
"""Tests for executing a run via an executor."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.executor import FakeExecutor
from fold_at_scripps.models import Artifact, RunStatus, Run, Tool, User
from fold_at_scripps.runs.service import execute_run
from fold_at_scripps.storage import LocalStorage

pytestmark = pytest.mark.integration


async def _queued_run(session: AsyncSession, storage: LocalStorage) -> Run:
    user = User(email="e@scripps.edu", display_name="E", hashed_password="x")
    tool = Tool(
        name="t",
        version="1.0.0",
        category="c",
        input_schema={},
        image_tag="t:1.0.0",
        default_timeout=600,
    )
    session.add_all([user, tool])
    await session.commit()
    run = Run(user_id=user.id, tool_id=tool.id, params={}, status=RunStatus.QUEUED)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    storage.create_run_dir(run.id)
    return run


async def test_execute_success_indexes_artifacts(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _queued_run(db_session, storage)
    result = await execute_run(db_session, run, FakeExecutor(), storage)
    assert result.status is RunStatus.SUCCEEDED
    assert result.started_at is not None
    assert result.finished_at is not None
    count = await db_session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.run_id == run.id)
    )
    assert count == 1


async def test_execute_failure_records_error(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _queued_run(db_session, storage)
    result = await execute_run(
        db_session, run, FakeExecutor(succeeded=False, error="kaboom", write_output=False), storage
    )
    assert result.status is RunStatus.FAILED
    assert result.error == "kaboom"
    count = await db_session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.run_id == run.id)
    )
    assert count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/runs/test_execute.py -v`
Expected: FAIL — `ImportError: cannot import name 'execute_run' from 'fold_at_scripps.runs.service'`.

- [ ] **Step 3: Implement `execute_run`**

Append to `src/fold_at_scripps/runs/service.py` (add `asyncio` to the imports; `Artifact`, `Tool` join the models import; `ExecutionRequest`/`Executor` and `Storage` are imported):

```python
import asyncio

from fold_at_scripps.executor import ExecutionRequest, Executor
from fold_at_scripps.models import Artifact


async def execute_run(
    session: AsyncSession, run: Run, executor: Executor, storage: Storage
) -> Run:
    """Run a queued run via the executor, recording outputs, timing, and final status."""
    tool = await session.get(Tool, run.tool_id)
    if tool is None:  # pragma: no cover - referential integrity guarantees this
        raise ValueError(f"Run {run.id} references missing tool {run.tool_id}")

    run.status = RunStatus.RUNNING
    run.started_at = datetime.datetime.now(datetime.UTC)
    await session.commit()

    request = ExecutionRequest(
        tool_name=tool.name,
        tool_version=tool.version,
        image_tag=tool.image_tag,
        config_path=storage.config_path(run.id),
        outputs_dir=storage.outputs_dir(run.id),
        gpu_ids=run.assigned_gpu_ids or [],
        timeout=tool.default_timeout,
    )
    result = await asyncio.to_thread(executor.execute, request)

    run.finished_at = datetime.datetime.now(datetime.UTC)
    run.wall_time_seconds = result.wall_time_seconds
    run.gpu_seconds = result.gpu_seconds
    if result.succeeded:
        for stored in storage.list_outputs(run.id):
            session.add(
                Artifact(
                    run_id=run.id,
                    name=stored.name,
                    path=stored.relative_path,
                    content_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                )
            )
        run.status = RunStatus.SUCCEEDED
    else:
        run.status = RunStatus.FAILED
        run.error = result.error
    await session.commit()
    await session.refresh(run)
    return run
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/runs/test_execute.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/runs/service.py tests/runs/test_execute.py
git commit -m "feat: add execute_run service"
```

---

## Self-Review

**1. Spec coverage (against the architecture's service-layer/storage/lifecycle + the roadmap):**
- `Storage` boundary + local FS → Task 1. ✓
- `Executor` boundary + fake → Task 2. ✓
- Quota config (DB-backed, admin-editable) + enforcement → Tasks 3, 4. ✓ (honors the admin-console-managed-config principle.)
- Run submission (param validation + quota + storage + queued) → Task 5. ✓
- Run query/lifecycle (list/get/cancel/soft-delete, ownership, hidden) → Task 6. ✓
- Execute-via-executor (running → outputs/artifacts/timing → succeeded/failed) → Task 7. ✓
- Relationship loading via explicit `selectinload` → Task 6. ✓
- Deferred (documented): scheduler/GPU allocation + real autobio executor + maintenance mode + crash recovery (Plan 6); `/runs` HTTP API + uploads (Plan 7); admin editing of SystemSettings/overrides (Plan 8).

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases". Every code/command step has concrete content. The single `# pragma: no cover` guards a referential-integrity-impossible branch (explained inline), not a placeholder.

**3. Type/name consistency:** `Storage`/`StoredFile`/`LocalStorage` (Task 1) are used by `submit_run` (Task 5) and `execute_run` (Task 7). `Executor`/`ExecutionRequest`/`ExecutionResult`/`FakeExecutor` (Task 2) match `execute_run` (Task 7) and its tests. `get_system_settings` (Task 3) is used by `check_quota` (Task 4). `check_quota`/`QuotaExceeded` (Task 4) match `submit_run` (Task 5). `validate_params`/`InvalidParams` (Task 5) match `submit_run`. `RunNotCancelable` (Task 6) matches its test. `submit_run`/`list_runs`/`get_run`/`cancel_run`/`soft_delete_run`/`execute_run` all live in `runs.service` and are imported consistently. `config_path`/`outputs_dir`/`list_outputs`/`run_root`/`create_run_dir`/`write_config` (Storage, Task 1) match every call site in Tasks 5 and 7.
