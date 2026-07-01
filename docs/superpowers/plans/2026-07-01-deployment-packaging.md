# Deployment & Packaging (Plan 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package and deploy the finished app on the single GPU node — FastAPI serves the built SPA, the backend runs as two host systemd services against a Dockerized Postgres, the frontend is built in a Docker stage — and close the accumulated operational deferrals (body-size limit, single-scheduler enforcement, code-split, structured logging, secret-key guard).

**Architecture:** The app runs on the host (uvicorn API + `fold-scheduler` via systemd) where autobio/Docker/GPUs live natively; Postgres runs in Docker (compose). FastAPI serves `frontend/dist` same-origin. The Python app is NOT containerized; the `Dockerfile` becomes a frontend-build stage. No multi-node; TLS/reverse-proxy is external (documented).

**Tech Stack:** FastAPI/Starlette (StaticFiles, middleware), SQLAlchemy async (`pg_advisory_lock`), uv, systemd, docker-compose, Vite (code-split), pytest, Vitest.

## Global Constraints

- Backend: Python `>=3.11`; `from __future__ import annotations`; type hints; Google-style docstrings; absolute imports; ruff (E,F,I,UP,B) line 100; `uv` for all commands.
- Frontend: TypeScript strict, no `any`; ESLint + Prettier; `npm` from `frontend/`.
- Backend tests via `uv run pytest` (Postgres for `@pytest.mark.integration`; a live autobio smoke test already exists). Frontend via `npm test`. `npm run build` must stay green.
- CI unchanged (backend job + frontend lint/test/build; Playwright E2E local-only).
- Settings are env-prefixed `FOLD_`; true secrets in env, admin-tunables stay DB-backed.

## Precision convention

- Backend logic/config/middleware: complete code + complete pytest tests.
- Ops artifacts (Dockerfile, compose, systemd units, `.env` example, Makefile, docs): complete file contents; verify with real commands (`docker compose config`, build), not pytest.
- Frontend code-split: exact `App.tsx`/`vite.config.ts` changes + a Vitest smoke test that a lazy route resolves.

## File Structure

```
src/fold_at_scripps/
  config.py            # (modify) + log_level, max_upload_bytes, frontend_dist
  logging_config.py    # (create) configure_logging(level)
  middleware.py        # (create) BodySizeLimitMiddleware
  main.py              # (modify) configure_logging + secret guard + body-limit mw + SPA serving
  scheduler/
    locking.py         # (create) acquire_scheduler_lock(engine)
    main.py            # (modify) configure_logging + acquire lock before run_forever
tests/
  test_startup_guard.py   # secret-key guard + configure_logging
  test_body_limit.py      # 413 middleware
  test_spa.py             # SPA fallback + API precedence + boots without dist
  scheduler/test_locking.py  # advisory lock (integration)
  conftest.py          # (modify) set a test FOLD_SECRET_KEY so create_app() passes the guard at import
frontend/
  src/App.tsx          # (modify) React.lazy pages + <Suspense>
  vite.config.ts       # (modify) manualChunks vendor split
  src/App.test.tsx     # (modify) await lazy route
Dockerfile             # (rewrite) frontend-build stage -> dist artifact
docker-compose.yml     # (rewrite) Postgres only
Makefile               # (create) build-frontend, postgres, migrate targets
deploy/
  fold-api.service         # (create)
  fold-scheduler.service   # (create)
  fold.env.example         # (create)
docs/DEPLOYMENT.md     # (create)
```

---

### Task 1: Config additions, structured logging, secret-key startup guard

**Files:**
- Modify: `src/fold_at_scripps/config.py`, `src/fold_at_scripps/main.py`, `tests/conftest.py`
- Create: `src/fold_at_scripps/logging_config.py`, `tests/test_startup_guard.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces: `Settings.log_level: str`, `Settings.max_upload_bytes: int`, `Settings.frontend_dist: str`; `logging_config.configure_logging(level: str) -> None`; a secret-key guard enforced inside `create_app()` (raises `RuntimeError`).

**Critical:** `main.py` has a module-level `app = create_app()` that runs at import. The guard must not break the test suite at collection — so `tests/conftest.py` sets a non-dev `FOLD_SECRET_KEY` at module import (before test modules import `main`). Without this, every test that imports the app fails to collect.

- [ ] **Step 1: Extend conftest so the suite imports under the guard**

At the TOP of `tests/conftest.py` (before other imports that pull in the app), add:

```python
import os

# The Plan 10 secret-key guard refuses the dev-default secret when not in debug.
# Provide a non-dev test secret at collection time so `create_app()` (run at
# import of fold_at_scripps.main) does not raise during the test suite.
os.environ.setdefault("FOLD_SECRET_KEY", "test-secret-not-for-production")
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_startup_guard.py
"""Tests for the secret-key startup guard and logging configuration."""

from __future__ import annotations

import logging

import pytest

from fold_at_scripps.config import get_settings
from fold_at_scripps.logging_config import configure_logging
from fold_at_scripps.main import create_app


def test_create_app_rejects_dev_secret_when_not_debug(monkeypatch):
    monkeypatch.setenv("FOLD_SECRET_KEY", "dev-insecure-secret-change-me")
    monkeypatch.setenv("FOLD_DEBUG", "false")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="FOLD_SECRET_KEY"):
        create_app()


def test_create_app_allows_dev_secret_in_debug(monkeypatch):
    monkeypatch.setenv("FOLD_SECRET_KEY", "dev-insecure-secret-change-me")
    monkeypatch.setenv("FOLD_DEBUG", "true")
    get_settings.cache_clear()
    assert create_app() is not None


def test_create_app_allows_real_secret(monkeypatch):
    monkeypatch.setenv("FOLD_SECRET_KEY", "a-real-long-secret")
    monkeypatch.setenv("FOLD_DEBUG", "false")
    get_settings.cache_clear()
    assert create_app() is not None


def test_configure_logging_sets_level():
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging("INFO")
    assert logging.getLogger().level == logging.INFO
```

Run: `uv run pytest tests/test_startup_guard.py -q`
Expected: FAIL (`ModuleNotFoundError: logging_config` / guard not implemented).

- [ ] **Step 3: Add the settings**

In `src/fold_at_scripps/config.py`, add to `Settings` (after `scheduler_poll_interval`):

```python
    log_level: str = "INFO"
    max_upload_bytes: int = 100 * 1024 * 1024  # 100 MB request-body cap
    frontend_dist: str = "frontend/dist"
```

- [ ] **Step 4: Create the logging config**

```python
# src/fold_at_scripps/logging_config.py
"""Process-wide structured logging configuration."""

from __future__ import annotations

import logging.config

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(level: str = "INFO") -> None:
    """Apply a consistent console logging configuration for the app/scheduler."""
    normalized = level.upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": _FORMAT, "datefmt": _DATEFMT}},
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"}
            },
            "root": {"handlers": ["console"], "level": normalized},
            "loggers": {
                "uvicorn": {"level": normalized},
                "uvicorn.error": {"level": normalized},
                "uvicorn.access": {"level": normalized},
            },
        }
    )
```

- [ ] **Step 5: Wire logging + guard into `create_app`**

In `src/fold_at_scripps/main.py`, add near the top:

```python
from fold_at_scripps.logging_config import configure_logging

_DEV_SECRET_KEY = "dev-insecure-secret-change-me"


def _require_production_secret(settings) -> None:
    """Refuse to boot with the insecure dev secret outside debug mode."""
    if not settings.debug and settings.secret_key == _DEV_SECRET_KEY:
        raise RuntimeError(
            "FOLD_SECRET_KEY is the insecure development default. Set a real "
            "FOLD_SECRET_KEY in production (or FOLD_DEBUG=true for local dev)."
        )
```

At the start of `create_app()` (before building the app):

```python
def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    _require_production_secret(settings)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    ...
```

- [ ] **Step 6: Run tests + full suite**

Run: `uv run pytest tests/test_startup_guard.py -q` → PASS.
Run: `uv run pytest -q` → all green (confirms the conftest secret keeps the existing suite importing/passing).
Run: `uv run ruff check . && uv run ruff format --check .` → clean.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/config.py src/fold_at_scripps/logging_config.py \
    src/fold_at_scripps/main.py tests/conftest.py tests/test_startup_guard.py
git commit -m "feat: structured logging + secret-key startup guard + deploy settings"
```

---

### Task 2: Request body-size-limit middleware

**Files:**
- Create: `src/fold_at_scripps/middleware.py`, `tests/test_body_limit.py`
- Modify: `src/fold_at_scripps/main.py`

**Interfaces:**
- Consumes: `Settings.max_upload_bytes`.
- Produces: `BodySizeLimitMiddleware(app, max_bytes: int)` — returns 413 JSON when `Content-Length` exceeds `max_bytes`, before the body is read; added in `create_app`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_body_limit.py
"""Tests for the request body-size-limit middleware."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app


def _client(monkeypatch, max_bytes: int) -> AsyncClient:
    monkeypatch.setenv("FOLD_SECRET_KEY", "a-real-long-secret")
    monkeypatch.setenv("FOLD_MAX_UPLOAD_BYTES", str(max_bytes))
    get_settings.cache_clear()
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_rejects_over_limit_body(monkeypatch):
    async with _client(monkeypatch, max_bytes=10) as client:
        # POST to an unknown route with a body over the cap -> 413 before routing/DB.
        resp = await client.post("/nope", content=b"x" * 100)
        assert resp.status_code == 413
        assert resp.json()["detail"]


async def test_allows_under_limit_body(monkeypatch):
    async with _client(monkeypatch, max_bytes=1_000_000) as client:
        # Small body to an unknown route -> passes the middleware -> 404 (not 413).
        resp = await client.post("/nope", content=b"small")
        assert resp.status_code == 404
```

Run: `uv run pytest tests/test_body_limit.py -q`
Expected: FAIL (over-limit request returns 404, not 413 — middleware absent).

- [ ] **Step 2: Implement the middleware**

```python
# src/fold_at_scripps/middleware.py
"""HTTP middleware: reject over-large request bodies early."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds a byte cap (413)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > self._max_bytes:
                return JSONResponse(
                    {"detail": "Request body too large"}, status_code=413
                )
        return await call_next(request)
```

- [ ] **Step 3: Register it in `create_app`**

In `src/fold_at_scripps/main.py`, add the import and register it (before or after `SessionMiddleware` — order is fine since it doesn't touch the session):

```python
from fold_at_scripps.middleware import BodySizeLimitMiddleware
...
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
```

- [ ] **Step 4: Run tests** → `uv run pytest tests/test_body_limit.py -q` PASS; `uv run ruff check .` clean.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/middleware.py src/fold_at_scripps/main.py tests/test_body_limit.py
git commit -m "feat: request body-size-limit middleware (413)"
```

---

### Task 3: FastAPI serves the built SPA

**Files:**
- Modify: `src/fold_at_scripps/main.py`
- Create: `tests/test_spa.py`

**Interfaces:**
- Consumes: `Settings.frontend_dist`.
- Produces: when `frontend_dist` is a directory, `create_app` serves real files under it and falls back to `index.html` for unknown GET paths — registered AFTER all API routers, so it never shadows `/auth`,`/tools`,`/runs`,`/admin`,`/health`,`/openapi.json`. When absent, the app is API-only and still boots.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spa.py
"""Tests for SPA static serving + API-route precedence."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>fold@Scripps</title>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    return dist


def _client(dist: str, monkeypatch) -> AsyncClient:
    monkeypatch.setenv("FOLD_SECRET_KEY", "a-real-long-secret")
    monkeypatch.setenv("FOLD_FRONTEND_DIST", dist)
    get_settings.cache_clear()
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_serves_index_for_unknown_client_route(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    async with _client(str(dist), monkeypatch) as client:
        resp = await client.get("/runs/some-client-route")
        assert resp.status_code == 200
        assert "fold@Scripps" in resp.text


async def test_serves_real_asset(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    async with _client(str(dist), monkeypatch) as client:
        resp = await client.get("/assets/app.js")
        assert resp.status_code == 200
        assert "console.log" in resp.text


async def test_api_route_not_shadowed(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    async with _client(str(dist), monkeypatch) as client:
        # openapi.json is a framework route with no DB dependency; must stay JSON.
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")


async def test_boots_without_dist(tmp_path, monkeypatch):
    async with _client(str(tmp_path / "missing"), monkeypatch) as client:
        assert (await client.get("/openapi.json")).status_code == 200
        # No SPA fallback registered -> unknown GET is a 404, not index.html.
        assert (await client.get("/nope")).status_code == 404
```

Note: `test_serves_index_for_unknown_client_route` uses `/runs/some-client-route` — a GET under the `/runs` prefix that is NOT a defined route (the real routes are `/runs`, `/runs/{id}`, `/runs/{id}/artifacts/{path}`, so `/runs/some-client-route` matches `/runs/{id}` GET… choose a path that does NOT collide). Use `/dashboard/x` instead to avoid matching `/runs/{run_id}` (which would hit the DB). Update the test to `client.get("/dashboard/x")`.

Run: `uv run pytest tests/test_spa.py -q`
Expected: FAIL (unknown route 404s; no SPA fallback).

- [ ] **Step 2: Implement SPA serving in `create_app`**

In `src/fold_at_scripps/main.py`, add imports:

```python
from pathlib import Path

from fastapi.responses import FileResponse
```

At the END of `create_app()` (AFTER all `include_router(...)` calls, before `return app`):

```python
    _mount_spa(app, Path(settings.frontend_dist))
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: real files, else index.html (client-side routing)."""
    if not dist.is_dir():
        return
    index_file = dist / "index.html"
    dist_root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index_file)
```

(The catch-all is defined after the routers are included, so specific API routes win; `dist_root in candidate.parents` is the path-traversal guard.)

- [ ] **Step 3: Run tests** → fix the `/dashboard/x` path note, `uv run pytest tests/test_spa.py -q` PASS; `uv run ruff check .` clean.

- [ ] **Step 4: Commit**

```bash
git add src/fold_at_scripps/main.py tests/test_spa.py
git commit -m "feat: serve the built SPA from FastAPI with client-route fallback"
```

---

### Task 4: Single-scheduler enforcement via pg_advisory_lock

**Files:**
- Create: `src/fold_at_scripps/scheduler/locking.py`, `tests/scheduler/test_locking.py`
- Modify: `src/fold_at_scripps/scheduler/main.py`

**Interfaces:**
- Consumes: `db.get_engine()`, `Settings.log_level`.
- Produces: `acquire_scheduler_lock(engine: AsyncEngine) -> AsyncConnection | None` — returns a held connection (keep open to hold the lock) or `None` if another holder exists. `run_scheduler` acquires it first and exits (SystemExit 1) if `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/scheduler/test_locking.py
"""The scheduler advisory lock admits exactly one holder."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from fold_at_scripps.config import get_settings
from fold_at_scripps.scheduler.locking import acquire_scheduler_lock

pytestmark = pytest.mark.integration


async def test_only_one_holder():
    # NullPool: a session-level advisory lock is released only when the Postgres
    # session ends. With a pooling engine, `conn.close()` returns the connection
    # to the pool WITHOUT ending its session, so the lock would linger and make
    # the "re-acquire after release" assertion pool-order-dependent. NullPool
    # makes `close()` physically end the session, releasing the lock
    # deterministically. (Production holds one connection for the process
    # lifetime and never closes it, so the default engine is correct there.)
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        first = await acquire_scheduler_lock(engine)
        assert first is not None
        second = await acquire_scheduler_lock(engine)
        assert second is None  # already held
        await first.close()  # release
        third = await acquire_scheduler_lock(engine)
        assert third is not None  # re-acquirable after release
        await third.close()
    finally:
        await engine.dispose()
```

Run: `docker compose up -d postgres && uv run pytest tests/scheduler/test_locking.py -q`
Expected: FAIL (`acquire_scheduler_lock` missing).

- [ ] **Step 2: Implement the lock helper**

```python
# src/fold_at_scripps/scheduler/locking.py
"""Postgres advisory lock enforcing a single active scheduler process."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Fixed 64-bit key ("fold-sched"); any constant works as long as it's stable.
_SCHEDULER_LOCK_KEY = 0x666F6C6473636864


async def acquire_scheduler_lock(engine: AsyncEngine) -> AsyncConnection | None:
    """Try to take the scheduler advisory lock on a dedicated connection.

    Returns the open connection (whose lifetime holds the lock — keep it open)
    on success, or None if another live scheduler already holds it. The lock
    releases automatically when the returned connection is closed or dropped.
    """
    conn = await engine.connect()
    try:
        result = await conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _SCHEDULER_LOCK_KEY}
        )
        acquired = bool(result.scalar())
    except Exception:
        await conn.close()
        raise
    if not acquired:
        await conn.close()
        return None
    return conn
```

- [ ] **Step 3: Enforce it in `run_scheduler`**

In `src/fold_at_scripps/scheduler/main.py`:

```python
import logging

from fold_at_scripps.config import get_settings
from fold_at_scripps.db import get_engine, get_sessionmaker
from fold_at_scripps.logging_config import configure_logging
from fold_at_scripps.scheduler.locking import acquire_scheduler_lock

logger = logging.getLogger(__name__)


async def run_scheduler() -> None:
    """Enforce single-scheduler, recover orphaned runs, then poll forever."""
    lock_conn = await acquire_scheduler_lock(get_engine())
    if lock_conn is None:
        logger.error("Another fold-scheduler holds the advisory lock; exiting.")
        raise SystemExit(1)
    try:
        async with get_sessionmaker()() as session:
            await fail_orphaned_runs(session)
        await build_scheduler().run_forever()
    finally:
        await lock_conn.close()


def main() -> None:
    """Console-script entry point."""
    configure_logging(get_settings().log_level)
    asyncio.run(run_scheduler())
```

(Keep the existing `build_scheduler`/imports; add the lock + logging. `configure_logging` is called in `main()` so the scheduler logs consistently.)

- [ ] **Step 4: Run tests** → `uv run pytest tests/scheduler/test_locking.py -q` PASS; `uv run pytest tests/scheduler -q` (no regressions); `uv run ruff check .` clean.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/scheduler/locking.py src/fold_at_scripps/scheduler/main.py \
    tests/scheduler/test_locking.py
git commit -m "feat(scheduler): enforce single scheduler via pg advisory lock"
```

---

### Task 5: Frontend code-split (route-level lazy loading)

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/vite.config.ts`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: the page components (default exports) + `@/components/states/Loading`.
- Produces: route page components loaded via `React.lazy` inside a `<Suspense>` boundary; a vendor `manualChunks` split; `npm run build` emits no chunk over Vite's 500 kB warning.

- [ ] **Step 1: Update `App.tsx` to lazy-load pages**

Replace the static page imports with lazy imports and wrap the routes in `<Suspense>`. Keep `RequireAuth`, `RequireAdmin`, `AppShell`, `AdminLayout`, and `Loading` as static imports (small, always needed):

```tsx
import { lazy, Suspense } from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import RequireAuth from "@/components/RequireAuth";
import RequireAdmin from "@/components/RequireAdmin";
import AppShell from "@/components/AppShell";
import AdminLayout from "@/pages/admin/AdminLayout";
import Loading from "@/components/states/Loading";
import { Toaster } from "@/components/ui/sonner";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const RegisterPage = lazy(() => import("@/pages/RegisterPage"));
const ResetPasswordPage = lazy(() => import("@/pages/ResetPasswordPage"));
const CatalogPage = lazy(() => import("@/pages/CatalogPage"));
const SubmitPage = lazy(() => import("@/pages/SubmitPage"));
const RunsPage = lazy(() => import("@/pages/RunsPage"));
const RunDetailPage = lazy(() => import("@/pages/RunDetailPage"));
const UsersPage = lazy(() => import("@/pages/admin/UsersPage"));
const AllowlistPage = lazy(() => import("@/pages/admin/AllowlistPage"));
const SettingsPage = lazy(() => import("@/pages/admin/SettingsPage"));
const AdminCatalogPage = lazy(() => import("@/pages/admin/CatalogPage"));
const AdminRunsPage = lazy(() => import("@/pages/admin/AdminRunsPage"));
const AdminRunDetailPage = lazy(() => import("@/pages/admin/AdminRunDetailPage"));
const AuditLogPage = lazy(() => import("@/pages/admin/AuditLogPage"));

export default function App(): React.JSX.Element {
  return (
    <>
      <Suspense fallback={<Loading />}>
        <Routes>
          {/* keep the exact same route tree as before, now referencing the lazy consts */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/tools" replace />} />
              <Route path="/tools" element={<CatalogPage />} />
              <Route path="/tools/:toolId" element={<SubmitPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/admin" element={<RequireAdmin />}>
                <Route element={<AdminLayout />}>
                  <Route index element={<Navigate to="/admin/users" replace />} />
                  <Route path="users" element={<UsersPage />} />
                  <Route path="allowed-emails" element={<AllowlistPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="catalog" element={<AdminCatalogPage />} />
                  <Route path="runs" element={<AdminRunsPage />} />
                  <Route path="runs/:runId" element={<AdminRunDetailPage />} />
                  <Route path="audit" element={<AuditLogPage />} />
                </Route>
              </Route>
            </Route>
          </Route>
        </Routes>
      </Suspense>
      <Toaster />
    </>
  );
}
```

**Important:** preserve the EXACT route tree currently in `App.tsx` (read the current file first — nesting of `RequireAuth`/`AppShell`/`RequireAdmin`/`AdminLayout` and the admin child paths must match what Tasks in 9a/9b established). Only the import style (static → `lazy`) and the added `<Suspense>` change.

- [ ] **Step 2: Add a vendor chunk split in `vite.config.ts`**

Add a `build.rollupOptions.output.manualChunks` to the config (alongside the existing `plugins`/`resolve`/`server`/`test`):

```ts
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom", "react-router-dom"],
          "query-vendor": ["@tanstack/react-query"],
          "form-vendor": ["react-hook-form", "zod", "@hookform/resolvers"],
        },
      },
    },
  },
```

- [ ] **Step 3: Update the App smoke test for the lazy boundary**

`frontend/src/App.test.tsx` currently renders `<App/>` and asserts a heading synchronously. With lazy routes it must await Suspense. Update it to render at `/login` via a router and `await screen.findByRole(...)`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { createQueryClient } from "@/lib/query";

test("lazy-loads and renders a route", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  // Login is a public lazy route; it resolves through <Suspense>.
  expect(await screen.findByRole("heading", { name: /log in/i })).toBeInTheDocument();
});
```

(If `App` already renders its own `BrowserRouter`, adapt: keep `App`'s internal routing and render it directly, awaiting the heading. Match the existing App structure — read it first.)

- [ ] **Step 4: Run tests + build**

Run (from `frontend/`): `npm test` → PASS (App smoke + all existing).
Run: `npm run build` → succeeds, and the output shows **no** "chunks are larger than 500 kB" warning. If a chunk still exceeds it, refine `manualChunks` (e.g. split the largest offender — likely Radix/`@radix-ui/*` — into its own `radix-vendor` group). Do NOT just raise `chunkSizeWarningLimit`.
Run: `npm run lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/vite.config.ts frontend/src/App.test.tsx
git commit -m "perf(frontend): route-level code-split + vendor chunks"
```

---

### Task 6: Deployment artifacts + docs (final)

**Files:**
- Rewrite: `Dockerfile`, `docker-compose.yml`
- Create: `Makefile`, `deploy/fold-api.service`, `deploy/fold-scheduler.service`, `deploy/fold.env.example`, `docs/DEPLOYMENT.md`

**Interfaces:** none (ops artifacts). This is the final task — it ends with the full gate.

- [ ] **Step 1: Rewrite `Dockerfile` as a frontend-build stage**

```dockerfile
# fold@Scripps frontend build.
#
# The backend runs on the host (uv + systemd); only the SPA is built here so
# the host needs no Node. Extract the built assets with:
#   docker build --target dist --output type=local,dest=frontend/dist .
# which writes index.html + assets/ into ./frontend/dist for FastAPI to serve.
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Export-only stage: its filesystem is exactly the built dist.
FROM scratch AS dist
COPY --from=frontend-build /build/dist /
```

- [ ] **Step 2: Slim `docker-compose.yml` to Postgres only**

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
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fold -d fold_at_scripps"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

(The `api` service + `src` bind-mount are removed — the app runs on the host.)

- [ ] **Step 3: Create the `Makefile`**

```makefile
.PHONY: postgres build-frontend migrate

postgres:  ## Start the Postgres container
	docker compose up -d postgres

build-frontend:  ## Build the SPA into frontend/dist (host needs no Node)
	rm -rf frontend/dist
	docker build --target dist --output type=local,dest=frontend/dist .

migrate:  ## Apply DB migrations
	uv run alembic upgrade head
```

- [ ] **Step 4: Create the systemd units**

```ini
# deploy/fold-api.service
[Unit]
Description=fold@Scripps API (uvicorn)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=fold
WorkingDirectory=/opt/fold-at-scripps
EnvironmentFile=/etc/fold/fold.env
ExecStartPre=/usr/bin/env uv run alembic upgrade head
ExecStart=/usr/bin/env uv run uvicorn fold_at_scripps.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```ini
# deploy/fold-scheduler.service
[Unit]
Description=fold@Scripps scheduler
After=network-online.target docker.service fold-api.service
Wants=network-online.target

[Service]
Type=simple
User=fold
WorkingDirectory=/opt/fold-at-scripps
EnvironmentFile=/etc/fold/fold.env
ExecStart=/usr/bin/env uv run fold-scheduler
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

(Only the API unit runs migrations — one runner, no race. The scheduler user must have autobio on PATH + Docker/nvidia access.)

- [ ] **Step 5: Create `deploy/fold.env.example`**

```bash
# fold@Scripps environment — copy to /etc/fold/fold.env and fill in.
# NEVER commit a real secret.

# Long random string (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`)
FOLD_SECRET_KEY=CHANGE-ME-to-a-long-random-secret

FOLD_DATABASE_URL=postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps
FOLD_STORAGE_ROOT=/var/lib/fold/data
FOLD_FRONTEND_DIST=/opt/fold-at-scripps/frontend/dist

FOLD_SESSION_HTTPS_ONLY=true
FOLD_GPU_COUNT=8
FOLD_LOG_LEVEL=INFO
FOLD_MAX_UPLOAD_BYTES=104857600
# FOLD_DEBUG=false
```

- [ ] **Step 6: Write `docs/DEPLOYMENT.md`**

Complete doc covering:
- **Host prerequisites:** the `autobio` CLI on PATH, Docker + the NVIDIA container runtime (for autobio's GPU model containers), `uv`, and the repo checked out at `/opt/fold-at-scripps` owned by a `fold` user (in the `docker` group, with GPU access).
- **Database:** `make postgres` (or `docker compose up -d postgres`).
- **Frontend:** `make build-frontend` (produces `frontend/dist`).
- **Config:** `sudo mkdir -p /etc/fold && sudo cp deploy/fold.env.example /etc/fold/fold.env`, then edit — set a real `FOLD_SECRET_KEY`, the DB URL, and `FOLD_STORAGE_ROOT`.
- **Services:** `sudo cp deploy/fold-*.service /etc/systemd/system/`, `sudo systemctl daemon-reload`, `sudo systemctl enable --now fold-api fold-scheduler`. Migrations apply automatically via the API unit's `ExecStartPre`.
- **Verify:** `curl localhost:8000/health`; the SPA at `http://<host>:8000/`; `journalctl -u fold-api -u fold-scheduler -f` for logs.
- **TLS / reverse proxy:** terminate TLS at the institute's intranet proxy (nginx/Caddy/etc.) in front of port 8000; set `FOLD_SESSION_HTTPS_ONLY=true`. (Not provided by this app.)
- **Single scheduler:** only one `fold-scheduler` may run — a second exits immediately (advisory lock).

Write the file with those sections as concrete, copy-pasteable commands.

- [ ] **Step 7: Verify + full gate**

Run: `docker compose config` → parses (Postgres-only, valid).
Run (backend): `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → all green.
Run (frontend, from `frontend/`): `npm run lint && npm test && npm run build` → all green, no >500 kB chunk warning.
(Optional, if `systemd-analyze` is available: `systemd-analyze verify deploy/fold-api.service deploy/fold-scheduler.service`.)

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose.yml Makefile deploy docs/DEPLOYMENT.md
git commit -m "feat: production deployment artifacts (host systemd + Postgres compose + docs)"
```

---

## Self-Review notes (for the executor)

- **Setting names are consistent:** `log_level`, `max_upload_bytes`, `frontend_dist` (env `FOLD_LOG_LEVEL`/`FOLD_MAX_UPLOAD_BYTES`/`FOLD_FRONTEND_DIST`) are used identically across config, middleware, SPA serving, and the `.env` example.
- **Secret guard + test import:** the guard runs in `create_app()`; `tests/conftest.py` sets a non-dev `FOLD_SECRET_KEY` at import so the module-level `app = create_app()` doesn't break collection. The guard only fires when `not debug and secret == dev-default`.
- **SPA fallback registered last:** `_mount_spa` is called after all `include_router` calls, so API routes (and `/openapi.json`) win; the catch-all is GET-only + traversal-guarded and only mounted when `dist` exists.
- **Advisory lock held for lifetime:** `acquire_scheduler_lock` returns the open connection; `run_scheduler` keeps it and only closes it in `finally` (i.e., on shutdown). A second scheduler gets `None` → SystemExit(1).
- **Route tree unchanged in Task 5:** only import style + `<Suspense>` change — read the current `App.tsx` and preserve the exact nesting.
- **Out of scope (unchanged):** the Python app is not containerized (Dockerfile is frontend-build only; compose is Postgres-only); TLS/reverse-proxy is external; multi-node and the optional 9a/9b UI polish are not built.
