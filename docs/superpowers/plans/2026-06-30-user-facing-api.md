# User-Facing Runs API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the run lifecycle over HTTP — submit (with file uploads), list, inspect, cancel, soft-delete, and download outputs — as a thin FastAPI adapter over the existing transport-agnostic run services, while closing two correctness gaps the Plan 5/6 reviews deferred: TOCTOU-safe quota enforcement and 404-vs-409 cancel semantics.

**Architecture:** HTTP endpoints in `api/runs.py` are a thin adapter: they authenticate via the existing `get_current_user`, translate requests into calls to `runs/service.py`, and map service exceptions to status codes. Submission is a single `multipart/form-data` request carrying `tool_id`, a JSON `params` string, and zero-or-more files; the run is staged to disk and committed as `QUEUED` atomically, so the scheduler never observes a claimable run missing its inputs. File inputs are staged via the `Storage` boundary and their config paths resolved from the tool's JSON Schema (`format: "path"` fields). Quota enforcement is made atomic by locking the user row (`SELECT … FOR UPDATE`) for the duration of the submit transaction, serializing that user's concurrent submissions.

**Tech Stack:** FastAPI (`APIRouter`, `Form`, `File`, `UploadFile`, `FileResponse`), `python-multipart` (form parsing), SQLAlchemy 2.0 async (`with_for_update`, conditional `UPDATE`), Pydantic v2 response models, pytest + httpx `ASGITransport`.

## Global Constraints

- Python `>=3.11`; ruff (E,F,I,UP,B) `target-version = "py311"`; max line length **100**.
- `src/` layout; package **`fold_at_scripps`**; `uv` for all commands (`uv run …`, `uv sync`).
- Type hints on all signatures; `from __future__ import annotations` in **every** module (docstring-only `__init__.py` exempt); Google-style docstrings on public classes/functions.
- Absolute imports only. Catch specific exceptions (no bare `except:`; `except Exception` only at a documented boundary). Enum/StrEnum for categoricals; Pydantic `BaseModel` with `ConfigDict(from_attributes=True)` for API response schemas; no mutable default arguments.
- Async relationship access requires eager loading — every ORM object serialized by a response model must have its accessed relationships `selectinload`ed (never rely on lazy loading in async; it raises `MissingGreenlet`).
- Tests: pytest, TDD. API/service tests that touch Postgres are `@pytest.mark.integration` and use the `db_session` fixture + the `_client()`/`_login()` patterns already in `tests/api/test_tools.py`. No real GPUs/autobio.

## Carried-in contracts (from Plan 5 & Plan 6 final reviews)

- **Quota is TOCTOU-unsafe** (`runs/quota.py::check_quota` counts-then-inserts). This plan makes submission atomic per user (Task 2).
- **`cancel_run` conflates not-found and not-cancelable.** This plan splits them into `RunNotFound` (→404) and `RunNotCancelable` (→409) and makes the transition atomic against the scheduler's claim (Task 3).

## File Structure

- `src/fold_at_scripps/storage.py` (modify) — add `write_input` and `remove_run_dir` to the `Storage` Protocol and `LocalStorage`.
- `src/fold_at_scripps/runs/service.py` (modify) — `InputFile` dataclass; `submit_run` gains atomic quota + input staging + path resolution; new `RunNotFound`; `cancel_run` split 404/409 and made atomic.
- `src/fold_at_scripps/schemas/runs.py` (create) — `ToolRef`, `ArtifactRead`, `RunSummary`, `RunRead`.
- `src/fold_at_scripps/api/runs.py` (create) — the `/runs` router (submit, list, get, cancel, delete, artifact download).
- `src/fold_at_scripps/main.py` (modify) — include the runs router.
- `pyproject.toml` (modify) — add `python-multipart` dependency.
- Tests: `tests/test_storage.py` (extend), `tests/runs/test_submit.py` (extend), `tests/runs/test_lifecycle.py` (extend), `tests/api/test_runs.py` (create).

---

### Task 1: `Storage.write_input` and `remove_run_dir`

Add the two `Storage` operations submission needs: staging an uploaded input file (reusing the existing `input_path` traversal guard) and best-effort removal of a run's directory tree for rollback cleanup.

**Files:**
- Modify: `src/fold_at_scripps/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: existing `LocalStorage.input_path(run_id, filename) -> Path` (traversal-guarded), `run_root(run_id) -> Path`, `create_run_dir(run_id)`.
- Produces:
  - `Storage.write_input(run_id: uuid.UUID, filename: str, content: bytes) -> str` — writes bytes to `inputs/<filename>`, returns the run-root-relative path `"inputs/<filename>"`.
  - `Storage.remove_run_dir(run_id: uuid.UUID) -> None` — best-effort recursive removal of the run root; no error if absent.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_storage.py`:

```python
def test_write_input_writes_bytes_and_returns_relative_path(tmp_path):
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)

    rel = storage.write_input(run_id, "seqs.fasta", b">a\nACDE\n")

    assert rel == "inputs/seqs.fasta"
    assert storage.input_path(run_id, "seqs.fasta").read_bytes() == b">a\nACDE\n"


def test_write_input_creates_missing_inputs_dir(tmp_path):
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()  # note: create_run_dir NOT called

    storage.write_input(run_id, "x.txt", b"hi")

    assert storage.input_path(run_id, "x.txt").read_bytes() == b"hi"


def test_write_input_rejects_traversal(tmp_path):
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    with pytest.raises(ValueError):
        storage.write_input(run_id, "../escape.txt", b"nope")


def test_remove_run_dir_deletes_tree_and_is_idempotent(tmp_path):
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    storage.write_input(run_id, "a.txt", b"a")

    storage.remove_run_dir(run_id)
    assert not storage.run_root(run_id).exists()

    storage.remove_run_dir(run_id)  # idempotent: no error when already gone
```

Ensure `tests/test_storage.py` imports `uuid`, `pytest`, and `LocalStorage` (add any missing).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -q`
Expected: FAIL (`AttributeError: 'LocalStorage' object has no attribute 'write_input'`).

- [ ] **Step 3: Implement**

In `src/fold_at_scripps/storage.py`, add `import shutil` (top, stdlib group). Add to the `Storage` Protocol (near `input_path`):

```python
    def write_input(self, run_id: uuid.UUID, filename: str, content: bytes) -> str: ...
    def remove_run_dir(self, run_id: uuid.UUID) -> None: ...
```

Add to `LocalStorage`:

```python
    def write_input(self, run_id: uuid.UUID, filename: str, content: bytes) -> str:
        """Stage an uploaded input file under ``inputs/``; return its relative path."""
        path = self.input_path(run_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"inputs/{path.name}"

    def remove_run_dir(self, run_id: uuid.UUID) -> None:
        """Best-effort recursive removal of the run's directory tree."""
        shutil.rmtree(self.run_root(run_id), ignore_errors=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/storage.py tests/test_storage.py
git commit -m "feat(storage): add write_input and remove_run_dir"
```

---

### Task 2: Atomic quota + input staging + config path resolution in `submit_run`

Make submission TOCTOU-safe (lock the user row) and stage uploaded files, writing the tool config with path-typed params resolved to the files' absolute staged paths. `Run.params` keeps the user-facing values (filenames); `config.json` on disk gets the resolved absolute paths for autobio.

**Files:**
- Modify: `src/fold_at_scripps/runs/service.py`
- Test: `tests/runs/test_submit.py`

**Interfaces:**
- Consumes: `Storage.write_input`, `Storage.input_path`, `Storage.remove_run_dir` (Task 1); `runs/quota.py::check_quota`; `runs/validation.py::validate_params`.
- Produces:
  - `InputFile` dataclass: `filename: str`, `content: bytes` (frozen).
  - `submit_run(session, *, user, tool, params, storage, inputs: Sequence[InputFile] | None = None) -> Run` — validates, locks the user row, enforces quota, stages inputs, writes resolved config, commits `QUEUED`. Rolls back and removes the run dir on any failure after row creation.
  - Behavior contract used by later tasks: `Run.params` == the submitted params; the on-disk config resolves top-level `format: "path"` fields whose value names an uploaded file to that file's absolute staged path.

- [ ] **Step 1: Write the failing tests**

Add to `tests/runs/test_submit.py` (reuse the file's existing user/tool seeding helpers; if it seeds a tool with a plain schema, add a small helper for a path-typed schema as shown):

```python
import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fold_at_scripps.config import get_settings
from fold_at_scripps.models import Run, Tool, User
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import InputFile, submit_run


async def test_submit_stages_inputs_and_resolves_config_paths(db_session, storage_tmp):
    user = await _make_active_user(db_session)
    tool = await _make_tool(
        db_session,
        input_schema={
            "type": "object",
            "properties": {"structure_path": {"type": "string", "format": "path"}},
            "required": ["structure_path"],
        },
    )

    run = await submit_run(
        db_session,
        user=user,
        tool=tool,
        params={"structure_path": "backbone.pdb"},
        storage=storage_tmp,
        inputs=[InputFile(filename="backbone.pdb", content=b"ATOM  ...")],
    )

    # File staged to inputs/.
    assert storage_tmp.input_path(run.id, "backbone.pdb").read_bytes() == b"ATOM  ..."
    # Run.params keeps the user-facing filename.
    assert run.params["structure_path"] == "backbone.pdb"
    # config.json resolves the path field to the absolute staged path.
    config = json.loads(storage_tmp.config_path(run.id).read_text())
    assert config["structure_path"] == str(storage_tmp.input_path(run.id, "backbone.pdb"))


async def test_submit_quota_atomic_under_concurrency(db_session, storage_tmp):
    user = await _make_active_user(db_session)
    user.max_concurrent_runs_override = 1
    tool = await _make_tool(db_session, input_schema={"type": "object"})
    await db_session.commit()
    user_id, tool_id = user.id, tool.id

    # A second engine to the same database gives the two attempts independent
    # connections/transactions that genuinely contend on the user row lock.
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _attempt() -> str:
        async with maker() as s:
            u = await s.get(User, user_id)
            t = await s.get(Tool, tool_id)
            try:
                await submit_run(s, user=u, tool=t, params={}, storage=storage_tmp)
                return "ok"
            except QuotaExceeded:
                return "quota"

    try:
        results = await asyncio.gather(_attempt(), _attempt())
    finally:
        await engine.dispose()

    assert sorted(results) == ["ok", "quota"]  # exactly one succeeded; GREEN is deterministic
    count = await db_session.scalar(
        select(func.count()).select_from(Run).where(Run.user_id == user_id)
    )
    assert count == 1
```

Notes for the implementer:
- `storage_tmp` is a fixture returning `LocalStorage(tmp_path)`. If it does not exist in this test module/conftest, add it locally:
  ```python
  @pytest.fixture
  def storage_tmp(tmp_path):
      from fold_at_scripps.storage import LocalStorage
      return LocalStorage(tmp_path)
  ```
- `_make_active_user` / `_make_tool` are the module's existing seed helpers; adapt names to what the file already uses. `_make_tool` must accept an `input_schema` argument (extend it if needed).
- The concurrency test is `@pytest.mark.integration` (real Postgres row locks). Determinism comes from the `FOR UPDATE` lock added in Step 3; without it, the two attempts can both pass the count check and create two runs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runs/test_submit.py -q`
Expected: FAIL — `ImportError: cannot import name 'InputFile'`, and (once importable) the concurrency test creates 2 runs.

- [ ] **Step 3: Implement**

In `src/fold_at_scripps/runs/service.py`:

Add imports: `from collections.abc import Sequence`, `from dataclasses import dataclass`. Ensure `from sqlalchemy import select` is present (it is).

Add near the top (after imports):

```python
@dataclass(frozen=True)
class InputFile:
    """An uploaded input file to stage for a run."""

    filename: str
    content: bytes


def _resolve_input_paths(
    params: dict[str, Any], schema: dict[str, Any], staged: dict[str, str]
) -> dict[str, Any]:
    """Return params with top-level ``format: 'path'`` fields naming an uploaded file
    rewritten to that file's absolute staged path. Other values pass through unchanged.
    """
    properties = schema.get("properties", {})
    resolved = dict(params)
    for key, spec in properties.items():
        if isinstance(spec, dict) and spec.get("format") == "path" and key in resolved:
            value = resolved[key]
            if isinstance(value, str) and value in staged:
                resolved[key] = staged[value]
    return resolved
```

Replace `submit_run` with:

```python
async def submit_run(
    session: AsyncSession,
    *,
    user: User,
    tool: Tool,
    params: dict[str, Any],
    storage: Storage,
    inputs: Sequence[InputFile] | None = None,
) -> Run:
    """Validate params, enforce the quota atomically, stage inputs, and queue a run.

    Concurrent submissions by the same user are serialized via a row lock on the user
    (``SELECT … FOR UPDATE``) held until commit, so the quota check cannot race. The
    run's config is written with path-typed params resolved to staged input paths;
    ``Run.params`` retains the user-supplied values.

    Raises:
        InvalidParams: params do not satisfy the tool's input schema.
        QuotaExceeded: the user is at their concurrency limit.
    """
    inputs = inputs or ()
    validate_params(params, tool.input_schema)

    # Serialize this user's concurrent submissions so the quota check is atomic.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    await check_quota(session, user)

    run = Run(user_id=user.id, tool_id=tool.id, params=params, status=RunStatus.QUEUED)
    session.add(run)
    await session.flush()  # assign run.id
    run_id = run.id

    try:
        storage.create_run_dir(run_id)
        staged: dict[str, str] = {}
        for item in inputs:
            storage.write_input(run_id, item.filename, item.content)
            staged[item.filename] = str(storage.input_path(run_id, item.filename))
        storage.write_config(run_id, _resolve_input_paths(params, tool.input_schema, staged))
        run.output_dir = str(storage.run_root(run_id))
        await session.commit()
    except Exception:
        # Never leave a half-written run: undo the transaction and remove staged files.
        await session.rollback()
        storage.remove_run_dir(run_id)
        raise

    await session.refresh(run)
    return run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/runs/test_submit.py -q`
Expected: PASS. Also run the executor/scheduler suites that consume `submit_run`/config to confirm no regression:
Run: `uv run pytest tests/runs -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/runs/service.py tests/runs/test_submit.py
git commit -m "feat(runs): atomic quota + input staging + config path resolution in submit_run"
```

---

### Task 3: `cancel_run` — 404 vs 409, atomic against the scheduler

Split the conflated error into `RunNotFound` (unknown/not-owned/hidden) and `RunNotCancelable` (found but not `QUEUED`), and perform the transition with a conditional `UPDATE … WHERE status = QUEUED` so it is atomic against the scheduler's concurrent claim.

**Files:**
- Modify: `src/fold_at_scripps/runs/service.py`
- Test: `tests/runs/test_lifecycle.py`

**Interfaces:**
- Consumes: existing `get_run` (ownership + hidden filtering + eager tool/artifacts).
- Produces:
  - `RunNotFound(Exception)`.
  - `cancel_run(session, user, run_id) -> Run` — raises `RunNotFound` if `get_run` returns None; raises `RunNotCancelable` if the conditional cancel updates 0 rows; otherwise returns the reloaded (eager-loaded, `CANCELED`) run.

- [ ] **Step 1: Write the failing tests**

In `tests/runs/test_lifecycle.py`, update/add (adapt to the file's existing seed helpers):

```python
import uuid

import pytest

from fold_at_scripps.models import RunStatus
from fold_at_scripps.runs.service import (
    RunNotCancelable,
    RunNotFound,
    cancel_run,
)


async def test_cancel_unknown_run_raises_not_found(db_session):
    user = await _make_active_user(db_session)
    with pytest.raises(RunNotFound):
        await cancel_run(db_session, user, uuid.uuid4())


async def test_cancel_running_run_raises_not_cancelable(db_session):
    user = await _make_active_user(db_session)
    run = await _make_run(db_session, user, status=RunStatus.RUNNING)
    with pytest.raises(RunNotCancelable):
        await cancel_run(db_session, user, run.id)


async def test_cancel_queued_run_succeeds(db_session):
    user = await _make_active_user(db_session)
    run = await _make_run(db_session, user, status=RunStatus.QUEUED)
    canceled = await cancel_run(db_session, user, run.id)
    assert canceled.status is RunStatus.CANCELED
```

If the file already has a cancel test asserting `RunNotCancelable` for a missing run, change that expectation to `RunNotFound`. `_make_run` is the file's helper for creating a Run in a given status (extend it to accept `status=`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runs/test_lifecycle.py -q`
Expected: FAIL — `ImportError: cannot import name 'RunNotFound'`.

- [ ] **Step 3: Implement**

In `src/fold_at_scripps/runs/service.py` add `update` to the sqlalchemy import: `from sqlalchemy import select, update`.

Add the exception (next to `RunNotCancelable`):

```python
class RunNotFound(Exception):
    """Raised when a run does not exist or is not visible to the user."""
```

Replace `cancel_run` with:

```python
async def cancel_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run:
    """Cancel the user's queued run.

    Raises:
        RunNotFound: no such run for this user (unknown, not owned, or hidden).
        RunNotCancelable: the run exists but is not QUEUED (e.g. already claimed).
    """
    run = await get_run(session, user, run_id)
    if run is None:
        raise RunNotFound(f"Run {run_id} not found")
    # Atomic against the scheduler's claim: only cancel if still QUEUED.
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == RunStatus.QUEUED)
        .values(status=RunStatus.CANCELED)
    )
    if result.rowcount == 0:
        await session.rollback()
        raise RunNotCancelable("Only queued runs can be canceled")
    await session.commit()
    await session.refresh(run)
    return run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/runs/test_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/runs/service.py tests/runs/test_lifecycle.py
git commit -m "feat(runs): cancel_run distinguishes not-found (404) from not-cancelable (409)"
```

---

### Task 4: Run response schemas + submit endpoint + router wiring

Create the `/runs` router with the multipart submit endpoint (the plan's most involved endpoint), define all run response schemas it and later tasks use, wire the router into the app, and add the `python-multipart` dependency that FastAPI's form parsing requires.

**Files:**
- Create: `src/fold_at_scripps/schemas/runs.py`
- Create: `src/fold_at_scripps/api/runs.py`
- Modify: `src/fold_at_scripps/main.py`
- Modify: `pyproject.toml`
- Test: `tests/api/test_runs.py`

**Interfaces:**
- Consumes: `get_current_user`; `get_session`; `get_storage` (as a FastAPI dependency); `catalog.service.get_enabled_tool`; `runs.service.submit_run`, `get_run`, `InputFile`; `runs.validation.InvalidParams`; `runs.quota.QuotaExceeded`.
- Produces (schemas, all `ConfigDict(from_attributes=True)`):
  - `ToolRef`: `id: uuid.UUID`, `name: str`, `version: str`, `category: str`.
  - `ArtifactRead`: `name: str`, `path: str`, `size_bytes: int`, `content_type: str | None`.
  - `RunSummary`: `id`, `tool: ToolRef`, `status: RunStatus`, `created_at`, `started_at: … | None`, `finished_at: … | None`.
  - `RunRead(RunSummary)`: `params: dict[str, Any]`, `assigned_gpu_ids: list[int] | None`, `wall_time_seconds: float | None`, `gpu_seconds: float | None`, `error: str | None`, `artifacts: list[ArtifactRead]`.
- Produces (endpoint): `POST /runs` (multipart) → 201 `RunRead`; router `router` importable for later tasks to extend.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_runs.py`:

```python
"""Tests for the user-facing runs API."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, Tool, User, UserStatus

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _tmp_storage_root(tmp_path, monkeypatch):
    """Redirect storage_root to a tmp dir so real file staging never touches the repo.

    ``storage_root`` defaults to ``./data`` (CWD-relative); the submit and download
    endpoints stage/serve real files, so isolate them per test. Clear the settings
    cache after setting the env var so both create_app() and get_storage() pick it up.
    """
    monkeypatch.setenv("FOLD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _record(name: str = "antifold") -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category="inverse-folding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=False,
        description="desc",
        image_tag=f"{name}:1.0.0",
        input_schema={
            "type": "object",
            "properties": {"structure_path": {"type": "string", "format": "path"}},
            "required": ["structure_path"],
        },
    )


async def _seed_tool(session: AsyncSession) -> Tool:
    await sync_catalog(session, FakeToolSource([_record()]))
    return await session.scalar(select(Tool).where(Tool.name == "antifold"))


async def _login(client: AsyncClient, session: AsyncSession, email: str = "u@scripps.edu") -> User:
    session.add(AllowedEmail(email=email))
    await session.commit()
    await client.post(
        "/auth/register", json={"email": email, "password": "s3cret-pw", "display_name": "U"}
    )
    user = await session.scalar(select(User).where(User.email == email))
    user.status = UserStatus.ACTIVE
    await session.commit()
    await client.post("/auth/login", json={"email": email, "password": "s3cret-pw"})
    return user


async def test_submit_requires_auth(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        resp = await client.post(
            "/runs",
            data={"tool_id": str(tool.id), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 401


async def test_submit_creates_queued_run_with_file(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.post(
            "/runs",
            data={"tool_id": str(tool.id), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "queued"
        assert body["tool"]["name"] == "antifold"
        assert body["params"]["structure_path"] == "b.pdb"
        assert body["artifacts"] == []


async def test_submit_invalid_params_returns_422(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        # structure_path is required; omit it.
        resp = await client.post(
            "/runs", data={"tool_id": str(tool.id), "params": json.dumps({})}
        )
        assert resp.status_code == 422


async def test_submit_bad_params_json_returns_422(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.post("/runs", data={"tool_id": str(tool.id), "params": "not-json"})
        assert resp.status_code == 422


async def test_submit_unknown_tool_returns_404(db_session: AsyncSession) -> None:
    await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.post(
            "/runs",
            data={"tool_id": str(uuid.uuid4()), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 404


async def test_submit_quota_exceeded_returns_429(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        user = await _login(client, db_session)
        user.max_concurrent_runs_override = 0
        await db_session.commit()
        resp = await client.post(
            "/runs",
            data={"tool_id": str(tool.id), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 429
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_runs.py -q`
Expected: FAIL (404 on `/runs` — route not registered; or import error).

- [ ] **Step 3: Add the dependency**

In `pyproject.toml`, add to `[project].dependencies` (keep the list sorted/grouped as the file already is):

```
    "python-multipart>=0.0.9",
```

Run: `uv sync` (updates `uv.lock`).

- [ ] **Step 4: Implement the schemas**

Create `src/fold_at_scripps/schemas/runs.py`:

```python
"""Run response schemas."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from fold_at_scripps.models import RunStatus


class ToolRef(BaseModel):
    """Compact reference to the tool a run used."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    category: str


class ArtifactRead(BaseModel):
    """An output file produced by a run."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    path: str
    size_bytes: int
    content_type: str | None


class RunSummary(BaseModel):
    """Compact run representation for listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool: ToolRef
    status: RunStatus
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None


class RunRead(RunSummary):
    """Full run representation, including params and artifacts."""

    params: dict[str, Any]
    assigned_gpu_ids: list[int] | None
    wall_time_seconds: float | None
    gpu_seconds: float | None
    error: str | None
    artifacts: list[ArtifactRead]
```

- [ ] **Step 5: Implement the router + submit endpoint**

Create `src/fold_at_scripps/api/runs.py`:

```python
"""User-facing run endpoints: submit, list, inspect, cancel, delete, download."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.catalog.service import get_enabled_tool
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import InputFile, get_run, submit_run
from fold_at_scripps.runs.validation import InvalidParams
from fold_at_scripps.schemas.runs import RunRead
from fold_at_scripps.storage import Storage, get_storage

router = APIRouter(prefix="/runs", tags=["runs"])


def _parse_params(raw: str) -> dict[str, Any]:
    """Parse the ``params`` form field as a JSON object, or raise 422."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"params is not valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="params must be a JSON object",
        )
    return parsed


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def submit(
    tool_id: uuid.UUID = Form(...),
    params: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Any:
    """Submit a run: validate, enforce quota, stage inputs, and queue it."""
    parsed = _parse_params(params)
    tool = await get_enabled_tool(session, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    inputs = [
        InputFile(filename=f.filename, content=await f.read()) for f in files if f.filename
    ]
    try:
        run = await submit_run(
            session, user=user, tool=tool, params=parsed, storage=storage, inputs=inputs
        )
    except InvalidParams as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    return await get_run(session, user, run.id)
```

Note: `get_storage` takes no arguments, so `Depends(get_storage)` works directly. The endpoint returns the `get_run` result (tool + artifacts eager-loaded) so `RunRead` serialization never touches a lazy relationship.

- [ ] **Step 6: Wire the router**

In `src/fold_at_scripps/main.py`, import and include it alongside the others:

```python
from fold_at_scripps.api.runs import router as runs_router
...
    app.include_router(runs_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_runs.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/fold_at_scripps/schemas/runs.py src/fold_at_scripps/api/runs.py \
    src/fold_at_scripps/main.py pyproject.toml uv.lock tests/api/test_runs.py
git commit -m "feat(api): runs router with multipart submit endpoint"
```

---

### Task 5: List, get, cancel, and delete endpoints

Add the remaining lifecycle endpoints to the runs router, mapping service results and exceptions to status codes.

**Files:**
- Modify: `src/fold_at_scripps/api/runs.py`
- Test: `tests/api/test_runs.py`

**Interfaces:**
- Consumes: `runs.service.list_runs`, `get_run`, `cancel_run`, `soft_delete_run`, `RunNotFound`, `RunNotCancelable`; `schemas.runs.RunSummary`, `RunRead`.
- Produces: `GET /runs` → `list[RunSummary]`; `GET /runs/{run_id}` → `RunRead` (404); `POST /runs/{run_id}/cancel` → `RunRead` (404/409); `DELETE /runs/{run_id}` → 204 (404).

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_runs.py` (reuse `_seed_tool`, `_login`, `_client`; helper to submit a run via the API):

```python
async def _submit(client: AsyncClient, tool_id: uuid.UUID) -> dict:
    resp = await client.post(
        "/runs",
        data={"tool_id": str(tool_id), "params": json.dumps({"structure_path": "b.pdb"})},
        files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
    )
    assert resp.status_code == 201
    return resp.json()


async def test_list_runs_returns_users_runs(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        await _submit(client, tool.id)
        resp = await client.get("/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["tool"]["name"] == "antifold"
        assert "artifacts" not in body[0]  # summary shape


async def test_get_run_detail_and_404(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        ok = await client.get(f"/runs/{run['id']}")
        assert ok.status_code == 200
        assert ok.json()["id"] == run["id"]
        missing = await client.get(f"/runs/{uuid.uuid4()}")
        assert missing.status_code == 404


async def test_cancel_endpoint_200_404_409(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        ok = await client.post(f"/runs/{run['id']}/cancel")
        assert ok.status_code == 200
        assert ok.json()["status"] == "canceled"
        again = await client.post(f"/runs/{run['id']}/cancel")  # now CANCELED, not queued
        assert again.status_code == 409
        missing = await client.post(f"/runs/{uuid.uuid4()}/cancel")
        assert missing.status_code == 404


async def test_delete_run_204_then_hidden(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        deleted = await client.delete(f"/runs/{run['id']}")
        assert deleted.status_code == 204
        assert (await client.get("/runs")).json() == []
        assert (await client.get(f"/runs/{run['id']}")).status_code == 404
        missing = await client.delete(f"/runs/{uuid.uuid4()}")
        assert missing.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_runs.py -q`
Expected: FAIL (405/404 — routes not defined).

- [ ] **Step 3: Implement**

Add to `src/fold_at_scripps/api/runs.py`. Extend imports:

```python
from fold_at_scripps.runs.service import (
    InputFile,
    RunNotCancelable,
    RunNotFound,
    cancel_run,
    get_run,
    list_runs,
    soft_delete_run,
    submit_run,
)
from fold_at_scripps.schemas.runs import RunRead, RunSummary
```

Add the endpoints:

```python
@router.get("", response_model=list[RunSummary])
async def list_user_runs(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """List the current user's non-hidden runs, newest first."""
    return await list_runs(session, user)


@router.get("/{run_id}", response_model=RunRead)
async def get_user_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """Return one of the current user's runs, with artifacts."""
    run = await get_run(session, user, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/{run_id}/cancel", response_model=RunRead)
async def cancel_user_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """Cancel a queued run."""
    try:
        return await cancel_run(session, user, run_id)
    except RunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunNotCancelable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    """Soft-delete (hide) a run from the user's history."""
    run = await soft_delete_run(session, user, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_runs.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/api/runs.py tests/api/test_runs.py
git commit -m "feat(api): list, get, cancel, and delete run endpoints"
```

---

### Task 6: Artifact download endpoint

Stream a run's output file by its run-root-relative artifact path, restricted to the run's own indexed artifacts, ownership-checked via `get_run`, and traversal-guarded.

**Files:**
- Modify: `src/fold_at_scripps/api/runs.py`
- Test: `tests/api/test_runs.py`

**Interfaces:**
- Consumes: `get_run` (ownership + eager `artifacts`); `Storage.outputs_dir`; `fastapi.responses.FileResponse`.
- Produces: `GET /runs/{run_id}/artifacts/{artifact_path:path}` → streamed file (404 if run/artifact missing or path escapes the outputs dir).

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_runs.py`:

```python
from fold_at_scripps.models import Artifact
from fold_at_scripps.storage import get_storage


async def _make_output(db_session: AsyncSession, run_id: uuid.UUID, rel: str, data: bytes) -> None:
    """Write a real output file and index it as an Artifact (simulates a finished run)."""
    storage = get_storage()
    target = storage.outputs_dir(run_id) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    db_session.add(
        Artifact(run_id=run_id, name=target.name, path=rel, content_type="text/plain",
                 size_bytes=len(data))
    )
    await db_session.commit()


async def test_download_artifact_streams_file(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        run_id = uuid.UUID(run["id"])
        await _make_output(db_session, run_id, "raw/result.txt", b"HELLO")
        resp = await client.get(f"/runs/{run_id}/artifacts/raw/result.txt")
        assert resp.status_code == 200
        assert resp.content == b"HELLO"


async def test_download_unknown_artifact_404(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        resp = await client.get(f"/runs/{run['id']}/artifacts/nope.txt")
        assert resp.status_code == 404


async def test_download_requires_ownership(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as owner:
        await _login(owner, db_session, email="owner@scripps.edu")
        run = await _submit(owner, tool.id)
        run_id = uuid.UUID(run["id"])
        await _make_output(db_session, run_id, "raw/result.txt", b"SECRET")
    async with _client() as other:
        await _login(other, db_session, email="other@scripps.edu")
        resp = await other.get(f"/runs/{run_id}/artifacts/raw/result.txt")
        assert resp.status_code == 404
```

Note: `_make_output` and the app must resolve to the *same* storage root. The autouse `_tmp_storage_root` fixture (added in Task 4) sets `FOLD_STORAGE_ROOT` and clears the settings cache, so `get_storage()` in both the test and the app point at the same per-test tmp dir. No further override is needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_runs.py -q`
Expected: FAIL (404 route missing / streaming not implemented).

- [ ] **Step 3: Implement**

In `src/fold_at_scripps/api/runs.py` add `from fastapi.responses import FileResponse`. Add the endpoint (place it after `get_user_run` so the more specific path is registered; FastAPI matches by declaration but the `:path` converter is unambiguous here):

```python
@router.get("/{run_id}/artifacts/{artifact_path:path}")
async def download_artifact(
    run_id: uuid.UUID,
    artifact_path: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> FileResponse:
    """Stream one of the run's output files (ownership-checked, traversal-guarded)."""
    run = await get_run(session, user, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    artifact = next((a for a in run.artifacts if a.path == artifact_path), None)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    outputs = storage.outputs_dir(run_id).resolve()
    target = (outputs / artifact_path).resolve()
    if not target.is_relative_to(outputs) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return FileResponse(
        target, filename=artifact.name, media_type=artifact.content_type or "application/octet-stream"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_runs.py -q`
Expected: PASS.

- [ ] **Step 5: Full-suite check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: ruff clean; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/api/runs.py tests/api/test_runs.py
git commit -m "feat(api): artifact download endpoint"
```

---

## Self-Review notes (for the executor)

- **Response eager-loading:** `RunRead` includes `tool` and `artifacts`; every endpoint returning `RunRead` returns a `get_run` result (both `selectinload`ed). `list` returns `RunSummary` (only `tool`, which `list_runs` loads). Do not return the bare `submit_run`/`cancel_run` object to a `RunRead` route without going through `get_run`.
- **`Run.params` vs config.json:** `Run.params` (and thus the API) shows user-supplied values (filenames); the on-disk config resolves path fields to absolute staged paths. Keep this split.
- **Atomicity:** the user-row lock (Task 2) and the conditional cancel `UPDATE` (Task 3) are the two correctness fixes — do not "simplify" them back into count-then-write / read-then-write.
- **Out of scope (later plans):** admin oversight of all users' runs (Plan 8); pagination/filtering of `GET /runs` (add when needed — YAGNI now); resumable/chunked uploads; per-file size limits (consider in Plan 10 hardening alongside a body-size limit).
</content>
