# Foundation & Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `fold_at_scripps` project skeleton — a booting FastAPI app with typed settings, an async Postgres connection, liveness/readiness health checks, a dev Docker Compose stack, and a CI pipeline — so every later plan builds on a tested foundation.

**Architecture:** A `src/`-layout Python package exposing a FastAPI app built by a factory function. Configuration is a Pydantic `BaseSettings` object. Database access is an async SQLAlchemy 2.0 engine/session, lazily created and injected via a FastAPI dependency. Health endpoints prove the app boots (`/health`) and can reach Postgres (`/health/ready`). Docker Compose runs the API + Postgres for local dev; GitHub Actions runs lint + tests against a Postgres service.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 (asyncio) + asyncpg, Postgres 16, pytest + pytest-asyncio + httpx, ruff, uv, Docker Compose, GitHub Actions.

## Global Constraints

- Python `>=3.11`; `target-version = "py311"`.
- `src/` layout; package name **`fold_at_scripps`**; distribution name `fold-at-scripps`.
- Dependency manager **`uv`**; commit `uv.lock`.
- Formatter/linter **`ruff`** (format + check); max line length **100**.
- Tests with **`pytest`** (TDD: failing test first). Async tests via `pytest-asyncio` with `asyncio_mode = "auto"`.
- Type hints on all signatures; `from __future__ import annotations` in every module; Google-style docstrings on public functions/classes.
- Absolute imports only; first-party package is `fold_at_scripps`.
- Settings come from the environment with prefix **`FOLD_`**; no secrets in code or committed config.
- Frequent commits — one per task minimum, using the commit step.

---

### Task 1: Project scaffold, tooling, and settings

**Files:**
- Create: `pyproject.toml`
- Create: `src/fold_at_scripps/__init__.py`
- Create: `src/fold_at_scripps/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`
- Modify: `.gitignore` (append Python entries)

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `fold_at_scripps.config.Settings` — Pydantic settings with fields `app_name: str`, `debug: bool`, `database_url: str`; env prefix `FOLD_`.
  - `fold_at_scripps.config.get_settings() -> Settings` — `lru_cache`d accessor exposing `.cache_clear()`.

- [ ] **Step 1: Create the package layout and `pyproject.toml`**

Create `src/fold_at_scripps/__init__.py`:

```python
"""fold@Scripps — web front-end for running biological models via autobio."""

__version__ = "0.1.0"
```

Create `tests/__init__.py` (empty file).

Create `pyproject.toml`:

```toml
[project]
name = "fold-at-scripps"
version = "0.1.0"
description = "Web front-end for running biological models via autobio."
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29",
]

[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.5",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fold_at_scripps"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.lint.isort]
known-first-party = ["fold_at_scripps"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: tests that require a running Postgres database",
]
```

- [ ] **Step 2: Append Python entries to `.gitignore`**

Append to the existing `.gitignore`:

```gitignore

# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/
.pytest_cache/
.ruff_cache/
.env
```

- [ ] **Step 3: Sync the environment**

Run: `uv sync`
Expected: creates `.venv/` and `uv.lock`, installs runtime + dev dependencies, and installs `fold_at_scripps` in editable mode. No errors.

- [ ] **Step 4: Write the failing settings test**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fold_at_scripps.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Ensure each test sees freshly-loaded settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

Create `tests/test_config.py`:

```python
"""Tests for application settings."""

from __future__ import annotations

import pytest

from fold_at_scripps.config import get_settings


def test_settings_defaults() -> None:
    settings = get_settings()
    assert settings.app_name == "fold@Scripps"
    assert settings.debug is False


def test_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLD_DEBUG", "true")
    monkeypatch.setenv("FOLD_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/test")
    settings = get_settings()
    assert settings.debug is True
    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/test"
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.config'`.

- [ ] **Step 6: Implement `config.py`**

Create `src/fold_at_scripps/config.py`:

```python
"""Application configuration loaded from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings (prefix ``FOLD_``)."""

    model_config = SettingsConfigDict(env_prefix="FOLD_", env_file=".env", extra="ignore")

    app_name: str = "fold@Scripps"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps"


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 8: Lint and format**

Run: `uv run ruff format . && uv run ruff check .`
Expected: files reformatted as needed; `ruff check` reports `All checks passed!`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src/fold_at_scripps/__init__.py src/fold_at_scripps/config.py tests/__init__.py tests/conftest.py tests/test_config.py
git commit -m "feat: scaffold project with typed settings"
```

---

### Task 2: FastAPI app factory and liveness health check

**Files:**
- Create: `src/fold_at_scripps/main.py`
- Create: `src/fold_at_scripps/api/__init__.py`
- Create: `src/fold_at_scripps/api/health.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_health.py`

**Interfaces:**
- Consumes: `fold_at_scripps.config.get_settings`.
- Produces:
  - `fold_at_scripps.main.create_app() -> fastapi.FastAPI` — application factory.
  - `fold_at_scripps.main.app` — module-level app instance for ASGI servers.
  - `fold_at_scripps.api.health.router` — `APIRouter` with `GET /health`.

- [ ] **Step 1: Write the failing liveness test**

Create `tests/api/__init__.py` (empty file).

Create `tests/api/test_health.py`:

```python
"""Tests for health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from fold_at_scripps.main import create_app


def test_liveness() -> None:
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/api/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.main'`.

- [ ] **Step 3: Implement the health router**

Create `src/fold_at_scripps/api/__init__.py` (empty file).

Create `src/fold_at_scripps/api/health.py`:

```python
"""Health-check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — confirms the process is serving requests."""
    return {"status": "ok"}
```

- [ ] **Step 4: Implement the app factory**

Create `src/fold_at_scripps/main.py`:

```python
"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from fold_at_scripps.api.health import router as health_router
from fold_at_scripps.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    return app


app = create_app()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/api/test_health.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Lint, format, and run the full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!` and 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/main.py src/fold_at_scripps/api/__init__.py src/fold_at_scripps/api/health.py tests/api/__init__.py tests/api/test_health.py
git commit -m "feat: add app factory and liveness health check"
```

---

### Task 3: Dev Docker Compose stack and Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.dockerignore`
- Modify: `README.md` (append a "Development" section)

**Interfaces:**
- Consumes: `fold_at_scripps.main:app` (run by uvicorn in the container); `FOLD_DATABASE_URL` env var.
- Produces: a `postgres` service reachable on `localhost:5432` and an `api` service on `localhost:8000`. Later tasks' integration tests rely on `postgres` being up.

- [ ] **Step 1: Create the Dockerfile**

Create `Dockerfile` (single-stage dev image; production multi-stage is deferred to the deployment plan):

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "fold_at_scripps.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `.dockerignore`**

Create `.dockerignore`:

```dockerignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.git/
tests/
docs/
.env
```

- [ ] **Step 3: Create the Compose file**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: fold
      POSTGRES_PASSWORD: fold
      POSTGRES_DB: fold_at_scripps
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fold -d fold_at_scripps"]
      interval: 5s
      timeout: 3s
      retries: 10

  api:
    build: .
    environment:
      FOLD_DATABASE_URL: postgresql+asyncpg://fold:fold@postgres:5432/fold_at_scripps
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 4: Create `.env.example`**

Create `.env.example`:

```dotenv
# Copy to .env for local (non-container) development.
FOLD_DEBUG=false
FOLD_DATABASE_URL=postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps
```

- [ ] **Step 5: Document development setup**

Append to `README.md`:

```markdown

## Development

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync                       # install dependencies
docker compose up -d postgres # start Postgres for tests/local runs
uv run pytest                 # run the test suite
uv run uvicorn fold_at_scripps.main:app --reload  # run the API locally
```

Or run the full stack in containers:

```bash
docker compose up --build
curl localhost:8000/health    # {"status":"ok"}
```
```

- [ ] **Step 6: Verify the stack boots**

Run: `docker compose up -d --build`
Then: `curl -s localhost:8000/health`
Expected: `{"status":"ok"}`.
Then: `docker compose down`

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml .env.example README.md
git commit -m "feat: add dev Docker Compose stack"
```

---

### Task 4: Async database engine and readiness health check

**Files:**
- Create: `src/fold_at_scripps/db.py`
- Modify: `src/fold_at_scripps/api/health.py` (add readiness endpoint)
- Modify: `tests/api/test_health.py` (add readiness test)
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes: `fold_at_scripps.config.get_settings`.
- Produces:
  - `fold_at_scripps.db.get_engine() -> sqlalchemy.ext.asyncio.AsyncEngine` — lazily created process-wide engine.
  - `fold_at_scripps.db.get_sessionmaker() -> async_sessionmaker[AsyncSession]`.
  - `fold_at_scripps.db.get_session() -> AsyncIterator[AsyncSession]` — FastAPI dependency yielding a session.
  - `GET /health/ready` returning `{"status": "ready"}` when the DB is reachable.

- [ ] **Step 1: Ensure Postgres is running**

Run: `docker compose up -d postgres`
Expected: the `postgres` container is healthy (`docker compose ps` shows `healthy`).

- [ ] **Step 2: Write the failing DB-connectivity test**

Create `tests/test_db.py`:

```python
"""Tests for the async database engine."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from fold_at_scripps.db import get_sessionmaker


@pytest.mark.integration
async def test_engine_connects() -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fold_at_scripps.db'`.

- [ ] **Step 4: Implement `db.py`**

Create `src/fold_at_scripps/db.py`:

```python
"""Async SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fold_at_scripps.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async database session."""
    async with get_sessionmaker()() as session:
        yield session
```

- [ ] **Step 5: Run the DB test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Write the failing readiness test**

Add to `tests/api/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.integration
async def test_readiness() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
```

- [ ] **Step 7: Run the readiness test to verify it fails**

Run: `uv run pytest tests/api/test_health.py::test_readiness -v`
Expected: FAIL — 404 (route not defined yet), so the `status_code == 200` assertion fails.

- [ ] **Step 8: Add the readiness endpoint**

Replace the contents of `src/fold_at_scripps/api/health.py` with:

```python
"""Health-check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — confirms the process is serving requests."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness probe — confirms the database is reachable."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
```

- [ ] **Step 9: Run the readiness test to verify it passes**

Run: `uv run pytest tests/api/test_health.py -v`
Expected: PASS (2 passed).

- [ ] **Step 10: Lint, format, and run the full suite**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -v`
Expected: `All checks passed!` and all tests pass (5 passed).

- [ ] **Step 11: Commit**

```bash
git add src/fold_at_scripps/db.py src/fold_at_scripps/api/health.py tests/test_db.py tests/api/test_health.py
git commit -m "feat: add async DB engine and readiness check"
```

---

### Task 5: Continuous integration

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `uv` project (`pyproject.toml`, `uv.lock`); the full test suite including `integration`-marked tests.
- Produces: a CI workflow running ruff + pytest against a Postgres service on push and pull request.

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: fold
          POSTGRES_PASSWORD: fold
          POSTGRES_DB: fold_at_scripps
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U fold -d fold_at_scripps"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      FOLD_DATABASE_URL: postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Install dependencies
        run: uv sync --frozen
      - name: Lint
        run: uv run ruff check .
      - name: Format check
        run: uv run ruff format --check .
      - name: Test
        run: uv run pytest -v
```

- [ ] **Step 2: Verify the workflow file is valid YAML**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('ok')"`
Expected: `ok` (no exception).

Note: `pyyaml` is not a project dependency; if the import fails, instead verify by eye that indentation is consistent, then rely on the push in the next step to validate the workflow on GitHub.

- [ ] **Step 3: Run the full local suite one final time**

Run: `docker compose up -d postgres && uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: `All checks passed!` and all tests pass (5 passed).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint and test workflow"
```

---

## Self-Review

**1. Spec coverage (against the Foundation plan's goal):**
- `src/` scaffold + `pyproject` + `uv` → Task 1. ✓
- Typed settings (`BaseSettings`, `FOLD_` prefix) → Task 1. ✓
- FastAPI app factory + liveness → Task 2. ✓
- Dev Docker Compose (api + Postgres) + Dockerfile → Task 3. ✓
- Async DB engine/session + readiness (DB connectivity) → Task 4. ✓
- pytest harness (sync + async, integration marker) → Tasks 1, 2, 4. ✓
- ruff format/lint → every task's lint step. ✓
- CI → Task 5. ✓
- Data model / migrations / auth / catalog / scheduler / SPA → intentionally **out of scope** (later plans).

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases"; every code and command step shows concrete content. The only conditional note (Task 5 Step 2) gives an explicit fallback, not a placeholder. ✓

**3. Type consistency:** `get_settings`, `Settings`, `create_app`, `app`, `router`, `get_engine`, `get_sessionmaker`, `get_session` are named identically where produced and consumed across tasks. Health routes (`/health`, `/health/ready`) and JSON bodies (`{"status": "ok"}` / `{"status": "ready"}`) match between implementation and tests. ✓
