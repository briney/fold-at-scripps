# Deployment

fold@Scripps is operated with the `foldapp` CLI. Everything runs as a single
service user — the app under `systemctl --user`, Postgres in Docker — so
deployment needs (almost) no root.

## Host prerequisites (verified by `foldapp doctor`, not installed)

- `uv` on the service user's PATH.
- Docker + `docker compose` v2; the service user in the `docker` group.
- The NVIDIA container runtime (for GPU model containers).
- The `autobio` CLI on PATH (the scheduler shells out to it).

## First-time install

    git clone https://github.com/briney/fold-at-scripps.git ~/fold-at-scripps
    cd ~/fold-at-scripps
    ./bootstrap.sh
    uv run foldapp doctor          # fix any FAIL rows
    uv run foldapp install         # scaffold .env, migrate, build, enable+start
    uv run foldapp admin create-admin --email you@scripps.edu --display-name "You"

`install` writes `.env` (with a generated `FOLD_SECRET_KEY`), creates
`~/.local/share/fold/{data,backups,state}`, brings up Postgres, migrates, builds
the SPA, and enables the two `systemctl --user` units.

## Boot-start (one optional privileged step)

User services start at login by default. To start them at boot without a login:

    sudo loginctl enable-linger $USER

`foldapp doctor` reports whether lingering is enabled.

## Everyday operations

    foldapp status                 # services + health + git ref
    foldapp logs scheduler -f      # follow logs
    foldapp restart all
    foldapp db dump                # manual snapshot

## Upgrades

    cd ~/fold-at-scripps
    foldapp upgrade                # backup + pull + build + migrate + health-gate
    # or target a ref:
    foldapp upgrade --ref v1.2.0

If the post-upgrade health check fails, the upgrade stops and leaves
`maintenance_mode` ON. Recover with:

    foldapp rollback               # restore previous code ref
    foldapp rollback --db          # also restore the pre-upgrade DB snapshot
                                   # (needed when a migration is the problem)

## TLS / reverse proxy (Caddy)

The app does not terminate TLS. In production, put Caddy in front of the API
port and access the app at `https://fold.scripps.edu`, keeping
`FOLD_SESSION_HTTPS_ONLY=true` in `.env`. The session cookie is `Secure`, which
requires HTTPS — over plain HTTP the browser silently drops it and login fails
(the page just reloads with no error).

A ready-to-adapt config is in [`deploy/Caddyfile.example`](../deploy/Caddyfile.example):

    fold.scripps.edu {
        reverse_proxy 127.0.0.1:8000
    }

Caddy speaks HTTPS to browsers and proxies to the API over localhost, so no app
changes are needed. Intranet-only hosts usually can't use Caddy's default ACME
HTTP-01 challenge; the example documents the alternatives (DNS-01 for trusted
certs on an internal host, an IT-issued/internal-CA cert, or Caddy's internal CA).

**Harden the origin** so the plaintext API can't be reached directly, bypassing
TLS: firewall port 8000 to localhost, or run the API bound to localhost (the
`fold-api` unit runs `serve --port …`, which binds `0.0.0.0` by default — add
`--host 127.0.0.1`). Then only Caddy can reach it.

For **local dev** on a host with no name/cert, set `FOLD_SESSION_HTTPS_ONLY=false`
and use the API over `http://localhost:8000` directly.

## Single scheduler

Exactly one scheduler runs. It holds a Postgres advisory lock; a second exits
immediately. After a Postgres container restart, run `foldapp restart scheduler`
so it re-takes the lock.

## Troubleshooting

- **`uv`/`autobio` not found under systemd:** the rendered units pin
  `Environment=PATH=` to include uv's and autobio's directories (computed at
  install time). If either moved, re-run `foldapp install` to re-render, then
  `foldapp restart all`.
- **Right after boot:** the API/scheduler may restart once or twice until the
  Postgres container is ready; `Restart=on-failure` recovers automatically.
