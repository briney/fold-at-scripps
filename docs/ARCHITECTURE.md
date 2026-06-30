# fold@Scripps — Architecture

> The technical architecture for fold@Scripps. This document records the
> structural decisions, the reasoning behind them, and the boundaries that keep
> the system simple now while leaving room to grow. It is the companion to
> [`VISION.md`](./VISION.md); where the vision states *why* and *what*, this
> states *how*.

## Guiding constraints

These come directly from the vision and shape every decision below:

- **Single node now.** The web server and the models run on the same 8× H200
  node. No near-term multi-node plans, but multi-node must remain reachable.
- **`autobio` is the execution engine.** It owns the containerized models, their
  inputs/outputs, and their execution. This app orchestrates and presents; it
  never reimplements model logic.
- **Simple, not over-engineered.** A simple job queue is sufficient. We
  deliberately avoid heavyweight infrastructure until there is a real need.
- **Don't wall off growth.** Three growth axes are kept reachable without being
  built now: new models/categories, multi-node compute, and a programmatic API.

The core technique for reconciling "simple now" with "flexible later" is a small
set of **swappable boundaries** (see [Boundaries](#the-swappable-boundaries)):
a transport-agnostic service layer, plus `Executor`, `Storage`, and identity
provider interfaces. Each is implemented with the simplest single-node option
today, behind an interface that localizes the blast radius of a future change.

## Technology choices

| Concern | Choice | Why |
| --- | --- | --- |
| Backend API | **FastAPI** | API-first native; auto-generated OpenAPI docs (makes the future API nearly free); Pydantic-native; async fits an I/O-bound web tier. |
| Frontend | **React + TypeScript + Tailwind**, built with **Vite** | A clean, modern SPA that consumes the JSON API. Pure SPA, not a Node meta-framework, to keep the "Python service layer + API" story clean. |
| Database | **PostgreSQL** | Single source of truth for both data and the job queue; concurrent-safe job claiming via `SELECT … FOR UPDATE SKIP LOCKED`; multi-node-reachable. |
| Job queue / scheduler | **Custom, DB-backed**, behind an `Executor` interface | Exclusive whole-GPU allocation is the dominant constraint, and off-the-shelf queues don't model it; a small purpose-built scheduler is the simplest *correct* fit and adds zero infrastructure. |
| Auth | **Local accounts** (v1), behind an identity-provider boundary | Lightweight identity for attribution/quotas/scoping — not hardened security (intranet only). Swappable to SSO/LDAP later. |
| Model execution | **`autobio`** (typed Python API) | Structured outputs + metadata (wall time, GPU IDs) returned directly, rather than parsing CLI output. |

## Components and process model

Everything runs on the single node. The one asymmetry that drives the process
model: **the scheduler must launch Docker containers and assign specific GPUs**
(via the NVIDIA Container Toolkit), so it needs direct host Docker + GPU access.
The API does not — it only touches Postgres and the filesystem.

```
                            ┌──────────────────────────── Docker Compose ───────────────────────────┐
                            │                                                                        │
   Browser ─── HTTPS ───────┼──▶  nginx ──▶  SPA static assets                                       │
      │                     │                                                                        │
      └──── JSON / cookie ──┼──▶  FastAPI (API)  ──┐                                                 │
                            │         │            │                                                 │
                            │         ▼            ▼                                                 │
                            │   Service layer   PostgreSQL  ◀──────────────┐                         │
                            │   (transport-                 │              │                         │
                            │    agnostic)                  │              │                         │
                            └───────────────────────────────┼──────────────┼─────────────────────────┘
                                                            │              │
                                          claims runs via   │              │  reads/writes runs,
                                       FOR UPDATE SKIP LOCKED│              │  artifacts, usage
                                                            ▼              │
                              ┌──── host process (systemd) ──────────────────────────────────┐
                              │   Scheduler  ──▶  Executor (v1: local autobio)                │
                              │      │                    │                                   │
                              │      │ owns 8-GPU pool    ▼                                   │
                              │      │             autobio Python API                         │
                              │      │                    │                                   │
                              │      │                    ▼                                   │
                              │      │             docker run --gpus … (tool container)       │
                              │      ▼                    │                                   │
                              │   Storage (v1: local FS) ◀┘  inputs / config / outputs        │
                              └──────────────────────────────────────────────────────────────┘
```

**In Docker Compose:**
- **nginx** — serves the built SPA static assets and reverse-proxies the API.
- **FastAPI (API)** — cookie-session auth, run CRUD, tool catalog, quota checks,
  ownership-checked downloads. A thin transport over the service layer. No Docker
  or GPU access.
- **PostgreSQL** — persistent volume; the single source of truth.

**Host process (systemd), with Docker + GPU access:**
- **Scheduler** — owns the 8-GPU pool; claims queued runs; allocates whole GPUs
  exclusively; drives the `Executor`; handles crash recovery.

The **service layer** is plain transport-agnostic Python (run lifecycle, quota
logic, catalog sync, enqueue). It is imported by both the API and the scheduler,
and it is the durable core that a future programmatic API would reuse unchanged.

## Data model

PostgreSQL. Core entities:

- **User** — identity (from the auth provider), display name, role
  (`user` / `admin`), quota config. Everything scopes to a user.
- **Tool** — one row per autobio tool **version**: id, category, GPU count, and a
  **snapshot of the input schema**, synced from `autobio list` / `info` rather
  than hand-authored. The guided form is generated from the stored schema. The
  version is pinned so historical runs remain interpretable against the schema
  they used.
- **Run** — the central, user-facing unit. One submission = one run = one queue
  job (no separate Job entity until something forces it). Fields: user, tool +
  version, input params (JSON), status
  (`queued` / `running` / `succeeded` / `failed` / `canceled`), assigned GPU IDs,
  timestamps (submitted / started / finished), wall time, GPU-seconds, error
  info, output-dir pointer.
- **Artifact** — files a run produced: name, type, size, path. A lightweight
  index over the run's output directory, populated on completion. The bytes live
  on disk; the DB only points at them.

**Usage and quotas.** Usage (GPU-hours) is recorded on every run from day one,
for visibility and so budgets can be enabled later without backfilling. v1
**enforces a per-user concurrency cap** (max simultaneous queued/running runs) —
the control that actually prevents one user monopolizing the 8 GPUs. A GPU-hours
budget is a later, additive toggle.

## Job lifecycle

1. **Submit.** User browses the catalog (synced from autobio), fills the guided
   form (generated from the stored schema), and uploads any inputs.
2. **Validate + enqueue.** The API and service layer validate the request and
   check the concurrency quota, create a `Run` with status `queued`, and write
   the user's inputs and the autobio JSON config to `Storage`.
3. **Schedule.** The scheduler claims a `queued` run via
   `SELECT … FOR UPDATE SKIP LOCKED` once enough GPUs are free, marks it
   `running`, and assigns specific GPU IDs exclusively (count from the tool's
   metadata, default 1).
4. **Execute.** The `Executor` invokes autobio's Python API, which launches the
   tool's Docker container on the assigned GPUs.
5. **Finalize.** On completion the Executor writes outputs to `Storage`, indexes
   `Artifact` rows, records wall time and GPU-seconds, and sets the run
   `succeeded` or `failed`.
6. **Observe + retrieve.** The SPA **polls** run status (`GET /runs/{id}`).
   On success the user views/downloads artifacts, served by the API with an
   ownership check (never static-served).

**GPU allocation policy:** exclusive, variable-count. Each run reserves N whole
GPUs for its duration; no VRAM packing and no OOM contention. The cap is ≤ 8
concurrent runs, and a small job occupies a whole card — accepted for simplicity;
packing/sharing is a possible future optimization the model does not preclude.

**Crash recovery:** because the scheduler owns the dispatch loop, it is also
responsible for recovery — on restart it sweeps for runs stuck in `running` whose
process no longer exists and fails (or re-queues) them. This is the one piece an
off-the-shelf queue would have provided; it is bounded and lives entirely within
the scheduler.

## Storage

Model outputs live on the filesystem; Postgres stores metadata and paths. v1 uses
the node's **local filesystem** behind a thin `Storage` interface.

Per-run directory layout:

```
…/runs/{run_id}/
├── inputs/    # user uploads (e.g. a PDB)
├── config/    # the autobio JSON config we generate
└── outputs/   # autobio results; the Artifact index points in here
```

Downloads are always served by the API with an ownership check, so scoping is
enforced and never bypassed by static file serving.

Because the scheduler runs on the host while the API runs in a container, the
per-run directory tree is a single location on the host that the API container
bind-mounts: the API (via the service layer) writes `inputs/` and `config/` at
submit time and reads `outputs/` to serve downloads, while the scheduler's
`Executor` writes `outputs/`.

## Authentication

Lightweight by design — identity for attribution, quotas, and output scoping, not
hardened security.

- **Mechanism (v1):** local accounts (app-managed users + passwords), behind an
  **identity-provider boundary** so the mechanism is swappable.
- **Sessions:** httpOnly, secure session **cookies** for the SPA — simple and
  safe-enough on an intranet, and it avoids the JWT-in-`localStorage` XSS footgun.
- **Future programmatic credential:** per-user **API tokens**, issued from the UI
  and checked by the same auth layer, mapping to the same `User`. Not built now,
  not precluded.

## The swappable boundaries

These four interfaces are the mechanism that keeps the system simple today while
leaving each growth axis reachable. Each has a trivial single-node implementation
now; growth means swapping the implementation, not rearchitecting.

| Boundary | v1 implementation | What it unlocks |
| --- | --- | --- |
| **Service layer** (transport-agnostic core) | Plain Python used by the API | A programmatic **API** as just another adapter over the same core. |
| **`Executor`** | Local autobio (Python API → Docker) | **Multi-node** execution; or handing scheduling to SLURM/k8s — both replace only this adapter. |
| **`Storage`** | Local filesystem | Shared **NFS** or **object storage** for multi-node, without touching callers. |
| **Identity provider** | Local accounts | **SSO (OIDC/SAML)** or **LDAP/AD** without changing the app's notion of "current user." |

## Growth axes, concretely

- **New models / categories.** Integrating an autobio tool is a sync: it appears
  in the catalog with its schema, and its guided form is generated from that
  schema. A small, well-bounded change — usually no bespoke UI work.
- **Multi-node compute.** Postgres `SKIP LOCKED` already permits multiple
  schedulers claiming from the same queue; `Storage` moves to shared/object
  storage; the `Executor` routes whole jobs to nodes (a single autobio container
  always runs entirely on one node, so this is job *placement*, not job
  *splitting*).
- **Programmatic API.** The service layer already holds all domain logic and
  FastAPI already generates the OpenAPI contract; exposing the API is adding
  token auth, docs, and stability guarantees — not new functionality.

## Explicit non-goals (for now)

Carried from the vision; recorded here so the architecture is not stretched to
accommodate them prematurely:

- Chained/automated multi-tool pipelines.
- Multi-node scheduling (reachable, not built).
- A public programmatic API (reachable, not built).
- Hardened, security-critical auth.
- VRAM packing / GPU sharing.
- Server-sent-events / push status (polling is sufficient for v1).
