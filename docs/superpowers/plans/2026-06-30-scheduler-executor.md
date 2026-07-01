# Scheduler & autobio Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the fold@Scripps scheduler — a single async host process that owns the GPU pool, atomically claims queued runs (`SELECT … FOR UPDATE SKIP LOCKED`), allocates whole GPUs exclusively, dispatches them through the `Executor`, recovers orphaned runs on restart, and honors maintenance mode — plus the real `AutobioExecutor` that runs tools via the autobio CLI.

**Architecture:** A `claim → execute` split: `claim_runnable_run` performs the atomic `QUEUED → RUNNING` transition with GPU assignment under a row lock; the (refactored) `execute_run` then runs a *RUNNING* run through the executor and records the outcome, catching any executor exception so a run never gets stuck in RUNNING. An in-memory `GpuPool` (owned by the single scheduler) tracks free GPUs. The `Scheduler` loop reaps finished dispatches (freeing GPUs), then — unless `SystemSettings.maintenance_mode` — claims and dispatches runs that fit the free-GPU count. The `AutobioExecutor` shells out to `autobio run … --format json`, deriving success from the exit code and moving autobio's `outputs/` into our `Storage.outputs_dir`. Everything is testable with `FakeExecutor` + a configurable GPU pool; the real executor has a skip-guarded smoke test.

**Tech Stack:** SQLAlchemy 2.0 async (`FOR UPDATE SKIP LOCKED`), asyncio, `subprocess` (autobio CLI), Typer (CLI entry), pytest, Postgres.

## autobio `run` reference (verified on this host)

- Command: `autobio run TOOL --config <config.json> --gpu <auto|none|ids> --timeout <s> --output-dir <workspace> --format json`. `--gpu` takes `none`, `auto`, or comma-separated IDs (e.g. `0,3`). Exit code 0 = success, non-zero = failure.
- The `--output-dir` workspace after a run: `config.json`, `inputs/`, `logs/{stdout,stderr,tool}.log`, `result.json`, and **`outputs/`** (the real tool outputs, e.g. `outputs/raw/…`, `outputs/standardized/…`).

## Global Constraints

- Python `>=3.11`; ruff `target-version = "py311"`; max line length **100**.
- `src/` layout; package **`fold_at_scripps`**; `uv` for all commands.
- Type hints on all signatures; `from __future__ import annotations` in **every** module (docstring-only `__init__.py` exempt); Google-style docstrings on public classes/functions.
- Absolute imports only. `subprocess` uses a list of args (never `shell=True`) with an explicit `timeout`. Catch specific exceptions, except at the execution boundary where an executor failure MUST mark the run FAILED (documented `except Exception` there).
- GPU pool size is env config (`gpu_count`, infra — like `storage_root`, not admin-editable). `maintenance_mode` and quota caps remain DB-backed (admin-editable, per the admin-console-managed-config principle).
- Tests: pytest, TDD. Scheduler/claim/recovery tests are `@pytest.mark.integration` (Postgres) and use `FakeExecutor` + a configurable `GpuPool` — no real GPUs/autobio. The real `AutobioExecutor` smoke test is `@pytest.mark.skipif(shutil.which("autobio") is None, ...)`.

## Downstream-contract fixes carried in from Plan 5 (per its final review)

- `execute_run` must guard the run state and be exception-safe (this plan, Task 1).
- The scheduler sets `assigned_gpu_ids` and performs the `QUEUED → RUNNING` transition (Task 3), so `execute_run` is refactored to expect a RUNNING run.

## Out of scope (later plans)

- HTTP endpoints for submitting/canceling runs (Plan 7); the scheduler consumes runs the API/service create.
- Admin control of maintenance mode / cancel-running (Plan 8); this plan only *reads* `maintenance_mode`.
- Multi-node scheduling (the `SKIP LOCKED` claim is already multi-node-ready; running it is future).

---

### Task 1: Refactor `execute_run` for the claim/execute split and exception safety

**Files:**
- Modify: `src/fold_at_scripps/runs/service.py`
- Modify: `tests/runs/test_execute.py`

**Interfaces:**
- Consumes: `Executor`/`ExecutionRequest`, `Storage`, `Run`, `RunStatus`, `Tool`, `Artifact`.
- Produces: `InvalidRunState` (exception); `execute_run(session, run, executor, storage) -> Run` now **requires a RUNNING run** (raising `InvalidRunState` otherwise), does **not** set RUNNING/`started_at` (the scheduler's claim does that), records `finished_at`/timing/artifacts/outcome, and marks the run FAILED if the executor raises.

- [ ] **Step 1: Update the failing tests**

Replace the body of `tests/runs/test_execute.py` with (the helper now returns a RUNNING run, matching the post-claim state; adds a guard test and an executor-raises test):

```python
"""Tests for executing a run via an executor."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.executor import ExecutionRequest, ExecutionResult, FakeExecutor
from fold_at_scripps.models import Artifact, RunStatus, Run, Tool, User
from fold_at_scripps.runs.service import InvalidRunState, execute_run
from fold_at_scripps.storage import LocalStorage

pytestmark = pytest.mark.integration


async def _running_run(session: AsyncSession, storage: LocalStorage) -> Run:
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
    run = Run(
        user_id=user.id,
        tool_id=tool.id,
        params={},
        status=RunStatus.RUNNING,
        assigned_gpu_ids=[0],
        started_at=datetime.datetime.now(datetime.UTC),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    storage.create_run_dir(run.id)
    return run


async def test_execute_success_indexes_artifacts(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    result = await execute_run(db_session, run, FakeExecutor(), storage)
    assert result.status is RunStatus.SUCCEEDED
    assert result.finished_at is not None
    count = await db_session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.run_id == run.id)
    )
    assert count == 1


async def test_execute_failure_records_error(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    result = await execute_run(
        db_session, run, FakeExecutor(succeeded=False, error="kaboom", write_output=False), storage
    )
    assert result.status is RunStatus.FAILED
    assert result.error == "kaboom"


async def test_execute_requires_running(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    run.status = RunStatus.QUEUED
    await db_session.commit()
    with pytest.raises(InvalidRunState):
        await execute_run(db_session, run, FakeExecutor(), storage)


async def test_execute_marks_failed_when_executor_raises(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    class _BoomExecutor:
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            raise RuntimeError("executor crashed")

    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    result = await execute_run(db_session, run, _BoomExecutor(), storage)
    assert result.status is RunStatus.FAILED
    assert "executor crashed" in (result.error or "")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose up -d postgres && uv run pytest tests/runs/test_execute.py -v`
Expected: FAIL — `ImportError: cannot import name 'InvalidRunState'` (and the RUNNING-guard behavior doesn't exist yet).

- [ ] **Step 3: Refactor `execute_run`**

In `src/fold_at_scripps/runs/service.py`, replace the existing `execute_run` implementation (keep its imports; add an `InvalidRunState` exception) with:

```python
class InvalidRunState(Exception):
    """Raised when a run is not in the expected state for an operation."""


async def execute_run(
    session: AsyncSession, run: Run, executor: Executor, storage: Storage
) -> Run:
    """Execute a RUNNING run via the executor and record its outcome.

    The caller (scheduler) is responsible for the QUEUED -> RUNNING transition and
    for assigning GPUs. If the executor raises, the run is marked FAILED rather
    than left RUNNING.
    """
    if run.status is not RunStatus.RUNNING:
        raise InvalidRunState(f"execute_run requires a RUNNING run, got {run.status}")

    tool = await session.get(Tool, run.tool_id)
    if tool is None:  # pragma: no cover - referential integrity guarantees this
        raise ValueError(f"Run {run.id} references missing tool {run.tool_id}")

    request = ExecutionRequest(
        tool_name=tool.name,
        tool_version=tool.version,
        image_tag=tool.image_tag,
        config_path=storage.config_path(run.id),
        outputs_dir=storage.outputs_dir(run.id),
        gpu_ids=run.assigned_gpu_ids or [],
        timeout=tool.default_timeout,
    )
    run.finished_at = datetime.datetime.now(datetime.UTC)
    try:
        result = await asyncio.to_thread(executor.execute, request)
    except Exception as exc:  # noqa: BLE001 - execution boundary: never leave a run RUNNING
        run.status = RunStatus.FAILED
        run.error = f"executor error: {exc}"
        run.finished_at = datetime.datetime.now(datetime.UTC)
        await session.commit()
        await session.refresh(run)
        return run

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

(If ruff flags `BLE001` is not enabled, the `# noqa` is harmless; the project's ruff select is `E,F,I,UP,B` — `B` is flake8-bugbear, which does not include blind-except, so remove the `# noqa: BLE001` if `ruff check` reports it as an unused/ unknown noqa. Keep the `except Exception` with its explanatory comment either way.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/runs/test_execute.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/runs/service.py tests/runs/test_execute.py
git commit -m "refactor: execute_run expects RUNNING run, is exception-safe"
```

---

### Task 2: GPU pool allocator

**Files:**
- Create: `src/fold_at_scripps/scheduler/__init__.py`
- Create: `src/fold_at_scripps/scheduler/pool.py`
- Create: `tests/scheduler/__init__.py`
- Create: `tests/scheduler/test_pool.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `fold_at_scripps.scheduler.pool.GpuPool(gpu_ids)` with `available` (property), `can_allocate(count) -> bool`, `try_allocate(count) -> list[int] | None` (exclusive; `[]` for count 0), `release(ids)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scheduler/__init__.py` (empty file).

Create `tests/scheduler/test_pool.py`:

```python
"""Tests for the in-memory GPU pool."""

from __future__ import annotations

from fold_at_scripps.scheduler.pool import GpuPool


def test_allocate_and_release() -> None:
    pool = GpuPool([0, 1, 2, 3])
    ids = pool.try_allocate(2)
    assert ids == [0, 1]
    assert pool.available == 2
    pool.release(ids)
    assert pool.available == 4


def test_allocation_is_exclusive() -> None:
    pool = GpuPool([0, 1])
    first = pool.try_allocate(1)
    second = pool.try_allocate(1)
    assert first == [0]
    assert second == [1]
    assert set(first).isdisjoint(second)


def test_try_allocate_returns_none_when_insufficient() -> None:
    pool = GpuPool([0])
    assert pool.try_allocate(2) is None
    assert pool.available == 1


def test_allocate_zero_gpus() -> None:
    pool = GpuPool([0, 1])
    assert pool.try_allocate(0) == []
    assert pool.available == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/scheduler/test_pool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.scheduler'`.

- [ ] **Step 3: Implement the package and pool**

Create `src/fold_at_scripps/scheduler/__init__.py`:

```python
"""GPU scheduler: pool, claim, recovery, and the scheduler loop."""
```

Create `src/fold_at_scripps/scheduler/pool.py`:

```python
"""In-memory GPU pool owned by the single scheduler process."""

from __future__ import annotations


class GpuPool:
    """Tracks which GPU IDs are free and allocates them exclusively."""

    def __init__(self, gpu_ids: list[int]) -> None:
        self._all = list(gpu_ids)
        self._free = set(gpu_ids)

    @property
    def available(self) -> int:
        """Number of currently-free GPUs."""
        return len(self._free)

    def can_allocate(self, count: int) -> bool:
        """Whether ``count`` GPUs are currently free."""
        return count <= len(self._free)

    def try_allocate(self, count: int) -> list[int] | None:
        """Allocate ``count`` GPUs (lowest IDs first); return them, or None if too few."""
        if count > len(self._free):
            return None
        allocated = sorted(self._free)[:count]
        self._free.difference_update(allocated)
        return allocated

    def release(self, gpu_ids: list[int]) -> None:
        """Return GPUs to the free set (ignores IDs not owned by this pool)."""
        self._free.update(gpu_id for gpu_id in gpu_ids if gpu_id in self._all)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/scheduler/test_pool.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && docker compose up -d postgres && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/scheduler/__init__.py src/fold_at_scripps/scheduler/pool.py tests/scheduler/__init__.py tests/scheduler/test_pool.py
git commit -m "feat: add in-memory GPU pool"
```

---

### Task 3: Atomic claim of a runnable queued run

**Files:**
- Create: `src/fold_at_scripps/scheduler/claim.py`
- Create: `tests/scheduler/test_claim.py`

**Interfaces:**
- Consumes: `GpuPool` (Task 2); `Run`, `RunStatus`, `Tool`; `db_session`.
- Produces: `claim_runnable_run(session, pool) -> tuple[Run, list[int]] | None` — finds the oldest queued run whose `tool.gpu_count` fits the free pool, allocates those GPUs, transitions it `QUEUED → RUNNING` with `assigned_gpu_ids` + `started_at`, commits, and returns `(run, gpu_ids)`; returns None if none fit. Uses `FOR UPDATE SKIP LOCKED` on `runs`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scheduler/test_claim.py`:

```python
"""Tests for claiming runnable queued runs."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Run, Tool, User
from fold_at_scripps.scheduler.claim import claim_runnable_run
from fold_at_scripps.scheduler.pool import GpuPool

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession) -> User:
    user = User(email="c@scripps.edu", display_name="C", hashed_password="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession, *, gpu_count: int = 1) -> Tool:
    tool = Tool(name=f"t{gpu_count}", version="1.0.0", category="c", input_schema={}, gpu_count=gpu_count)
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def _queue(session: AsyncSession, user: User, tool: Tool, when: int) -> Run:
    run = Run(
        user_id=user.id,
        tool_id=tool.id,
        params={},
        status=RunStatus.QUEUED,
        created_at=datetime.datetime(2026, 1, 1, 0, when, tzinfo=datetime.UTC),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_claim_transitions_oldest_fitting_run(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session, gpu_count=1)
    first = await _queue(db_session, user, tool, when=1)
    await _queue(db_session, user, tool, when=2)
    pool = GpuPool([0, 1])
    claimed = await claim_runnable_run(db_session, pool)
    assert claimed is not None
    run, gpu_ids = claimed
    assert run.id == first.id
    assert run.status is RunStatus.RUNNING
    assert run.assigned_gpu_ids == gpu_ids == [0]
    assert run.started_at is not None
    assert pool.available == 1


async def test_claim_returns_none_when_nothing_fits(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session, gpu_count=4)
    await _queue(db_session, user, tool, when=1)
    pool = GpuPool([0, 1])  # only 2 free, run needs 4
    assert await claim_runnable_run(db_session, pool) is None


async def test_claim_returns_none_when_no_queued(db_session: AsyncSession) -> None:
    pool = GpuPool([0, 1])
    assert await claim_runnable_run(db_session, pool) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/scheduler/test_claim.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.scheduler.claim'`.

- [ ] **Step 3: Implement the claim**

Create `src/fold_at_scripps/scheduler/claim.py`:

```python
"""Atomically claim a runnable queued run and assign it GPUs."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool
from fold_at_scripps.scheduler.pool import GpuPool


async def claim_runnable_run(
    session: AsyncSession, pool: GpuPool
) -> tuple[Run, list[int]] | None:
    """Claim the oldest queued run that fits the free GPU pool.

    Locks candidate rows with FOR UPDATE SKIP LOCKED, allocates GPUs for the first
    run whose tool needs no more than are free, transitions it to RUNNING with
    assigned GPUs and a start time, commits, and returns ``(run, gpu_ids)``.
    Returns None when no queued run fits.
    """
    stmt = (
        select(Run, Tool.gpu_count)
        .join(Tool, Run.tool_id == Tool.id)
        .where(Run.status == RunStatus.QUEUED)
        .order_by(Run.created_at)
        .with_for_update(skip_locked=True, of=Run)
    )
    rows = (await session.execute(stmt)).all()
    for run, gpu_count in rows:
        gpu_ids = pool.try_allocate(gpu_count)
        if gpu_ids is None:
            continue
        run.status = RunStatus.RUNNING
        run.assigned_gpu_ids = gpu_ids
        run.started_at = datetime.datetime.now(datetime.UTC)
        await session.commit()
        await session.refresh(run)
        return run, gpu_ids
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/scheduler/test_claim.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/scheduler/claim.py tests/scheduler/test_claim.py
git commit -m "feat: add atomic claim of runnable queued runs"
```

---

### Task 4: Crash recovery — fail orphaned runs

**Files:**
- Create: `src/fold_at_scripps/scheduler/recovery.py`
- Create: `tests/scheduler/test_recovery.py`

**Interfaces:**
- Consumes: `Run`, `RunStatus`; `db_session`.
- Produces: `fail_orphaned_runs(session) -> int` — marks every RUNNING run FAILED (with an error + `finished_at`); returns the count. Called at scheduler startup, since a RUNNING run after a restart means its execution was lost.

- [ ] **Step 1: Write the failing tests**

Create `tests/scheduler/test_recovery.py`:

```python
"""Tests for orphaned-run crash recovery."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Run, Tool, User
from fold_at_scripps.scheduler.recovery import fail_orphaned_runs

pytestmark = pytest.mark.integration


async def _run(session: AsyncSession, status: RunStatus) -> Run:
    user = User(email=f"{status.value}@scripps.edu", display_name="U", hashed_password="x")
    tool = Tool(name=f"t-{status.value}", version="1.0.0", category="c", input_schema={})
    session.add_all([user, tool])
    await session.commit()
    run = Run(user_id=user.id, tool_id=tool.id, params={}, status=status)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_fail_orphaned_marks_running_failed(db_session: AsyncSession) -> None:
    running = await _run(db_session, RunStatus.RUNNING)
    queued = await _run(db_session, RunStatus.QUEUED)
    done = await _run(db_session, RunStatus.SUCCEEDED)
    count = await fail_orphaned_runs(db_session)
    assert count == 1
    await db_session.refresh(running)
    await db_session.refresh(queued)
    await db_session.refresh(done)
    assert running.status is RunStatus.FAILED
    assert running.error is not None
    assert running.finished_at is not None
    assert queued.status is RunStatus.QUEUED
    assert done.status is RunStatus.SUCCEEDED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/scheduler/test_recovery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.scheduler.recovery'`.

- [ ] **Step 3: Implement recovery**

Create `src/fold_at_scripps/scheduler/recovery.py`:

```python
"""Startup recovery for runs orphaned by a scheduler crash/restart."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus


async def fail_orphaned_runs(session: AsyncSession) -> int:
    """Mark all RUNNING runs FAILED (their execution was lost). Returns the count."""
    runs = (
        (await session.execute(select(Run).where(Run.status == RunStatus.RUNNING)))
        .scalars()
        .all()
    )
    for run in runs:
        run.status = RunStatus.FAILED
        run.error = "Run interrupted by scheduler restart"
        run.finished_at = datetime.datetime.now(datetime.UTC)
    await session.commit()
    return len(runs)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/scheduler/test_recovery.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/scheduler/recovery.py tests/scheduler/test_recovery.py
git commit -m "feat: add orphaned-run crash recovery"
```

---

### Task 5: The real autobio executor

**Files:**
- Create: `src/fold_at_scripps/autobio_executor.py`
- Create: `tests/test_autobio_executor.py`

**Interfaces:**
- Consumes: `ExecutionRequest`/`ExecutionResult` (Plan 5 `executor.py`).
- Produces: `AutobioExecutor(autobio_bin="autobio")` implementing `Executor` — runs `autobio run … --format json`, derives `succeeded` from the exit code, measures wall time, sets `gpu_seconds = wall × len(gpu_ids)`, captures stderr on failure, and on success moves autobio's `outputs/` into `request.outputs_dir`. Uses a per-run workspace at `request.outputs_dir.parent / "workspace"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_autobio_executor.py`:

```python
"""Tests for the autobio CLI executor."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from fold_at_scripps.autobio_executor import AutobioExecutor, _gpu_spec
from fold_at_scripps.executor import ExecutionRequest


def test_gpu_spec_mapping() -> None:
    assert _gpu_spec([]) == "none"
    assert _gpu_spec([0]) == "0"
    assert _gpu_spec([0, 3]) == "0,3"


def _request(root: Path, gpu_ids: list[int]) -> ExecutionRequest:
    (root / "config").mkdir(parents=True)
    (root / "outputs").mkdir(parents=True)
    (root / "config" / "config.json").write_text("{}")
    return ExecutionRequest(
        tool_name="ablang2",
        tool_version="1.0.0",
        image_tag="ablang2:1.0.0",
        config_path=root / "config" / "config.json",
        outputs_dir=root / "outputs",
        gpu_ids=gpu_ids,
        timeout=300,
    )


def test_failure_from_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request(tmp_path, [0])

    def _fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = AutobioExecutor().execute(request)
    assert result.succeeded is False
    assert "boom" in (result.error or "")
    assert result.gpu_seconds is not None  # wall * 1 gpu


def test_success_moves_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request(tmp_path, [])

    def _fake_run(cmd, **kwargs):
        # emulate autobio writing a workspace with outputs/
        workspace = Path(cmd[cmd.index("--output-dir") + 1])
        (workspace / "outputs" / "raw").mkdir(parents=True)
        (workspace / "outputs" / "raw" / "emb.npy").write_text("data")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = AutobioExecutor().execute(request)
    assert result.succeeded is True
    assert (request.outputs_dir / "raw" / "emb.npy").read_text() == "data"
    assert result.gpu_seconds is None  # no gpus


@pytest.mark.skipif(shutil.which("autobio") is None, reason="autobio CLI not on PATH")
def test_real_ablang2_smoke(tmp_path: Path) -> None:
    import json

    from fold_at_scripps.storage import LocalStorage

    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    storage.write_config(
        run_id,
        {
            "sequences": [
                {
                    "id": "ab1",
                    "heavy_chain": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAKDGYYYYGMDVWGQGTTVTVSS",
                    "light_chain": "DIQMTQSPSSLSASVGDRVTITCRASQSISSYLNWYQQKPGKAPKLLIYAASSLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPLTFGGGTKVEIK",
                }
            ]
        },
    )
    request = ExecutionRequest(
        tool_name="ablang2",
        tool_version="1.0.0",
        image_tag="ghcr.io/briney/autobio-ablang2:1.0.0",
        config_path=storage.config_path(run_id),
        outputs_dir=storage.outputs_dir(run_id),
        gpu_ids=[0],
        timeout=300,
    )
    result = AutobioExecutor().execute(request)
    assert result.succeeded is True, result.error
    assert any(storage.outputs_dir(run_id).rglob("*.npy"))
    _ = json  # (kept for clarity; remove if unused)
```

(Remove the trailing `_ = json` line and the `import json` if `ruff` flags them as unused.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_autobio_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.autobio_executor'`.

- [ ] **Step 3: Implement the executor**

Create `src/fold_at_scripps/autobio_executor.py`:

```python
"""An Executor that runs tools via the autobio CLI."""

from __future__ import annotations

import shutil
import subprocess
import time

from fold_at_scripps.executor import ExecutionRequest, ExecutionResult

_ERROR_TAIL = 4000


def _gpu_spec(gpu_ids: list[int]) -> str:
    """Map assigned GPU IDs to autobio's --gpu value ('none' or 'a,b,c')."""
    if not gpu_ids:
        return "none"
    return ",".join(str(gpu_id) for gpu_id in gpu_ids)


class AutobioExecutor:
    """Runs a tool by shelling out to `autobio run` and collecting its outputs."""

    def __init__(self, autobio_bin: str = "autobio") -> None:
        self._bin = autobio_bin

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run the tool; success = exit code 0; move autobio outputs into outputs_dir."""
        workspace = request.outputs_dir.parent / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        cmd = [
            self._bin,
            "run",
            request.tool_name,
            "--config",
            str(request.config_path),
            "--gpu",
            _gpu_spec(request.gpu_ids),
            "--output-dir",
            str(workspace),
            "--format",
            "json",
        ]
        if request.timeout is not None:
            cmd += ["--timeout", str(request.timeout)]

        sub_timeout = None if request.timeout is None else request.timeout + 60
        start = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=sub_timeout)
        except subprocess.TimeoutExpired:
            wall = time.monotonic() - start
            return ExecutionResult(
                succeeded=False,
                wall_time_seconds=wall,
                gpu_seconds=self._gpu_seconds(wall, request.gpu_ids),
                error="autobio run timed out",
            )
        wall = time.monotonic() - start
        gpu_seconds = self._gpu_seconds(wall, request.gpu_ids)

        if proc.returncode != 0:
            error = (proc.stderr or proc.stdout or "autobio run failed")[-_ERROR_TAIL:]
            return ExecutionResult(
                succeeded=False, wall_time_seconds=wall, gpu_seconds=gpu_seconds, error=error
            )

        autobio_outputs = workspace / "outputs"
        if autobio_outputs.is_dir():
            for item in autobio_outputs.iterdir():
                shutil.move(str(item), str(request.outputs_dir / item.name))
        return ExecutionResult(
            succeeded=True, wall_time_seconds=wall, gpu_seconds=gpu_seconds, error=None
        )

    @staticmethod
    def _gpu_seconds(wall: float, gpu_ids: list[int]) -> float | None:
        """GPU-seconds under exclusive allocation: wall time x number of GPUs."""
        return wall * len(gpu_ids) if gpu_ids else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/test_autobio_executor.py -v`
Expected: PASS — the 3 unit tests pass; the real-autobio smoke test runs here (autobio + a GPU + the cached ablang2 image are present) and passes, or SKIPS where autobio is absent.

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/autobio_executor.py tests/test_autobio_executor.py
git commit -m "feat: add autobio CLI executor"
```

---

### Task 6: The scheduler loop

**Files:**
- Modify: `src/fold_at_scripps/config.py` (add `gpu_count`, `scheduler_poll_interval`)
- Create: `src/fold_at_scripps/scheduler/service.py`
- Create: `tests/scheduler/test_service.py`

**Interfaces:**
- Consumes: `GpuPool` (Task 2); `claim_runnable_run` (Task 3); `execute_run` (Task 1); `get_system_settings` (maintenance mode); `Executor`, `Storage`, `Run`; an `async_sessionmaker`.
- Produces: `Scheduler(sessionmaker, executor, storage, gpu_pool, poll_interval)` with `async run_once()` (reap finished dispatches → free GPUs; skip if maintenance; claim+dispatch runs that fit), `async drain()` (await in-flight dispatches; for graceful shutdown/tests), and `async run_forever()`.

- [ ] **Step 1: Add config**

In `src/fold_at_scripps/config.py`, add to `Settings` (after `storage_root`):

```python
    gpu_count: int = 8
    scheduler_poll_interval: float = 2.0
```

- [ ] **Step 2: Write the failing tests**

Create `tests/scheduler/test_service.py`:

```python
"""Tests for the scheduler loop."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fold_at_scripps.executor import FakeExecutor
from fold_at_scripps.models import RunStatus, Run, Tool, User
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.scheduler.service import Scheduler
from fold_at_scripps.storage import LocalStorage
from fold_at_scripps.system_settings import get_system_settings

pytestmark = pytest.mark.integration


async def _seed_queued(session: AsyncSession, storage: LocalStorage, n: int) -> None:
    user = User(email="sch@scripps.edu", display_name="S", hashed_password="x")
    tool = Tool(name="t", version="1.0.0", category="c", input_schema={}, gpu_count=1)
    session.add_all([user, tool])
    await session.commit()
    for _ in range(n):
        session.add(Run(user_id=user.id, tool_id=tool.id, params={}, status=RunStatus.QUEUED))
    await session.commit()
    # Create per-run storage dirs (production does this in submit_run) so the
    # executor has an outputs directory to write into.
    for run in (await session.execute(select(Run))).scalars().all():
        storage.create_run_dir(run.id)


def _scheduler(db_session: AsyncSession, storage: LocalStorage, pool: GpuPool) -> Scheduler:
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    return Scheduler(
        sessionmaker=maker,
        executor=FakeExecutor(),
        storage=storage,
        gpu_pool=pool,
        poll_interval=0.01,
    )


async def test_run_once_dispatches_up_to_capacity(tmp_path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    await _seed_queued(db_session, storage, 3)
    pool = GpuPool([0, 1])  # capacity 2
    scheduler = _scheduler(db_session, storage, pool)

    await scheduler.run_once()
    await scheduler.drain()  # finish the 2 dispatched, free their GPUs
    assert pool.available == 2

    await scheduler.run_once()  # claim the 3rd
    await scheduler.drain()

    statuses = (await db_session.execute(select(Run.status))).scalars().all()
    assert all(s is RunStatus.SUCCEEDED for s in statuses)
    assert len(statuses) == 3


async def test_run_once_respects_maintenance_mode(tmp_path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    await _seed_queued(db_session, storage, 2)
    settings = await get_system_settings(db_session)
    settings.maintenance_mode = True
    await db_session.commit()
    scheduler = _scheduler(db_session, storage, GpuPool([0, 1]))

    await scheduler.run_once()
    await scheduler.drain()

    running = (
        await db_session.execute(select(Run).where(Run.status != RunStatus.QUEUED))
    ).scalars().all()
    assert running == []  # nothing claimed while in maintenance
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/scheduler/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.scheduler.service'`.

- [ ] **Step 4: Implement the scheduler**

Create `src/fold_at_scripps/scheduler/service.py`:

```python
"""The scheduler loop: reap finished dispatches, then claim and dispatch runs."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from fold_at_scripps.executor import Executor
from fold_at_scripps.models import Run
from fold_at_scripps.runs.service import execute_run
from fold_at_scripps.scheduler.claim import claim_runnable_run
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.storage import Storage
from fold_at_scripps.system_settings import get_system_settings


class Scheduler:
    """Owns the GPU pool and drives queued runs through the executor."""

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker,
        executor: Executor,
        storage: Storage,
        gpu_pool: GpuPool,
        poll_interval: float,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._executor = executor
        self._storage = storage
        self._pool = gpu_pool
        self._poll_interval = poll_interval
        self._inflight: dict[uuid.UUID, tuple[asyncio.Task[None], list[int]]] = {}

    def _reap(self) -> None:
        """Release GPUs for finished dispatches."""
        for run_id, (task, gpu_ids) in list(self._inflight.items()):
            if task.done():
                self._pool.release(gpu_ids)
                del self._inflight[run_id]

    async def _dispatch(self, run_id: uuid.UUID) -> None:
        """Execute a claimed (RUNNING) run in its own session."""
        async with self._sessionmaker() as session:
            run = await session.get(Run, run_id)
            if run is not None:
                await execute_run(session, run, self._executor, self._storage)

    async def run_once(self) -> None:
        """One scheduling iteration: reap, then (unless in maintenance) claim+dispatch."""
        self._reap()
        async with self._sessionmaker() as session:
            settings = await get_system_settings(session)
            if settings.maintenance_mode:
                return
            while True:
                claimed = await claim_runnable_run(session, self._pool)
                if claimed is None:
                    break
                run, gpu_ids = claimed
                task = asyncio.create_task(self._dispatch(run.id))
                self._inflight[run.id] = (task, gpu_ids)

    async def drain(self) -> None:
        """Await all in-flight dispatches and reap them (graceful stop / tests)."""
        tasks = [task for task, _ in self._inflight.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._reap()

    async def run_forever(self) -> None:
        """Poll forever: schedule work, then sleep for the poll interval."""
        while True:
            await self.run_once()
            await asyncio.sleep(self._poll_interval)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/scheduler/test_service.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/config.py src/fold_at_scripps/scheduler/service.py tests/scheduler/test_service.py
git commit -m "feat: add scheduler loop"
```

---

### Task 7: Scheduler entry point

**Files:**
- Create: `src/fold_at_scripps/scheduler/main.py`
- Modify: `pyproject.toml` (add the `fold-scheduler` console script)
- Create: `tests/scheduler/test_main.py`

**Interfaces:**
- Consumes: `get_settings`, `get_sessionmaker` (db), `get_storage` (storage), `AutobioExecutor` (Task 5), `GpuPool`, `fail_orphaned_runs`, `Scheduler`.
- Produces: `build_scheduler() -> Scheduler` (wires real components from settings), `async run_scheduler()` (recover orphans, then `run_forever`), and `main()` (sync entry). Console script `fold-scheduler`.

- [ ] **Step 1: Write the failing test**

Create `tests/scheduler/test_main.py`:

```python
"""Tests for the scheduler entry point wiring."""

from __future__ import annotations

from fold_at_scripps.scheduler.main import build_scheduler
from fold_at_scripps.scheduler.service import Scheduler


def test_build_scheduler_uses_configured_gpu_count(monkeypatch) -> None:
    monkeypatch.setenv("FOLD_GPU_COUNT", "4")
    from fold_at_scripps.config import get_settings

    get_settings.cache_clear()
    scheduler = build_scheduler()
    assert isinstance(scheduler, Scheduler)
    assert scheduler._pool.available == 4
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/scheduler/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.scheduler.main'`.

- [ ] **Step 3: Implement the entry point**

Create `src/fold_at_scripps/scheduler/main.py`:

```python
"""Entry point that wires and runs the scheduler as a host process."""

from __future__ import annotations

import asyncio

from fold_at_scripps.autobio_executor import AutobioExecutor
from fold_at_scripps.config import get_settings
from fold_at_scripps.db import get_sessionmaker
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.scheduler.recovery import fail_orphaned_runs
from fold_at_scripps.scheduler.service import Scheduler
from fold_at_scripps.storage import get_storage


def build_scheduler() -> Scheduler:
    """Construct a Scheduler from application settings and the real components."""
    settings = get_settings()
    pool = GpuPool(list(range(settings.gpu_count)))
    return Scheduler(
        sessionmaker=get_sessionmaker(),
        executor=AutobioExecutor(),
        storage=get_storage(),
        gpu_pool=pool,
        poll_interval=settings.scheduler_poll_interval,
    )


async def run_scheduler() -> None:
    """Recover orphaned runs, then poll forever."""
    async with get_sessionmaker()() as session:
        await fail_orphaned_runs(session)
    await build_scheduler().run_forever()


def main() -> None:
    """Console-script entry point for the scheduler daemon."""
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add the console script**

In `pyproject.toml`, under `[project.scripts]` (alongside `fold-admin`), add:

```toml
fold-scheduler = "fold_at_scripps.scheduler.main:main"
```

Run: `uv sync`
Expected: the `fold-scheduler` entry point is registered.

- [ ] **Step 5: Run the test to verify it passes**

Run: `docker compose up -d postgres && uv run pytest tests/scheduler/test_main.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/scheduler/main.py pyproject.toml uv.lock tests/scheduler/test_main.py
git commit -m "feat: add scheduler entry point"
```

---

## Self-Review

**1. Spec coverage (against the architecture's scheduler/executor section + Plan-5 contracts):**
- Exclusive variable-count GPU allocation → `GpuPool` (Task 2) + `claim_runnable_run` (Task 3). ✓
- Atomic claim via `FOR UPDATE SKIP LOCKED` (multi-node-ready) → Task 3. ✓
- `execute_run` exception-safe + claim/execute split → Task 1. ✓
- Real autobio executor (CLI, exit-code result, output move) → Task 5. ✓
- Crash recovery (RUNNING→FAILED on restart) → Task 4. ✓
- Maintenance mode honored → Task 6. ✓
- Scheduler loop + host entry point → Tasks 6, 7. ✓
- Deferred (documented): HTTP run submission/cancel (Plan 7); admin control of maintenance/cancel-running (Plan 8); multi-node execution (future).

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases". Every code/command step is concrete; the autobio smoke test uses the verified real CLI. The one `except Exception` (Task 1) is the documented execution boundary. The two `# pragma: no cover` / conditional-`# noqa` notes are explained, not placeholders.

**3. Type/name consistency:** `GpuPool` (Task 2: `available`/`can_allocate`/`try_allocate`/`release`) is used by `claim_runnable_run` (Task 3) and `Scheduler` (Task 6). `claim_runnable_run` (Task 3) and the refactored `execute_run` (Task 1, expects RUNNING) are both driven by `Scheduler` (Task 6). `AutobioExecutor` (Task 5) implements the Plan-5 `Executor` protocol that `execute_run` and `Scheduler` consume. `fail_orphaned_runs` (Task 4) is called by `run_scheduler` (Task 7). `build_scheduler`/`run_scheduler`/`main` (Task 7) wire `get_sessionmaker`/`get_storage`/`AutobioExecutor`/`GpuPool`. Config `gpu_count`/`scheduler_poll_interval` (Task 6) are read by `build_scheduler` (Task 7). `ExecutionRequest`/`ExecutionResult` field names match Plan 5's `executor.py` throughout.
