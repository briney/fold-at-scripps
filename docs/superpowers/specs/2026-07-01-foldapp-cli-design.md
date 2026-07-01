# fold@Scripps — `foldapp` operator CLI — Design

> A single, user-scoped operator CLI that automates installation, deployment,
> upgrade/refresh, rollback, and day-to-day operations for the fold@Scripps node.
> It consolidates the existing `fold-admin` / `fold-scheduler` console scripts and
> the `Makefile` into one entry point, and introduces a near-rootless deployment
> model that supersedes the system-scoped layout shipped in Plan 10.

## Purpose & scope

fold@Scripps is deployable today, but deployment and upgrades are a manual,
mostly-`sudo` sequence documented in `docs/DEPLOYMENT.md` (create a system user,
clone to `/opt`, scaffold `/etc/fold/fold.env`, `make build-frontend`, install +
enable system systemd units, restart on upgrade). This project replaces that
sequence with `foldapp` — a Typer CLI that a couple of admins can drive from the
command line to stand up, operate, and upgrade the node with minimal privilege.

**In scope:** a new `foldapp` console script (Typer subpackage inside the app); a
user-scoped deployment model (home-dir layout + `systemctl --user` units); a
first-run installer; a guarded upgrade path (backup + health-gate + explicit
rollback); operational commands (status/logs/start/stop/restart/db); preflight
diagnostics (`doctor`); folding `create-admin` / `sync-catalog` / the scheduler
entry under `foldapp`; retiring the `Makefile` and the system-scoped deploy
artifacts; and rewriting `docs/DEPLOYMENT.md`.

**Out of scope:** installing OS-level prerequisites (Docker, the NVIDIA container
runtime, `uv`, `autobio`) — these are assumed present and are *verified*, not
installed; multi-node orchestration; TLS/reverse-proxy termination (external, as
today); any change to autobio/GPU/Docker, which live natively on the host; and
the operational/policy config that is deliberately DB-backed and owned by the
admin console (quotas, maintenance mode as a *policy*, tool enable/disable).

## Decisions locked in brainstorming

These were settled with the user and drive the rest of the design:

1. **Scope: app-level operator + preflight checks.** foldapp automates
   app-level lifecycle and *verifies* host prerequisites with clear
   diagnostics; it does not install OS packages.
2. **Consolidation: unify everything under `foldapp`.** One operator entry
   point. `fold-admin` and the `fold-scheduler` console script are removed;
   their behavior moves under `foldapp` subcommands. The `Makefile` is retired.
3. **Privilege posture: user-scoped (near-rootless).** Everything under one
   service user's home; supervision via `systemctl --user`; the only privileged
   step is a one-time, optional `sudo loginctl enable-linger <user>`. Docker
   access (inherent, because the scheduler runs GPU containers via autobio and
   Postgres is containerized) is via the `docker` group.
4. **Environments: production node first, dev as a cheap bonus.** A lightweight
   `foldapp dev up` is included because it nearly falls out of the user-scoped
   model, but the production node is the priority.
5. **Upgrade safety: guarded.** Backup (pg_dump) + record git ref + health-gate
   on upgrade; failures stop and leave the system in a visibly-safe state; a
   separate `foldapp rollback` performs recovery. No surprise auto-revert.

## Architecture & packaging (Approach A)

`foldapp` is a Typer app backed by a new subpackage
`src/fold_at_scripps/foldapp/`. It **imports app internals** for the parts that
benefit from reuse (read `Settings` from `config.py`; call the health-check
path; read/write `SystemSettings.maintenance_mode` via the existing admin
settings service; reuse `configure_logging`) and **shells out** for the
mechanical, external actions (`git`, `docker` / `docker compose`, `uv sync`,
`alembic`, `systemctl --user`, `journalctl --user`, `pg_dump` / restore).

Proposed modules (each small and single-purpose):

- `cli.py` — the Typer app and command wiring; `main()` is the console-script
  entry point.
- `context.py` — resolves the runtime layout: app dir (repo root), `.env` path,
  state/data/backups dirs, the service user, unit paths. One place that owns
  "where things live," so every command agrees.
- `preflight.py` — the individual checks + a runner that renders OK/WARN/FAIL.
- `envfile.py` — `.env` scaffolding + `FOLD_SECRET_KEY` generation + redacted
  `config show`.
- `units.py` — renders the `systemd --user` unit files from templates.
- `postgres.py` — compose up + `pg_isready` wait; `pg_dump` / restore helpers.
- `frontend.py` — `docker build --target dist` wrapper.
- `state.py` — read/write `state/last_deploy.json` (prev git ref, backup path).
- `install.py`, `deploy.py`, `upgrade.py` — the lifecycle orchestrations.
- `run.py` — the foreground `serve` / `scheduler` entry points invoked by the
  systemd units.

Console script (in `pyproject.toml`):

```toml
[project.scripts]
foldapp = "fold_at_scripps.foldapp.cli:main"
```

**Bootstrap (chicken-and-egg).** `foldapp` is a console script inside the
package, so a first run needs the package installed. A committed `bootstrap.sh`
(clone if needed → `uv sync` → `uv run foldapp doctor`) handles this; the same
three steps are documented as plain commands so the script is optional.

## Deployment model & layout (user-scoped)

All paths are under the service user's home and are overridable via env; the
defaults are:

- **App dir** = the git checkout (e.g. `~/fold-at-scripps`). foldapp resolves
  its own repo root; no fixed `/opt` requirement.
- **Config**: `<APP_DIR>/.env` (already git-ignored; `pydantic-settings` reads
  `.env` from the working directory natively, and the units set
  `WorkingDirectory=<APP_DIR>`). Holds secrets/infra only:
  `FOLD_SECRET_KEY`, `FOLD_DATABASE_URL`, `FOLD_STORAGE_ROOT`,
  `FOLD_FRONTEND_DIST`, `FOLD_SESSION_HTTPS_ONLY`, `FOLD_GPU_COUNT`,
  `FOLD_LOG_LEVEL`, `FOLD_MAX_UPLOAD_BYTES`. Operational/policy config stays
  DB-backed (`SystemSettings`) and owned by the admin console — foldapp does not
  manage it.
- **State / data**: `~/.local/share/fold/` →
  - `data/` — the storage root (run inputs/outputs); `FOLD_STORAGE_ROOT`.
  - `backups/` — pg_dump snapshots (rotated to the last 5 by default).
  - `state/last_deploy.json` — previous git ref + last backup path (for
    rollback).
  Kept **outside the checkout** so `git pull` / re-clone never touches data.
- **Supervision**: `systemctl --user` units at
  `~/.config/systemd/user/{fold-api,fold-scheduler}.service`, rendered by
  `foldapp install` with absolute paths, `EnvironmentFile=<APP_DIR>/.env`, and a
  pinned `Environment=PATH=` that includes uv's and autobio's directories
  (carrying forward the Plan 10 PATH lesson). `ExecStart` invokes
  `foldapp serve` / `foldapp scheduler` (uniform entry; lets foldapp apply
  logging config). `Restart=on-failure`.
- **Boot-start**: user services start at boot only if lingering is enabled. This
  is the single privileged step — `sudo loginctl enable-linger <user>`.
  foldapp *detects* whether linger is on and **prints** the exact command when
  it is not; it never runs sudo itself. If the operator prefers to start
  services manually after login, linger is optional.
- **Postgres**: unchanged — `docker compose up -d postgres`
  (`restart: unless-stopped`, named volume), with the service user in the
  `docker` group. foldapp waits for `pg_isready` before migrating, which closes
  the Plan 10 cold-boot race.

## Command surface

Every mutating command supports `--dry-run` (print the exact ordered steps /
shell-outs without executing) and `--yes` (skip confirmations). Destructive
commands (`rollback --db`, `uninstall --purge`, `db restore`) confirm by
default.

### Lifecycle

- **`foldapp install`** — first-time setup, idempotent: preflight → scaffold
  `.env` (generate `FOLD_SECRET_KEY` if absent) → create state/data/backups
  dirs → `uv sync` → start Postgres + wait for ready → `alembic upgrade head` →
  build frontend → render + `systemctl --user enable --now` both units → check
  linger → print next step (`foldapp admin create-admin`).
- **`foldapp deploy`** — "make the running system match the current checkout":
  start Postgres, ensure migrated, ensure units enabled + (re)started. `install`
  is `deploy` plus first-time scaffolding.
- **`foldapp upgrade [--ref <git-ref>]`** — the guarded flow (below).
- **`foldapp refresh`** — light re-apply, no `git pull` and no migration:
  rebuild frontend + `catalog sync` + restart services.
- **`foldapp rollback [--db]`** — restore the recorded previous git ref +
  restart (health-gated); `--db` also restores the last pg_dump snapshot.
- **`foldapp uninstall [--purge]`** — disable/remove the user units; leaves data
  unless `--purge`.

### Operations

- **`foldapp status`** — units active? `/health` OK? Postgres up? current git
  ref/version, `maintenance_mode`, GPU/scheduler summary. This is the default
  command when `foldapp` is run bare.
- **`foldapp start|stop|restart [api|scheduler|all]`** — wrap `systemctl --user`.
- **`foldapp logs [api|scheduler] [-f]`** — wrap `journalctl --user -u …`.
- **`foldapp db dump|restore`** — pg_dump / restore helpers (`upgrade` reuses
  `dump`); `restore` confirmed.

### Diagnostics

- **`foldapp doctor`** — run all preflight checks; OK/WARN/FAIL + one-line
  remediation each; non-zero exit on any FAIL. Read-only.
- **`foldapp version`** — app version + git ref.
- **`foldapp config show`** — resolved settings, secrets redacted.
  (`foldapp config init` scaffolds `.env`; `install` also does this.)

### Admin (moved from `fold-admin`)

- **`foldapp admin create-admin`** — bootstrap the first admin.
- **`foldapp catalog sync`** — sync the tool catalog from autobio.

### Run targets (invoked by the systemd user units)

- **`foldapp serve`** — foreground uvicorn (the `fold-api` unit's `ExecStart`).
- **`foldapp scheduler`** — foreground scheduler (the `fold-scheduler` unit's
  `ExecStart`).

### Dev (the cheap bonus)

- **`foldapp dev up`** — foreground, ephemeral: Postgres + `uvicorn --reload` +
  the Vite dev server; no systemd, no frontend build. `Ctrl-C` tears it down.

## Preflight (`foldapp doctor` + a fast subset before mutating commands)

Each check reports **OK / WARN / FAIL** with a one-line fix; any FAIL causes a
non-zero exit and blocks the mutating command that ran it.

- **uv** present + version; **Python ≥ 3.11**.
- **Docker** daemon reachable (`docker info`); service user in the `docker`
  group; `docker compose` v2 present.
- **NVIDIA runtime + GPU** visible
  (`docker run --rm --gpus all … nvidia-smi`) — **WARN** (dev boxes lack it),
  not FAIL.
- **autobio** on PATH and responding (the scheduler shells out to it) — FAIL for
  a deploy context, WARN for dev.
- **Ports** 8000 / 5432 free, or held by our own services.
- **`.env`** present; `FOLD_SECRET_KEY` set and not the dev default;
  `storage_root` writable; sufficient disk for data/backups.
- **linger** enabled for boot-start — **WARN** + print
  `sudo loginctl enable-linger <user>`.
- **Postgres** reachable (when already deployed).

## Guarded upgrade & rollback

### Upgrade

Ordered steps, each logged; abort on any error:

1. Fast preflight.
2. Record the current git rev → `state/last_deploy.json` (prev_ref, timestamp).
3. **maintenance_mode ON** via the DB `SystemSettings` service (the scheduler
   stops claiming new runs; the API can surface a banner). In-flight `RUNNING`
   jobs are left alone — foldapp does not kill running work.
4. **pg_dump snapshot** → `backups/pre-upgrade-<ts>.sql.gz`; record the path in
   state; rotate to the last 5 snapshots (configurable).
5. `git pull` (or `git fetch && git checkout <ref>` when `--ref` is given);
   record the new ref.
6. `uv sync` → build frontend → `alembic upgrade head`.
7. `systemctl --user restart` both units.
8. **Health-gate**: poll `/health` until healthy (default timeout ~60 s) and
   confirm both units are active.
9. **maintenance_mode OFF**; print a summary (old→new ref, backup path).

**Failure posture.** On any failure before the health-gate passes, stop and
**leave maintenance_mode ON** (a visibly-safe state), then print the exact
`foldapp rollback` command. There is no automatic revert — this is the "guarded"
choice.

### Rollback

- **`foldapp rollback`** — read state → `git checkout <prev_ref>` → `uv sync` →
  build frontend → restart → health-gate → maintenance_mode off.
- **`foldapp rollback --db`** — additionally restore the recorded pg_dump
  snapshot (destructive; confirmed). This is the real revert when a **migration**
  is the problem. The docs state plainly that a code-only rollback can be
  incompatible with an already-applied migration, so `--db` is required in that
  case.

## Configuration handling

- `.env` is scaffolded from an updated `deploy/fold.env.example` (user-scoped
  home-path defaults). `FOLD_SECRET_KEY` is generated with
  `secrets.token_urlsafe(48)` when absent; foldapp never overwrites an existing
  key.
- Only secrets/infra live in `.env`. Operational/policy config remains DB-backed
  (`SystemSettings`) and is owned by the admin console; foldapp reads
  `maintenance_mode` (to toggle it during upgrade) but does not otherwise manage
  policy config.
- `foldapp config show` prints the resolved settings with secrets redacted.

## Retire / replace from Plan 10

- `deploy/fold-api.service`, `deploy/fold-scheduler.service` (system units) →
  **replaced** by user-unit templates that foldapp renders into
  `~/.config/systemd/user/`.
- `deploy/fold.env.example` → **updated** for user-scoped defaults.
- `Makefile` → **retired**; its three targets fold into foldapp (`postgres` →
  part of `deploy`; `build-frontend` → `foldapp refresh` / the frontend build
  step; `migrate` → the migration step of `install` / `deploy`).
- `src/fold_at_scripps/cli.py` (`fold-admin`) and the `fold-scheduler` console
  script → **removed**; behavior moves under `foldapp admin create-admin`,
  `foldapp catalog sync`, and `foldapp scheduler`. The scheduler *logic*
  (`scheduler/main.py`) is retained and called by `foldapp scheduler`.
- **Kept as-is**: `docker-compose.yml` (Postgres-only) and `Dockerfile` (the
  frontend-build stage — foldapp shells `docker build --target dist`).
- `docs/DEPLOYMENT.md` → **rewritten** around the foldapp user-scoped flow
  (bootstrap → doctor → install → create-admin → status; upgrade/rollback;
  troubleshooting incl. linger, the docker group, Postgres readiness).

## Error handling, idempotency & output

- All commands are **idempotent / re-runnable**.
- Shell-outs use `subprocess.run([...])` with argument lists — **never
  `shell=True`** (per project conventions). Return codes are checked; stderr
  tails are surfaced with clear, actionable messages.
- `--dry-run` on every mutating command; `--yes` to skip prompts; destructive
  ops confirm by default.
- foldapp **never** runs sudo itself; when linger is missing it prints the
  command for the operator to run.
- `rich` for progress/status output; reuse the app's `configure_logging`.

## Testing

- **Unit** (the logic-heavy pure parts):
  - unit-file rendering (template → expected content, incl. the pinned PATH and
    `EnvironmentFile`);
  - each preflight check, mocking `shutil.which` / `subprocess`;
  - `state.py` read/write round-trip;
  - `.env` scaffolding + secret generation (and non-overwrite of an existing
    key);
  - **upgrade orchestration** with mocked shell-outs: assert step order,
    maintenance_mode on→off on success, and that a mid-flow failure stops and
    leaves maintenance_mode ON;
  - `config show` redaction.
- **Integration** (Postgres, marked): pg_dump → restore round-trip; the
  maintenance_mode toggle via the DB.
- **CLI smoke**: `foldapp --help` and every subcommand `--help`; `foldapp
  doctor` on the dev box. No GPU is required in CI. The existing backend suite
  and the Alembic no-drift test stay green.

## Success criteria

- A fresh checkout on the node reaches a running system with:
  `./bootstrap.sh` (or `uv sync`) → `foldapp doctor` → `foldapp install` →
  `foldapp admin create-admin`, with at most one privileged command
  (`sudo loginctl enable-linger <user>`, and only for boot-start).
- `foldapp upgrade` performs a backed-up, health-gated upgrade; a failed upgrade
  leaves the system in a visibly-safe state and is recoverable with
  `foldapp rollback` (`--db` when a migration is at fault).
- `foldapp status` / `logs` / `start|stop|restart` cover day-to-day operations
  without hand-written `systemctl --user` / `journalctl` invocations.
- The `Makefile`, the system systemd units, and the `fold-admin` /
  `fold-scheduler` scripts are gone, with their behavior available under
  `foldapp`; `docs/DEPLOYMENT.md` documents only the foldapp flow.
- Backend suite, Alembic no-drift test, and frontend lint/test/build stay green.

## Deferred / future (explicitly not built)

- Installing OS-level prerequisites (Docker, NVIDIA runtime, uv, autobio) —
  verified, not installed.
- A lease-watchdog for the scheduler's Postgres advisory lock, and automatic
  scheduler restart after a Postgres container restart (documented operational
  caveat from Plan 10; foldapp's `status` can surface the condition, but
  auto-healing it is out of scope here).
- Automatic rollback on health-gate failure (deliberately rejected in favor of
  the guarded posture).
- Multi-node orchestration; built-in TLS/reverse proxy (external, as today);
  object-storage backend (the `Storage` boundary already allows it later).
