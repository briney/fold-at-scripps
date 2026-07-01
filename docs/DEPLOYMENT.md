# Deployment

fold@Scripps runs the backend directly on the host as two systemd services — the
FastAPI app (uvicorn) and the scheduler — while Postgres runs in Docker. The
FastAPI app also serves the built single-page frontend (`frontend/dist`), so no
separate web server is required. The frontend is built once inside a Docker stage
and extracted to the host, so the production host does not need Node installed.

This guide assumes a single host with GPUs, running the model workloads through
the `autobio` CLI.

## Architecture at a glance

- **fold-api** (systemd) — uvicorn serving the API and the SPA on port 8000.
- **fold-scheduler** (systemd) — dispatches queued runs to `autobio`.
- **postgres** (Docker Compose) — the database, on port 5432.
- **TLS / reverse proxy** — provided externally, in front of port 8000.

## Host prerequisites

- **`autobio` CLI** on the `PATH` of the `fold` user (the scheduler invokes it to
  run model containers).
- **Docker** and the **NVIDIA container runtime** — autobio launches GPU model
  containers, and Postgres runs under Docker Compose. Verify GPU access with:

  ```bash
  docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
  ```

- **[`uv`](https://docs.astral.sh/uv/)** installed and on the `PATH` of the `fold`
  user (systemd runs the app via `uv run`).
- A dedicated **`fold`** service user, in the `docker` group and with GPU access,
  owning the repo checkout.
- The repository checked out at **`/opt/fold-at-scripps`**, owned by `fold`:

  ```bash
  sudo useradd --system --create-home --shell /usr/sbin/nologin fold
  sudo usermod -aG docker fold
  sudo git clone https://github.com/briney/fold-at-scripps.git /opt/fold-at-scripps
  sudo chown -R fold:fold /opt/fold-at-scripps
  ```

All commands below are run from `/opt/fold-at-scripps`.

## 1. Start the database

Bring up Postgres (defined in `docker-compose.yml`, Postgres-only):

```bash
make postgres
# or, equivalently:
docker compose up -d postgres
```

The container is marked `restart: unless-stopped`, so it comes back after a host
reboot. Data persists in the `pgdata` named volume.

## 2. Build the frontend

The SPA is built inside a Docker stage and extracted to `frontend/dist`; the host
needs no Node:

```bash
make build-frontend
# expands to:
#   docker build --target dist --output type=local,dest=frontend/dist .
```

This writes `index.html` + `assets/` into `frontend/dist`, which the API serves.

## 3. Configure the environment

Create the config directory and copy the example file, then edit it:

```bash
sudo mkdir -p /etc/fold
sudo cp deploy/fold.env.example /etc/fold/fold.env
sudo chown root:fold /etc/fold/fold.env
sudo chmod 640 /etc/fold/fold.env
sudo -e /etc/fold/fold.env
```

At minimum, set:

- **`FOLD_SECRET_KEY`** — a long random string. Generate one with:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

- **`FOLD_DATABASE_URL`** — the Postgres URL (defaults to the Compose database).
- **`FOLD_STORAGE_ROOT`** — where run inputs/outputs are stored (e.g.
  `/var/lib/fold/data`). Create it and give the `fold` user ownership:

  ```bash
  sudo mkdir -p /var/lib/fold/data
  sudo chown -R fold:fold /var/lib/fold
  ```

Keep `FOLD_SESSION_HTTPS_ONLY=true` in production (see TLS below). Confirm
`FOLD_FRONTEND_DIST` points at the `frontend/dist` you built in step 2.

## 4. Install and enable the services

Install the unit files, reload systemd, and start both services:

```bash
sudo cp deploy/fold-api.service deploy/fold-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fold-api fold-scheduler
```

Database migrations run automatically: the `fold-api` unit applies them via its
`ExecStartPre` (`uv run alembic upgrade head`) on every start. Only the API unit
runs migrations — a single runner, so there is no race with the scheduler.

## 5. Verify

```bash
# API health check
curl localhost:8000/health

# The SPA (served by FastAPI)
curl -I http://localhost:8000/

# Follow logs for both services
journalctl -u fold-api -u fold-scheduler -f
```

Open `http://<host>:8000/` (through your reverse proxy in production) to reach the
web UI.

## TLS / reverse proxy

This app does **not** terminate TLS. Put the institute's intranet reverse proxy
(nginx, Caddy, etc.) in front of port 8000 and terminate TLS there. Because
sessions are served behind that proxy over HTTPS, keep
`FOLD_SESSION_HTTPS_ONLY=true` so the session cookie is marked `Secure`.

## Single scheduler

Only **one** `fold-scheduler` process may run at a time. The scheduler takes a
Postgres advisory lock at startup; a second instance fails to acquire it and exits
immediately. Do not run additional scheduler processes or scale the unit.

## Upgrades

```bash
cd /opt/fold-at-scripps
sudo -u fold git pull
make build-frontend                       # rebuild the SPA
sudo systemctl restart fold-api           # runs migrations, then restarts uvicorn
sudo systemctl restart fold-scheduler
```

## Troubleshooting & operational notes

- **`uv`/`autobio` "not found" at start.** systemd runs services with a minimal
  `PATH` that does **not** include the fold user's login-shell `PATH`. Both units
  set `Environment=PATH=…` including `/home/fold/.local/bin` (uv's default install
  dir). If you installed `uv` elsewhere, or the `autobio` CLI lives in a
  conda/miniforge env, edit the `Environment=PATH=` line in the unit files to
  include those directories (the scheduler in particular must be able to find
  `autobio`). Then `sudo systemctl daemon-reload && sudo systemctl restart …`.

- **Failed starts right after a host reboot are expected.** The units order after
  `docker.service`, not after the Postgres *container* is accepting connections,
  so on boot the API's migration step (and the scheduler's DB access) may fail
  once or twice until Postgres is ready. `Restart=on-failure` (5 s) recovers
  automatically; the units settle within a few seconds. To avoid the noise you
  can add an `ExecStartPre` that waits for `pg_isready`.

- **Restart the scheduler after restarting Postgres.** The single-scheduler
  guarantee uses a *session-scoped* Postgres advisory lock held on one dedicated
  connection. If the Postgres container is restarted while the scheduler is
  running, that connection drops and the server-side lock is released, but the
  running scheduler does not re-acquire it. Run `sudo systemctl restart
  fold-scheduler` after any Postgres restart so it takes the lock again. (On a
  single-node deployment with one scheduler unit this is only a concern if you
  also start a second scheduler during that window.)
