# fold@Scripps — Deployment & Packaging (Plan 10) — Design

> The final plan: package and deploy the finished application (backend Plans 1–8
> + frontend 9a/9b) for the single co-located GPU node, and close the
> operational deferrals accumulated across earlier plans.

## Purpose & scope

Make fold@Scripps deployable and operable on the institute's single 8×H200
node, and resolve the carry-in deferrals that earlier plans intentionally
postponed to deployment. The application logic is done; this plan is packaging,
process supervision, serving the built SPA, and hardening.

**Runtime topology (decided):** the backend runs as **two host processes**
supervised by **systemd** (the uvicorn API + the `fold-scheduler`), directly on
the host where `autobio`, Docker, and the GPUs already live (native access — no
Docker-socket/nvidia gymnastics). **Postgres runs in Docker** (compose). The
**frontend is built in a Docker stage** (so the host needs no Node) and
**FastAPI serves the built `frontend/dist`** same-origin (so the session cookie
works with no CORS).

**In scope:** FastAPI SPA serving; systemd units + migration step; a
Postgres-only compose; a frontend-build Docker stage; a deployment doc; and the
deferrals — request/upload body-size limit, `pg_advisory_lock` single-scheduler
enforcement, frontend code-split, structured logging, and the secret-key startup
guard.

**Out of scope:** multi-node/orchestration; TLS termination and reverse proxy
(assume the intranet or an existing proxy fronts the app — documented, not
built); the residual optional 9a/9b UI polish (not deployment); any change to
autobio/GPU/Docker, which live natively on the host.

## Removed / repurposed

- **Remove the Python app Docker image** and the compose `api` service — the app
  runs on the host, not in a container. `docker-compose.yml` becomes
  Postgres-only.
- **Repurpose `Dockerfile`** into a frontend-build stage (`node:20` →
  `npm ci && npm run build` → `frontend/dist`).

## Components

### 1. FastAPI serves the SPA (`src/fold_at_scripps/main.py`)

- Mount `StaticFiles` for the built assets (e.g. `frontend/dist/assets`) and
  serve `frontend/dist/index.html` as a **catch-all SPA fallback** for any
  non-API GET, registered **after** all API routers so it never shadows
  `/auth`, `/tools`, `/runs`, `/admin`, `/health`.
- The static mount + fallback activate only when the `frontend/dist` directory
  exists, so running the API in dev without a build still works (API-only).
- The dist location is resolved from a setting (default `frontend/dist`
  relative to the repo root) so the host layout is configurable.

### 2. systemd units + migrations (`deploy/`)

- `deploy/fold-api.service`: `WorkingDirectory` = repo; `EnvironmentFile` =
  `/etc/fold/fold.env`; `ExecStartPre=/usr/bin/env uv run alembic upgrade head`
  (the **single** migration runner); `ExecStart=… uv run uvicorn
  fold_at_scripps.main:app --host 0.0.0.0 --port 8000`; `Restart=on-failure`;
  `After=network.target`.
- `deploy/fold-scheduler.service`: `ExecStart=… uv run fold-scheduler`;
  `Restart=on-failure`; same `EnvironmentFile`/`WorkingDirectory`. No migration
  step here (avoids a race — the API unit owns migrations).
- `deploy/fold.env.example`: the required env — `FOLD_SECRET_KEY`,
  `FOLD_DATABASE_URL`, `FOLD_STORAGE_ROOT`, `FOLD_SESSION_HTTPS_ONLY`,
  `FOLD_GPU_COUNT`, `FOLD_LOG_LEVEL`, `FOLD_MAX_UPLOAD_BYTES`, and any others —
  with safe placeholders (never a real secret).

### 3. Postgres compose (`docker-compose.yml`)

Postgres 16 only: `restart: unless-stopped`, named volume, the existing
healthcheck, port 5432. Used in both dev (devs run the app via `uv` locally
against it) and prod.

### 4. Frontend-build Docker stage (`Dockerfile`)

A build-only image: `FROM node:20`, copy `frontend/`, `npm ci && npm run build`,
output `frontend/dist`. A `make build-frontend` (or documented
`docker build --output type=local,dest=frontend ...`) extracts `dist` to the
host for FastAPI to serve. Pinned Node for reproducibility; the prod host needs
no Node.

### 5. Deferrals

- **Upload/body-size limit** (`src/fold_at_scripps/main.py` +
  `config.py`): a Starlette middleware that rejects any request whose
  `Content-Length` exceeds `settings.max_upload_bytes` with **413**
  (before the body is read). Protects the multipart `POST /runs`. Default a
  sensible cap (e.g. 100 MB); configurable via `FOLD_MAX_UPLOAD_BYTES`.
- **`pg_advisory_lock` single-scheduler** (`src/fold_at_scripps/scheduler/main.py`):
  at `run_scheduler` startup, open a **dedicated** connection and
  `SELECT pg_try_advisory_lock(<fixed 64-bit key>)`; if it returns false
  (another scheduler holds it) → log an error and exit non-zero. Otherwise hold
  the connection (and thus the lock) for the process lifetime — the lock
  releases automatically on disconnect/crash. This *enforces* the
  single-scheduler invariant Plan 6 only documented (prevents GPU
  double-booking by a second accidental `fold-scheduler`).
- **Frontend code-split** (`frontend/src/App.tsx`, `frontend/vite.config.ts`):
  convert the route page components to `React.lazy` + a `<Suspense>` boundary
  (route-level splitting), and/or a manual vendor chunk, so `npm run build`
  emits no chunk over Vite's 500 kB warning threshold. A lightweight route
  fallback (reuse the shared `Loading`).
- **Structured logging** (`src/fold_at_scripps/logging_config.py` or similar):
  a `logging.dictConfig` with a consistent formatter and level from
  `settings.log_level`; applied by both entry points (the app lifespan/factory
  and `fold-scheduler`'s `main`), and uvicorn aligned to the same format. Keep
  it simple text logging (levels + timestamps + logger name) — no JSON unless
  trivially free.
- **Secret-key startup guard** (`src/fold_at_scripps/config.py` or
  `main.py`): refuse to boot when `not settings.debug and
  settings.secret_key == "<dev default>"` — raise a clear error at
  `create_app` (and mirror the check in the scheduler entry). Prevents shipping
  the insecure dev session key.

### 6. Deployment doc (`docs/DEPLOYMENT.md`)

Host prerequisites (autobio CLI, Docker, nvidia runtime, `uv`), Postgres via
compose, building/extracting the frontend, `/etc/fold/fold.env`, installing +
enabling the two systemd units, running migrations (automatic via
`ExecStartPre`), and a note that TLS/reverse-proxy termination is expected to be
handled by the intranet/an existing proxy in front of port 8000.

## Configuration additions (`config.py`)

Add settings (env-prefixed `FOLD_`): `log_level: str = "INFO"`,
`max_upload_bytes: int = 100 * 1024 * 1024`, and `frontend_dist: str =
"frontend/dist"` (or resolved default). Keep true secrets in env; operational
tunables that admins change stay DB-backed (SystemSettings) per the
admin-console principle.

## Error handling

- Over-limit uploads → 413 with a clear detail, before body read.
- A second scheduler → immediate non-zero exit with a logged reason (systemd
  will not restart-loop it into contention because `pg_try_advisory_lock` fails
  fast and the message is explicit; `Restart=on-failure` with a start-limit is
  acceptable, or document `RestartSec`).
- Missing `frontend/dist` in dev → API serves normally, no SPA (no crash).
- Boot with the dev secret in prod → hard fail with an actionable message.

## Testing

- **SPA serving** (pytest, ASGI client): an unknown non-API GET returns the
  SPA `index.html`; `/health` and an API route still resolve; with `dist`
  absent the app still boots and API routes work.
- **Body-limit middleware**: a request with `Content-Length` over the cap → 413;
  under the cap → passes through.
- **Advisory lock** (integration, Postgres): acquiring the lock twice
  concurrently — the second acquisition fails (the helper returns false / the
  startup path exits). Test at the helper level to keep it deterministic.
- **Secret-key guard**: `create_app` raises when `not debug` + dev default;
  succeeds with a real key or in debug.
- **Frontend**: `npm run build` produces no >500 kB chunk (a build-output
  check / documented); lazy routes still render (the existing component tests
  cover the pages; a smoke test that a lazy route resolves via `<Suspense>`).
- The Alembic no-drift migration test (Plan 2) continues to pass.
- Backend suite stays green against Postgres + the live autobio smoke test;
  frontend lint/test/build green; CI unchanged (backend job + frontend
  lint/test/build; E2E local-only).

## Success criteria

- A fresh host can deploy fold@Scripps by: `docker compose up -d postgres`,
  building + extracting the frontend, setting `/etc/fold/fold.env`, and enabling
  the two systemd units — migrations apply automatically, the API serves the SPA
  and JSON on port 8000, and the scheduler runs biological models via autobio on
  the GPUs.
- Exactly one scheduler can run (a second exits immediately); oversized uploads
  are rejected; the SPA loads without a monolithic bundle; the app refuses to
  boot with the dev secret in production.
- `npm run lint && npm test && npm run build` and the backend suite stay green.

## Deferred / future (explicitly not built)

Multi-node scheduling; built-in TLS/reverse proxy (documented as external);
object-storage backend (the `Storage` boundary already allows it later); the
optional 9a/9b UI polish (theme persistence, shared `errorMessage` helper,
Settings no-op-PATCH guard, `aria-describedby`).
