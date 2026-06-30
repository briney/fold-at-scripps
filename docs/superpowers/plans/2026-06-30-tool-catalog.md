# Tool Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate and serve the fold@Scripps tool catalog from autobio — extend the `Tool` model with the metadata autobio exposes, define a `ToolSource` boundary with an `AutobioToolSource` (CLI adapter) and a `FakeToolSource` for tests, a `sync_catalog` service that upserts tools (preserving admin enable/disable), a read API (`GET /tools`, `GET /tools/{id}`), and a `sync-catalog` CLI command.

**Architecture:** autobio is the source of truth; the app snapshots it into the `tools` table. A `ToolSource` protocol decouples the sync logic from autobio: `AutobioToolSource` shells out to the `autobio` CLI (`list`/`info --format json`) — autobio is on PATH but deliberately NOT a Python dependency — while `FakeToolSource` drives tests. The sync logic, read service, and API are all autobio-independent (tested with the fake / direct rows); only the thin CLI adapter touches autobio, and its real-CLI test skips when autobio is absent (like the Postgres skip).

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, Pydantic v2, FastAPI, Typer, `subprocess` (autobio CLI), pytest + httpx, Postgres.

## Global Constraints

- Python `>=3.11`; ruff `target-version = "py311"`; max line length **100**.
- `src/` layout; package **`fold_at_scripps`**; `uv` for all commands.
- Type hints on all signatures; `from __future__ import annotations` in **every** module (docstring-only `__init__.py` files are exempt, per the convention codified in Plan 3's review); Google-style docstrings on public classes/functions.
- Absolute imports only.
- `subprocess` calls use a list of args (never `shell=True`); pass an explicit `timeout`; `check=True` and handle `CalledProcessError`.
- The catalog snapshots the **full** autobio tool contract: `Tool` gains `description`, `image_tag`, `default_timeout`, `supports_batch` (in addition to the existing `name`, `version`, `category`, `gpu_count`, `input_schema`, `enabled`).
- `sync_catalog` **never overwrites the `enabled` flag** on existing tools (admin-controlled); new tools default to `enabled=True`. Tools absent from the source are left as-is in v1 (no auto-delete/disable).
- Catalog read endpoints require an authenticated active user (`get_current_user`) and expose only **enabled** tools (admin views of disabled tools come in Plan 8).
- Tests use `pytest` (TDD). DB-touching tests are `@pytest.mark.integration` and use the shared `db_session` fixture; the real-autobio test uses `@pytest.mark.skipif(shutil.which("autobio") is None, ...)`.

## autobio CLI reference (verified)

- `autobio list --format json` → JSON array; each item: `{"name", "category", "gpu" (bool), "version", "description"}`. (No `input_schema`; enumerates tools.)
- `autobio info <name> --format json` → object: `{"name", "category", "image_tag", "requires_gpu" (bool), "gpu_count" (int), "default_timeout" (int, seconds), "supports_batch" (bool), "version", "description", "input_schema" (JSON Schema object)}`.
- Categories are hyphenated, e.g. `embedding`, `inverse-folding`, `structure-prediction`, `scoring`, `structure-design`, `simulation`. Stored verbatim in `Tool.category`.

## Out of scope (later plans)

- Admin-triggered sync + per-tool enable/disable endpoints → Plan 8 (admin console). This plan provides the `sync_catalog` service + a `sync-catalog` CLI to populate the catalog.
- Running tools / using `image_tag`/`default_timeout` for execution → Plan 6 (scheduler/executor) reads them from the catalog.
- Auto-disabling tools that disappear from autobio → future.

---

### Task 1: Extend the Tool model and migrate

**Files:**
- Modify: `src/fold_at_scripps/models/tool.py`
- Modify: `tests/models/test_tool.py`
- Create: `migrations/versions/<generated>_add_tool_metadata.py` (via autogenerate)

**Interfaces:**
- Consumes: existing `Tool` model.
- Produces: `Tool` gains `description: str | None`, `image_tag: str | None`, `default_timeout: int | None`, `supports_batch: bool` (default False); plus the migration that adds these columns.

- [ ] **Step 1: Write the failing test**

Add to `tests/models/test_tool.py` a test for the new fields:

```python
async def test_tool_metadata_fields(db_session: AsyncSession) -> None:
    tool = Tool(
        name="proteinmpnn",
        version="1.0.0",
        category="inverse-folding",
        gpu_count=1,
        input_schema={},
        description="Design sequences for a backbone.",
        image_tag="proteinmpnn:1.0.0",
        default_timeout=600,
        supports_batch=True,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    assert tool.description == "Design sequences for a backbone."
    assert tool.image_tag == "proteinmpnn:1.0.0"
    assert tool.default_timeout == 600
    assert tool.supports_batch is True


async def test_tool_metadata_defaults(db_session: AsyncSession) -> None:
    tool = Tool(name="esmfold", version="1.0.0", category="structure-prediction", input_schema={})
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    assert tool.description is None
    assert tool.image_tag is None
    assert tool.default_timeout is None
    assert tool.supports_batch is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose up -d postgres && uv run pytest tests/models/test_tool.py::test_tool_metadata_fields -v`
Expected: FAIL — `TypeError`/`AttributeError` (the new keyword args/attributes don't exist).

- [ ] **Step 3: Add the columns to the model**

In `src/fold_at_scripps/models/tool.py`, extend the imports and add four columns. Update the sqlalchemy import line to include `Text` and `false`:

```python
from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint, false, true
```

Add these columns to the `Tool` class (after `enabled`):

```python
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_timeout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_batch: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
```

- [ ] **Step 4: Run the model tests to verify they pass**

Run: `uv run pytest tests/models/test_tool.py -v`
Expected: PASS (all Tool tests, including the two new ones).

- [ ] **Step 5: Generate the migration**

Bring the database to head, then autogenerate the incremental migration:

Run: `uv run alembic upgrade head`
Then: `uv run alembic revision --autogenerate -m "add tool metadata"`
Expected: a new file under `migrations/versions/` whose `upgrade()` calls `op.add_column("tools", ...)` four times (`description`, `image_tag`, `default_timeout`, `supports_batch`) and whose `downgrade()` drops them. Open it and confirm exactly these four columns are added and nothing else. Run `uv run ruff format .` on the generated file.

- [ ] **Step 6: Verify migration round-trip and no-drift**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: PASS — `command.upgrade(head)` applies both migrations and `command.check` reports no drift between the models and the migrated schema.

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/fold_at_scripps/models/tool.py tests/models/test_tool.py migrations/versions/
git commit -m "feat: add tool metadata columns and migration"
```

---

### Task 2: ToolRecord and the ToolSource boundary

**Files:**
- Create: `src/fold_at_scripps/catalog/__init__.py`
- Create: `src/fold_at_scripps/catalog/sources.py`
- Create: `tests/catalog/__init__.py`
- Create: `tests/catalog/test_sources.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `fold_at_scripps.catalog.sources.ToolRecord` — Pydantic model: `name`, `version`, `category`, `gpu_count`, `default_timeout`, `supports_batch`, `description`, `image_tag`, `input_schema`.
  - `ToolSource` (Protocol) with `fetch_tools(self) -> list[ToolRecord]` (synchronous).
  - `FakeToolSource(records: list[ToolRecord])` implementing `ToolSource`.

- [ ] **Step 1: Write the failing tests**

Create `tests/catalog/__init__.py` (empty file).

Create `tests/catalog/test_sources.py`:

```python
"""Tests for tool sources."""

from __future__ import annotations

from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord


def _record(name: str = "proteinmpnn") -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category="inverse-folding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=True,
        description="Design sequences for a backbone.",
        image_tag=f"{name}:1.0.0",
        input_schema={"type": "object", "properties": {}},
    )


def test_tool_record_validates_from_dict() -> None:
    record = ToolRecord.model_validate(
        {
            "name": "esmfold",
            "version": "1.0.0",
            "category": "structure-prediction",
            "gpu_count": 1,
            "default_timeout": 1200,
            "supports_batch": False,
            "description": "Predict structure.",
            "image_tag": "esmfold:1.0.0",
            "input_schema": {"type": "object"},
        }
    )
    assert record.name == "esmfold"
    assert record.gpu_count == 1


def test_fake_tool_source_returns_records() -> None:
    records = [_record("a"), _record("b")]
    source = FakeToolSource(records)
    assert source.fetch_tools() == records
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/catalog/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.catalog'`.

- [ ] **Step 3: Implement the package and sources**

Create `src/fold_at_scripps/catalog/__init__.py`:

```python
"""Tool catalog: sources, sync, and read services."""
```

Create `src/fold_at_scripps/catalog/sources.py`:

```python
"""Tool-source boundary: how the catalog learns about available tools."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class ToolRecord(BaseModel):
    """A single tool's metadata as reported by a source (e.g. autobio)."""

    name: str
    version: str
    category: str
    gpu_count: int
    default_timeout: int
    supports_batch: bool
    description: str | None = None
    image_tag: str | None = None
    input_schema: dict[str, Any]


class ToolSource(Protocol):
    """Yields the set of tools currently available from a backend."""

    def fetch_tools(self) -> list[ToolRecord]: ...


class FakeToolSource:
    """An in-memory tool source for tests."""

    def __init__(self, records: list[ToolRecord]) -> None:
        self._records = records

    def fetch_tools(self) -> list[ToolRecord]:
        """Return the configured records."""
        return self._records
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/catalog/test_sources.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && docker compose up -d postgres && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/catalog/__init__.py src/fold_at_scripps/catalog/sources.py tests/catalog/__init__.py tests/catalog/test_sources.py
git commit -m "feat: add ToolRecord and ToolSource boundary"
```

---

### Task 3: AutobioToolSource (CLI adapter)

**Files:**
- Create: `src/fold_at_scripps/catalog/autobio_source.py`
- Create: `tests/catalog/test_autobio_source.py`

**Interfaces:**
- Consumes: `ToolRecord` (Task 2).
- Produces:
  - `fold_at_scripps.catalog.autobio_source.parse_tool_names(payload: list[dict]) -> list[str]` (pure).
  - `parse_tool_info(payload: dict) -> ToolRecord` (pure).
  - `AutobioToolSource(autobio_bin: str = "autobio", timeout: int = 120)` implementing `ToolSource` by shelling out to the autobio CLI.

- [ ] **Step 1: Write the failing tests**

Create `tests/catalog/test_autobio_source.py`:

```python
"""Tests for the autobio CLI tool source."""

from __future__ import annotations

import shutil

import pytest

from fold_at_scripps.catalog.autobio_source import (
    AutobioToolSource,
    parse_tool_info,
    parse_tool_names,
)

_LIST_PAYLOAD = [
    {
        "name": "ablang2",
        "category": "embedding",
        "gpu": True,
        "version": "1.0.0",
        "description": "Extract antibody embeddings using AbLang2.",
    },
    {
        "name": "proteinmpnn",
        "category": "inverse-folding",
        "gpu": True,
        "version": "1.0.0",
        "description": "Design sequences for a backbone using ProteinMPNN.",
    },
]

_INFO_PAYLOAD = {
    "name": "proteinmpnn",
    "category": "inverse-folding",
    "image_tag": "proteinmpnn:1.0.0",
    "requires_gpu": True,
    "gpu_count": 1,
    "default_timeout": 600,
    "supports_batch": True,
    "version": "1.0.0",
    "description": "Design sequences for a backbone using ProteinMPNN.",
    "input_schema": {
        "type": "object",
        "properties": {
            "structure_path": {"type": "string"},
            "num_sequences": {"type": "integer", "default": 8},
        },
        "required": ["structure_path"],
    },
}


def test_parse_tool_names() -> None:
    assert parse_tool_names(_LIST_PAYLOAD) == ["ablang2", "proteinmpnn"]


def test_parse_tool_info() -> None:
    record = parse_tool_info(_INFO_PAYLOAD)
    assert record.name == "proteinmpnn"
    assert record.version == "1.0.0"
    assert record.category == "inverse-folding"
    assert record.gpu_count == 1
    assert record.default_timeout == 600
    assert record.supports_batch is True
    assert record.image_tag == "proteinmpnn:1.0.0"
    assert record.input_schema["required"] == ["structure_path"]


@pytest.mark.skipif(shutil.which("autobio") is None, reason="autobio CLI not on PATH")
def test_autobio_source_fetches_real_tools() -> None:
    source = AutobioToolSource()
    records = source.fetch_tools()
    assert len(records) > 0
    assert all(r.name and r.version and r.input_schema is not None for r in records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/catalog/test_autobio_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.catalog.autobio_source'`.

- [ ] **Step 3: Implement the adapter**

Create `src/fold_at_scripps/catalog/autobio_source.py`:

```python
"""A ToolSource backed by the autobio CLI (`autobio list` / `autobio info`)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from fold_at_scripps.catalog.sources import ToolRecord


def parse_tool_names(payload: list[dict[str, Any]]) -> list[str]:
    """Extract tool names from `autobio list --format json` output."""
    return [item["name"] for item in payload]


def parse_tool_info(payload: dict[str, Any]) -> ToolRecord:
    """Build a ToolRecord from `autobio info <name> --format json` output."""
    return ToolRecord(
        name=payload["name"],
        version=payload["version"],
        category=payload["category"],
        gpu_count=payload.get("gpu_count", 0),
        default_timeout=payload["default_timeout"],
        supports_batch=payload["supports_batch"],
        description=payload.get("description"),
        image_tag=payload.get("image_tag"),
        input_schema=payload["input_schema"],
    )


class AutobioToolSource:
    """Fetches the catalog by invoking the autobio CLI with JSON output."""

    def __init__(self, autobio_bin: str = "autobio", timeout: int = 120) -> None:
        self._bin = autobio_bin
        self._timeout = timeout

    def _run_json(self, *args: str) -> Any:
        """Run an autobio subcommand with `--format json` and parse stdout."""
        result = subprocess.run(
            [self._bin, *args, "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=self._timeout,
        )
        return json.loads(result.stdout)

    def fetch_tools(self) -> list[ToolRecord]:
        """List tools, then fetch each tool's full info, into ToolRecords."""
        names = parse_tool_names(self._run_json("list"))
        return [parse_tool_info(self._run_json("info", name)) for name in names]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/catalog/test_autobio_source.py -v`
Expected: PASS — the two parse tests pass; the real-CLI test passes if autobio is on PATH, otherwise SKIPPED.

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass (real-CLI test runs or skips depending on environment).

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/catalog/autobio_source.py tests/catalog/test_autobio_source.py
git commit -m "feat: add autobio CLI tool source"
```

---

### Task 4: Catalog sync service

**Files:**
- Create: `src/fold_at_scripps/catalog/service.py`
- Create: `tests/catalog/test_service_sync.py`

**Interfaces:**
- Consumes: `ToolSource`, `ToolRecord` (Task 2); `Tool` (model); `db_session`.
- Produces:
  - `fold_at_scripps.catalog.service.SyncResult` (dataclass: `added: int`, `updated: int`).
  - `async sync_catalog(session, source) -> SyncResult` — upserts tools by `(name, version)`; updates metadata on existing rows (never `enabled`); creates new rows `enabled=True`.

- [ ] **Step 1: Write the failing tests**

Create `tests/catalog/test_service_sync.py`:

```python
"""Tests for catalog synchronization."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.models import Tool

pytestmark = pytest.mark.integration


def _record(name: str, *, version: str = "1.0.0", schema: dict[str, Any] | None = None) -> ToolRecord:
    return ToolRecord(
        name=name,
        version=version,
        category="inverse-folding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=True,
        description=f"{name} description",
        image_tag=f"{name}:{version}",
        input_schema=schema if schema is not None else {"type": "object"},
    )


async def test_sync_adds_new_tools(db_session: AsyncSession) -> None:
    source = FakeToolSource([_record("a"), _record("b")])
    result = await sync_catalog(db_session, source)
    assert result.added == 2
    assert result.updated == 0
    tools = (await db_session.execute(select(Tool))).scalars().all()
    assert {t.name for t in tools} == {"a", "b"}
    assert all(t.enabled is True for t in tools)


async def test_resync_updates_without_duplicates(db_session: AsyncSession) -> None:
    await sync_catalog(db_session, FakeToolSource([_record("a", schema={"v": 1})]))
    result = await sync_catalog(db_session, FakeToolSource([_record("a", schema={"v": 2})]))
    assert result.added == 0
    assert result.updated == 1
    tools = (await db_session.execute(select(Tool))).scalars().all()
    assert len(tools) == 1
    assert tools[0].input_schema == {"v": 2}


async def test_sync_preserves_enabled_flag(db_session: AsyncSession) -> None:
    await sync_catalog(db_session, FakeToolSource([_record("a")]))
    tool = (await db_session.execute(select(Tool))).scalar_one()
    tool.enabled = False
    await db_session.commit()
    await sync_catalog(db_session, FakeToolSource([_record("a", schema={"v": 9})]))
    refreshed = (await db_session.execute(select(Tool))).scalar_one()
    assert refreshed.enabled is False
    assert refreshed.input_schema == {"v": 9}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/catalog/test_service_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.catalog.service'`.

- [ ] **Step 3: Implement the sync service**

Create `src/fold_at_scripps/catalog/service.py`:

```python
"""Catalog synchronization: upsert tools from a ToolSource."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.sources import ToolRecord, ToolSource
from fold_at_scripps.models import Tool


@dataclass
class SyncResult:
    """Summary of a catalog sync run."""

    added: int
    updated: int


def _apply(tool: Tool, record: ToolRecord) -> None:
    """Copy a record's metadata onto a Tool (never touches `enabled`)."""
    tool.category = record.category
    tool.gpu_count = record.gpu_count
    tool.input_schema = record.input_schema
    tool.description = record.description
    tool.image_tag = record.image_tag
    tool.default_timeout = record.default_timeout
    tool.supports_batch = record.supports_batch


async def sync_catalog(session: AsyncSession, source: ToolSource) -> SyncResult:
    """Upsert every tool from ``source`` into the catalog.

    Existing tools (matched by name + version) have their metadata refreshed but
    keep their admin-controlled ``enabled`` flag; new tools are created enabled.
    """
    records = await asyncio.to_thread(source.fetch_tools)
    added = 0
    updated = 0
    for record in records:
        stmt = select(Tool).where(Tool.name == record.name, Tool.version == record.version)
        existing = await session.scalar(stmt)
        if existing is None:
            tool = Tool(name=record.name, version=record.version, enabled=True)
            _apply(tool, record)
            session.add(tool)
            added += 1
        else:
            _apply(existing, record)
            updated += 1
    await session.commit()
    return SyncResult(added=added, updated=updated)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/catalog/test_service_sync.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/catalog/service.py tests/catalog/test_service_sync.py
git commit -m "feat: add catalog sync service"
```

---

### Task 5: Catalog read API

**Files:**
- Create: `src/fold_at_scripps/schemas/tools.py`
- Modify: `src/fold_at_scripps/catalog/service.py` (add read functions)
- Create: `src/fold_at_scripps/api/tools.py`
- Modify: `src/fold_at_scripps/main.py` (include the tools router)
- Create: `tests/api/test_tools.py`

**Interfaces:**
- Consumes: `Tool`; `get_current_user` (Plan 3); `get_session`; `sync_catalog` + `FakeToolSource` (for seeding tests).
- Produces:
  - `fold_at_scripps.schemas.tools.ToolSummary` (id, name, version, category, gpu_count, description, supports_batch) and `ToolRead` (adds image_tag, default_timeout, input_schema).
  - `service.list_enabled_tools(session, *, category=None) -> list[Tool]` and `service.get_enabled_tool(session, tool_id) -> Tool | None`.
  - `api.tools.router`: `GET /tools` (optional `?category=`), `GET /tools/{tool_id}` — both require an active user, both expose only enabled tools.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_tools.py`:

```python
"""Tests for the catalog read API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, Tool, User, UserStatus

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _record(name: str, category: str = "inverse-folding") -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category=category,
        gpu_count=1,
        default_timeout=600,
        supports_batch=True,
        description=f"{name} description",
        image_tag=f"{name}:1.0.0",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
    )


async def _seed_tools(session: AsyncSession) -> None:
    await sync_catalog(
        session,
        FakeToolSource([_record("alpha"), _record("beta", category="embedding")]),
    )


async def _login(client: AsyncClient, session: AsyncSession) -> None:
    session.add(AllowedEmail(email="u@scripps.edu"))
    await session.commit()
    await client.post(
        "/auth/register",
        json={"email": "u@scripps.edu", "password": "s3cret-pw", "display_name": "U"},
    )
    user = await session.scalar(select(User).where(User.email == "u@scripps.edu"))
    assert user is not None
    user.status = UserStatus.ACTIVE
    await session.commit()
    await client.post("/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"})


async def test_tools_requires_auth(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    async with _client() as client:
        assert (await client.get("/tools")).status_code == 401


async def test_list_tools_returns_enabled(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get("/tools")
        assert resp.status_code == 200
        names = {t["name"] for t in resp.json()}
        assert names == {"alpha", "beta"}


async def test_list_tools_filters_category(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get("/tools", params={"category": "embedding"})
        assert [t["name"] for t in resp.json()] == ["beta"]


async def test_disabled_tool_excluded(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    tool = await db_session.scalar(select(Tool).where(Tool.name == "alpha"))
    assert tool is not None
    tool.enabled = False
    await db_session.commit()
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get("/tools")
        assert [t["name"] for t in resp.json()] == ["beta"]
        detail = await client.get(f"/tools/{tool.id}")
        assert detail.status_code == 404


async def test_tool_detail_includes_schema(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    tool = await db_session.scalar(select(Tool).where(Tool.name == "alpha"))
    assert tool is not None
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get(f"/tools/{tool.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "alpha"
        assert body["input_schema"]["type"] == "object"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/api/test_tools.py -v`
Expected: FAIL — `/tools` returns 404 (no router yet), so assertions fail.

- [ ] **Step 3: Create the schemas**

Create `src/fold_at_scripps/schemas/tools.py`:

```python
"""Catalog (tool) response schemas."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolSummary(BaseModel):
    """Compact tool representation for catalog listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    category: str
    gpu_count: int
    description: str | None
    supports_batch: bool


class ToolRead(ToolSummary):
    """Full tool representation, including the input schema."""

    image_tag: str | None
    default_timeout: int | None
    input_schema: dict[str, Any]
```

- [ ] **Step 4: Add the read functions to the service**

Append to `src/fold_at_scripps/catalog/service.py`:

```python
import uuid


async def list_enabled_tools(
    session: AsyncSession, *, category: str | None = None
) -> list[Tool]:
    """Return enabled tools, optionally filtered by category, ordered by name."""
    stmt = select(Tool).where(Tool.enabled.is_(True))
    if category is not None:
        stmt = stmt.where(Tool.category == category)
    stmt = stmt.order_by(Tool.name)
    return list((await session.execute(stmt)).scalars().all())


async def get_enabled_tool(session: AsyncSession, tool_id: uuid.UUID) -> Tool | None:
    """Return a single enabled tool by id, or None."""
    tool = await session.get(Tool, tool_id)
    if tool is None or not tool.enabled:
        return None
    return tool
```

(Place the `import uuid` with the existing imports at the top of the file; `uv run ruff check --fix .` will sort it.)

- [ ] **Step 5: Create the router**

Create `src/fold_at_scripps/api/tools.py`:

```python
"""Catalog read endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.catalog.service import get_enabled_tool, list_enabled_tools
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User
from fold_at_scripps.schemas.tools import ToolRead, ToolSummary

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolSummary])
async def list_tools(
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list:
    """List enabled tools, optionally filtered by category."""
    return await list_enabled_tools(session, category=category)


@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    tool_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Return a single enabled tool, including its input schema."""
    tool = await get_enabled_tool(session, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool
```

- [ ] **Step 6: Register the router**

In `src/fold_at_scripps/main.py`, import and include the tools router (after the auth router):

```python
from fold_at_scripps.api.tools import router as tools_router
```

and inside `create_app()`:

```python
    app.include_router(tools_router)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `docker compose up -d postgres && uv run pytest tests/api/test_tools.py -v`
Expected: PASS (5 passed).

- [ ] **Step 8: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/fold_at_scripps/schemas/tools.py src/fold_at_scripps/catalog/service.py src/fold_at_scripps/api/tools.py src/fold_at_scripps/main.py tests/api/test_tools.py
git commit -m "feat: add catalog read API"
```

---

### Task 6: `sync-catalog` CLI command

**Files:**
- Modify: `src/fold_at_scripps/cli.py` (add `sync-catalog` command)
- Modify: `tests/test_cli.py` (add a real-CLI test, skipped without autobio)

**Interfaces:**
- Consumes: `AutobioToolSource` (Task 3); `sync_catalog` (Task 4); `get_sessionmaker`, `dispose_engine` (db).
- Produces: a `sync-catalog` Typer command that runs the autobio-backed sync and prints the added/updated counts.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
import shutil

from sqlalchemy import func, select

from fold_at_scripps.models import Tool


@pytest.mark.skipif(shutil.which("autobio") is None, reason="autobio CLI not on PATH")
async def test_sync_catalog_populates_tools(db_session: AsyncSession) -> None:
    result = await asyncio.to_thread(runner.invoke, app, ["sync-catalog"])
    assert result.exit_code == 0, result.output
    count = await db_session.scalar(select(func.count()).select_from(Tool))
    assert count > 0
```

(Add the imports at the top of the file alongside the existing ones; `ruff check --fix` will sort them.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL if autobio is on PATH (no `sync-catalog` command yet → non-zero exit / usage error); SKIPPED if autobio is absent. If it skips in your environment, also confirm failure by checking `uv run python -c "from fold_at_scripps.cli import app"` then `uv run fold-admin sync-catalog --help` returns a "no such command" error before implementing.

- [ ] **Step 3: Implement the command**

In `src/fold_at_scripps/cli.py`, add imports and a new command. Add to the imports:

```python
from fold_at_scripps.catalog.autobio_source import AutobioToolSource
from fold_at_scripps.catalog.service import sync_catalog
```

Add the async worker and command:

```python
async def _sync_catalog() -> None:
    source = AutobioToolSource()
    try:
        async with get_sessionmaker()() as session:
            result = await sync_catalog(session, source)
        typer.echo(f"Catalog synced: {result.added} added, {result.updated} updated.")
    finally:
        await dispose_engine()


@app.command("sync-catalog")
def sync_catalog_command() -> None:
    """Sync the tool catalog from autobio."""
    asyncio.run(_sync_catalog())
```

(Ensure `dispose_engine` is imported from `fold_at_scripps.db` — it was added in the Plan 3 CLI refactor; if the import line only has `get_sessionmaker`, add `dispose_engine`.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker compose up -d postgres && uv run pytest tests/test_cli.py -v`
Expected: PASS — the existing create-admin tests pass; `test_sync_catalog_populates_tools` passes if autobio is on PATH, otherwise SKIPPED.

- [ ] **Step 5: Lint, format, full suite**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!`; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/cli.py tests/test_cli.py
git commit -m "feat: add sync-catalog CLI command"
```

---

## Self-Review

**1. Spec coverage (against the architecture's catalog description + this plan's goal):**
- Tool catalog snapshots the full autobio contract (description, image_tag, default_timeout, supports_batch) → Task 1. ✓
- `ToolSource` boundary + `FakeToolSource` → Task 2; `AutobioToolSource` CLI adapter → Task 3. ✓
- Schema-driven: `input_schema` (autobio's JSON Schema) is stored verbatim and exposed via the API → Tasks 1, 3, 5. ✓
- `sync_catalog` upsert preserving admin `enabled` → Task 4. ✓
- Read API (`/tools`, `/tools/{id}`, auth-required, enabled-only) → Task 5. ✓
- CLI to populate the catalog → Task 6. ✓
- Deferred (documented): admin sync-trigger + enable/disable endpoints (Plan 8); execution use of image_tag/default_timeout (Plan 6); auto-disable of vanished tools (future).

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases". Every code/command step has concrete content. The autobio sample payloads in tests are realistic captures of the verified CLI output, not placeholders.

**3. Type/name consistency:** `ToolRecord`/`ToolSource`/`FakeToolSource` (Task 2) are used by `parse_tool_info`/`AutobioToolSource` (Task 3), `sync_catalog` (Task 4), and the API/CLI tests (Tasks 5, 6). `sync_catalog`/`SyncResult` (Task 4) match their use in Tasks 5 (test seeding) and 6 (CLI). `list_enabled_tools`/`get_enabled_tool` (Task 5 service) match the router. `ToolSummary`/`ToolRead` (Task 5) match the endpoints' `response_model`. The new `Tool` columns (Task 1) are populated by `_apply` (Task 4) and exposed by `ToolRead` (Task 5). `get_current_user` (Plan 3) gates both endpoints. `AutobioToolSource`/`sync_catalog` (Tasks 3, 4) are wired by the CLI (Task 6).
