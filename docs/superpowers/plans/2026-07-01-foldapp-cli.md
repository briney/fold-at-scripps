# foldapp Operator CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `foldapp`, a single user-scoped operator CLI that installs, deploys, operates, and safely upgrades fold@Scripps on the GPU node, consolidating the existing `fold-admin`/`fold-scheduler` scripts and the `Makefile`.

**Architecture:** A new Typer subpackage `src/fold_at_scripps/foldapp/` whose command bodies **lazily import** app internals (`config`, `db`, `main:app`, scheduler, `system_settings`) for the smart parts and **shell out** (via one `shell.run` helper) for the mechanical parts (`git`, `docker`/`compose`, `uv`, `alembic`, `systemctl --user`, `journalctl`, `pg_dump`). Runtime state lives under the service user's home; supervision is `systemctl --user` units rendered by `foldapp install`.

**Tech Stack:** Python 3.11+, Typer, Rich, stdlib (`subprocess`, `urllib.request`, `gzip`, `socket`, `string.Template`, `secrets`), pytest. Postgres runs in Docker Compose; the frontend builds via the existing Docker `dist` stage.

## Global Constraints

- Python **3.11+**; every non-docstring-only module starts with `from __future__ import annotations`; type hints on all signatures. (Docstring-only `__init__.py` is exempt from the future-annotations rule.)
- Line length **100**; `ruff format` + `ruff check` (rules `E,F,I,UP,B`) must pass. Absolute imports only; `isort` profile black; first-party is `fold_at_scripps`.
- **Never** use `subprocess` with `shell=True`; always pass a list of args. Never call `sudo` from foldapp — print the command instead.
- CLI = **Typer**; formatted output = **Rich**. Every mutating command accepts `--dry-run` and `--yes`.
- Docstrings Google style on public functions/classes.
- Tests: **pytest**, files mirror source at `tests/foldapp/`. Tests needing a live Postgres are marked `@pytest.mark.integration`. No GPU required in CI.
- **Never overwrite an existing `FOLD_SECRET_KEY`.**
- Config in `.env` holds only secrets/infra; operational/policy config stays DB-backed (`SystemSettings`), owned by the admin console.
- New runtime dependency allowed: **`rich`** (used directly). Do **not** add `httpx` to runtime deps — the health-gate uses stdlib `urllib.request`.
- The app's async DB accessors: `get_engine()`, `get_sessionmaker()`, `get_session()`, `dispose_engine()` (in `fold_at_scripps.db`). The ASGI app is `fold_at_scripps.main:app`. The scheduler entry is `fold_at_scripps.scheduler.main:main`. Health path is `GET /health` → `{"status": "ok"}`. Settings singleton via `get_system_settings(session)`; fields include `maintenance_mode: bool`.

---

## File structure

**New package `src/fold_at_scripps/foldapp/`:**
- `__init__.py` — docstring only.
- `shell.py` — `run()` subprocess wrapper (`CommandResult`, `CommandError`, dry-run).
- `context.py` — `FoldappPaths` dataclass + `resolve_paths()` (single source of "where things live").
- `state.py` — `DeployState` + `read_state()`/`write_state()` (`last_deploy.json`).
- `envfile.py` — `.env` scaffolding, secret generation, redaction.
- `units.py` — render + install `systemctl --user` units.
- `preflight.py` — individual checks + `run_checks()`/`has_failures()`.
- `postgres.py` — compose up, `pg_isready` wait, `pg_dump`/restore.
- `frontend.py` — `docker build --target dist` wrapper; `migrate()`.
- `service.py` — `systemctl --user`/`journalctl` wrappers + `is_active()`.
- `run.py` — foreground `serve()` / `scheduler()` entry points (invoked by the units).
- `install.py` / `deploy.py` — first-run + converge orchestrations.
- `upgrade.py` — guarded upgrade + rollback + refresh.
- `cli.py` — the Typer app and `main()`.

**Modified app files:**
- `src/fold_at_scripps/system_settings.py` — add `set_maintenance_mode()`.
- `src/fold_at_scripps/config.py` — add `api_port: int = 8000`.
- `pyproject.toml` — add `foldapp` script; add `rich`; remove `fold-admin`/`fold-scheduler` scripts.
- `deploy/fold.env.example` — user-scoped defaults.

**New ops artifacts:**
- `deploy/systemd/fold-api.service.tmpl`, `deploy/systemd/fold-scheduler.service.tmpl`.
- `bootstrap.sh`.

**Removed:** `src/fold_at_scripps/cli.py`, `deploy/fold-api.service`, `deploy/fold-scheduler.service`, `Makefile`.

**Rewritten:** `docs/DEPLOYMENT.md`.

**Tests:** `tests/foldapp/test_{shell,context,state,envfile,units,preflight,postgres,frontend,service,run,cli,install,deploy,upgrade}.py`.

---

## Task 1: Package scaffold + `shell.run` + installable CLI

**Files:**
- Create: `src/fold_at_scripps/foldapp/__init__.py`, `src/fold_at_scripps/foldapp/shell.py`, `src/fold_at_scripps/foldapp/cli.py`
- Create: `tests/foldapp/__init__.py`, `tests/foldapp/test_shell.py`, `tests/foldapp/test_cli.py`
- Modify: `pyproject.toml` (add `foldapp` script + `rich` dep)

**Interfaces:**
- Produces: `fold_at_scripps.foldapp.shell.run(args: list[str], *, dry_run: bool = False, check: bool = True, capture: bool = True, cwd: Path | None = None, env: Mapping[str, str] | None = None) -> CommandResult`; `CommandResult(args, returncode, stdout, stderr)`; `CommandError(RuntimeError)`; `fold_at_scripps.foldapp.cli.app` (Typer) and `main()`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_shell.py`:
```python
from __future__ import annotations

import sys

import pytest

from fold_at_scripps.foldapp.shell import CommandError, run


def test_run_captures_stdout():
    result = run([sys.executable, "-c", "print('hi')"])
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


def test_run_dry_run_does_not_execute():
    result = run([sys.executable, "-c", "raise SystemExit(3)"], dry_run=True)
    assert result.returncode == 0
    assert result.stdout == ""


def test_run_raises_on_failure_with_stderr_tail():
    with pytest.raises(CommandError) as exc:
        run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); raise SystemExit(1)"])
    assert "boom" in str(exc.value)


def test_run_check_false_returns_nonzero():
    result = run([sys.executable, "-c", "raise SystemExit(2)"], check=False)
    assert result.returncode == 2
```

`tests/foldapp/test_cli.py`:
```python
from __future__ import annotations

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_help_lists_command_group():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "foldapp" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/foldapp/test_shell.py tests/foldapp/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: fold_at_scripps.foldapp`.

- [ ] **Step 3: Create the package + shell helper + CLI stub**

`src/fold_at_scripps/foldapp/__init__.py`:
```python
"""The ``foldapp`` operator CLI (install, deploy, operate, upgrade)."""
```

`src/fold_at_scripps/foldapp/shell.py`:
```python
"""Thin subprocess wrapper: list-args only, dry-run aware, clear errors."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import rich


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a shell-out."""

    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    """A shell-out exited non-zero when ``check=True``."""


def run(
    args: list[str],
    *,
    dry_run: bool = False,
    check: bool = True,
    capture: bool = True,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run ``args`` (never via a shell). On ``dry_run`` print and return success."""
    if dry_run:
        rich.print(f"[dim]+ {' '.join(args)}[/dim]")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")
    proc = subprocess.run(  # noqa: S603 - args is always a list, never shell=True
        args,
        cwd=str(cwd) if cwd else None,
        env=dict(env) if env is not None else None,
        capture_output=capture,
        text=True,
    )
    result = CommandResult(
        args=args,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
    if check and proc.returncode != 0:
        tail = (result.stderr or result.stdout).strip()[-2000:]
        raise CommandError(f"command failed ({proc.returncode}): {' '.join(args)}\n{tail}")
    return result
```

`src/fold_at_scripps/foldapp/cli.py`:
```python
"""The ``foldapp`` Typer application."""

from __future__ import annotations

import typer

app = typer.Typer(help="fold@Scripps operator CLI (install, deploy, operate, upgrade).")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Wire the console script + dependency**

In `pyproject.toml`, replace the `[project.scripts]` block:
```toml
[project.scripts]
foldapp = "fold_at_scripps.foldapp.cli:main"
```
Add `"rich>=13.7",` to `[project].dependencies`. Then:

Run: `uv sync`
Expected: resolves and installs; `foldapp` console script created.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_shell.py tests/foldapp/test_cli.py -v && uv run foldapp --help`
Expected: PASS; `--help` prints the app help.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/foldapp tests/foldapp pyproject.toml uv.lock
git commit -m "feat(foldapp): package scaffold, shell helper, CLI entry"
```

---

## Task 2: `context.py` — path/layout resolution

**Files:**
- Create: `src/fold_at_scripps/foldapp/context.py`, `tests/foldapp/test_context.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FoldappPaths` (frozen dataclass) with fields `app_dir, env_file, state_dir, data_dir, backups_dir, deploy_state_file, user_unit_dir, user: str` and properties `api_unit -> Path`, `scheduler_unit -> Path`. `resolve_paths(*, app_dir: Path | None = None, home: Path | None = None, env: Mapping[str, str] | None = None, user: str | None = None) -> FoldappPaths`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_context.py`:
```python
from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths


def test_resolve_paths_defaults_under_home(tmp_path: Path):
    app = tmp_path / "app"
    home = tmp_path / "home"
    paths = resolve_paths(app_dir=app, home=home, env={}, user="fold")
    assert paths.app_dir == app
    assert paths.env_file == app / ".env"
    assert paths.state_dir == home / ".local" / "share" / "fold"
    assert paths.data_dir == paths.state_dir / "data"
    assert paths.backups_dir == paths.state_dir / "backups"
    assert paths.deploy_state_file == paths.state_dir / "state" / "last_deploy.json"
    assert paths.user_unit_dir == home / ".config" / "systemd" / "user"
    assert paths.user == "fold"


def test_resolve_paths_honors_state_dir_override(tmp_path: Path):
    paths = resolve_paths(
        app_dir=tmp_path, home=tmp_path, env={"FOLDAPP_STATE_DIR": str(tmp_path / "s")}, user="x"
    )
    assert paths.state_dir == tmp_path / "s"


def test_unit_path_properties(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="x")
    assert paths.api_unit.name == "fold-api.service"
    assert paths.scheduler_unit.name == "fold-scheduler.service"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_context.py -v`
Expected: FAIL — `ImportError` for `resolve_paths`.

- [ ] **Step 3: Implement**

`src/fold_at_scripps/foldapp/context.py`:
```python
"""Resolve where foldapp keeps everything (single source of layout truth)."""

from __future__ import annotations

import getpass
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FoldappPaths:
    """Absolute locations foldapp reads and writes."""

    app_dir: Path
    env_file: Path
    state_dir: Path
    data_dir: Path
    backups_dir: Path
    deploy_state_file: Path
    user_unit_dir: Path
    user: str

    @property
    def api_unit(self) -> Path:
        """Path to the rendered fold-api user unit."""
        return self.user_unit_dir / "fold-api.service"

    @property
    def scheduler_unit(self) -> Path:
        """Path to the rendered fold-scheduler user unit."""
        return self.user_unit_dir / "fold-scheduler.service"


def _find_app_dir(env: Mapping[str, str]) -> Path:
    """Repo root: env override, else nearest ancestor of CWD with pyproject.toml."""
    override = env.get("FOLDAPP_APP_DIR")
    if override:
        return Path(override).resolve()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return here


def resolve_paths(
    *,
    app_dir: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    user: str | None = None,
) -> FoldappPaths:
    """Compute :class:`FoldappPaths`, honoring env overrides for testability."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    app_dir = _find_app_dir(env) if app_dir is None else app_dir
    state_override = env.get("FOLDAPP_STATE_DIR")
    state_dir = Path(state_override) if state_override else home / ".local" / "share" / "fold"
    return FoldappPaths(
        app_dir=app_dir,
        env_file=app_dir / ".env",
        state_dir=state_dir,
        data_dir=state_dir / "data",
        backups_dir=state_dir / "backups",
        deploy_state_file=state_dir / "state" / "last_deploy.json",
        user_unit_dir=home / ".config" / "systemd" / "user",
        user=user or getpass.getuser(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foldapp/test_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/context.py tests/foldapp/test_context.py
git commit -m "feat(foldapp): path/layout resolution (FoldappPaths)"
```

---

## Task 3: `state.py` — deploy-state file

**Files:**
- Create: `src/fold_at_scripps/foldapp/state.py`, `tests/foldapp/test_state.py`

**Interfaces:**
- Produces: `DeployState(prev_ref: str | None, new_ref: str | None, backup_path: str | None, timestamp: str)`; `read_state(path: Path) -> DeployState | None`; `write_state(path: Path, state: DeployState) -> None` (creates parent dirs).

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_state.py`:
```python
from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.state import DeployState, read_state, write_state


def test_read_missing_returns_none(tmp_path: Path):
    assert read_state(tmp_path / "nope.json") is None


def test_write_then_read_roundtrip(tmp_path: Path):
    path = tmp_path / "state" / "last_deploy.json"
    state = DeployState(prev_ref="aaa", new_ref="bbb", backup_path="/b/x.sql.gz", timestamp="t0")
    write_state(path, state)
    assert path.is_file()
    assert read_state(path) == state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_state.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`src/fold_at_scripps/foldapp/state.py`:
```python
"""Persist the last-deploy record used by upgrade/rollback."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeployState:
    """Snapshot of the last upgrade, for rollback."""

    prev_ref: str | None
    new_ref: str | None
    backup_path: str | None
    timestamp: str


def read_state(path: Path) -> DeployState | None:
    """Load the deploy state, or ``None`` if it does not exist."""
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return DeployState(**data)


def write_state(path: Path, state: DeployState) -> None:
    """Write the deploy state as JSON, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foldapp/test_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/state.py tests/foldapp/test_state.py
git commit -m "feat(foldapp): deploy-state file for rollback"
```

---

## Task 4: `envfile.py` — `.env` scaffolding, secret, redaction

**Files:**
- Create: `src/fold_at_scripps/foldapp/envfile.py`, `tests/foldapp/test_envfile.py`

**Interfaces:**
- Consumes: `FoldappPaths` (Task 2).
- Produces: `generate_secret_key() -> str`; `scaffold_env(paths: FoldappPaths, *, dry_run: bool = False) -> bool` (True if created, False if it already existed — **never overwrites**); `redact_settings(values: Mapping[str, object]) -> dict[str, object]` (masks `secret_key` and the password in `database_url`).

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_envfile.py`:
```python
from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.envfile import generate_secret_key, redact_settings, scaffold_env


def test_generate_secret_key_is_long_and_unique():
    a, b = generate_secret_key(), generate_secret_key()
    assert a != b
    assert len(a) >= 40


def test_scaffold_creates_env_with_generated_secret(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    created = scaffold_env(paths)
    assert created is True
    text = paths.env_file.read_text()
    assert "FOLD_SECRET_KEY=" in text
    assert "CHANGE-ME" not in text
    assert str(paths.data_dir) in text


def test_scaffold_never_overwrites(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    paths.env_file.write_text("FOLD_SECRET_KEY=keepme\n")
    created = scaffold_env(paths)
    assert created is False
    assert paths.env_file.read_text() == "FOLD_SECRET_KEY=keepme\n"


def test_redact_masks_secret_and_password():
    out = redact_settings(
        {
            "secret_key": "supersecret",
            "database_url": "postgresql+asyncpg://fold:pw@localhost/db",
            "gpu_count": 8,
        }
    )
    assert out["secret_key"] == "***"
    assert "pw" not in out["database_url"]
    assert out["gpu_count"] == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_envfile.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`src/fold_at_scripps/foldapp/envfile.py`:
```python
"""Scaffold and redact the ``.env`` (secrets/infra only)."""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from typing import Any

import rich

from fold_at_scripps.foldapp.context import FoldappPaths

_TEMPLATE = """\
# fold@Scripps environment — secrets/infra only. NEVER commit a real secret.
FOLD_SECRET_KEY={secret}
FOLD_DATABASE_URL=postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps
FOLD_STORAGE_ROOT={data_dir}
FOLD_FRONTEND_DIST={app_dir}/frontend/dist
FOLD_SESSION_HTTPS_ONLY=true
FOLD_GPU_COUNT=8
FOLD_LOG_LEVEL=INFO
FOLD_MAX_UPLOAD_BYTES=104857600
"""


def generate_secret_key() -> str:
    """Return a fresh URL-safe secret suitable for ``FOLD_SECRET_KEY``."""
    return secrets.token_urlsafe(48)


def scaffold_env(paths: FoldappPaths, *, dry_run: bool = False) -> bool:
    """Create ``.env`` with a generated secret. Return False if it already exists."""
    if paths.env_file.exists():
        return False
    content = _TEMPLATE.format(
        secret=generate_secret_key(), data_dir=paths.data_dir, app_dir=paths.app_dir
    )
    if dry_run:
        rich.print(f"[dim]+ write {paths.env_file}[/dim]")
        return True
    paths.env_file.parent.mkdir(parents=True, exist_ok=True)
    paths.env_file.write_text(content)
    paths.env_file.chmod(0o600)
    return True


def redact_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with the secret key and any DB password masked."""
    out = dict(values)
    if "secret_key" in out:
        out["secret_key"] = "***"
    if "database_url" in out and isinstance(out["database_url"], str):
        out["database_url"] = re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", out["database_url"])
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foldapp/test_envfile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/envfile.py tests/foldapp/test_envfile.py
git commit -m "feat(foldapp): .env scaffolding, secret gen, redaction"
```

---

## Task 5: `units.py` + templates — systemd user units

**Files:**
- Create: `deploy/systemd/fold-api.service.tmpl`, `deploy/systemd/fold-scheduler.service.tmpl`
- Create: `src/fold_at_scripps/foldapp/units.py`, `tests/foldapp/test_units.py`

**Interfaces:**
- Consumes: `FoldappPaths` (Task 2), `shell.run` (Task 1).
- Produces: `render_unit(kind: str, paths: FoldappPaths, *, port: int = 8000, uv_path: str | None = None, autobio_dir: str | None = None) -> str` (kind is `"api"` or `"scheduler"`); `install_units(paths: FoldappPaths, *, port: int = 8000, dry_run: bool = False) -> None` (writes both + `systemctl --user daemon-reload`).

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_units.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.units import render_unit


def test_render_api_unit_has_expected_fields(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path / "app", home=tmp_path, env={}, user="fold")
    text = render_unit("api", paths, port=8000, uv_path="/opt/uv/uv", autobio_dir="/opt/autobio/bin")
    assert f"WorkingDirectory={paths.app_dir}" in text
    assert f"EnvironmentFile={paths.env_file}" in text
    assert "/opt/uv/uv run alembic upgrade head" in text
    assert "/opt/uv/uv run foldapp serve --port 8000" in text
    assert "/opt/autobio/bin" in text  # autobio dir folded into PATH
    assert "WantedBy=default.target" in text


def test_render_scheduler_unit_has_no_migration_and_runs_scheduler(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path / "app", home=tmp_path, env={}, user="fold")
    text = render_unit("scheduler", paths, uv_path="/opt/uv/uv", autobio_dir="/opt/autobio/bin")
    assert "foldapp scheduler" in text
    assert "alembic upgrade head" not in text


def test_render_unknown_kind_raises(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with pytest.raises(ValueError):
        render_unit("bogus", paths)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_units.py -v`
Expected: FAIL — module/templates missing.

- [ ] **Step 3: Create the templates**

`deploy/systemd/fold-api.service.tmpl`:
```ini
[Unit]
Description=fold@Scripps API (uvicorn)

[Service]
Type=simple
WorkingDirectory=$app_dir
EnvironmentFile=$env_file
Environment=PATH=$path
ExecStartPre=$uv run alembic upgrade head
ExecStart=$uv run foldapp serve --port $port
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`deploy/systemd/fold-scheduler.service.tmpl`:
```ini
[Unit]
Description=fold@Scripps scheduler

[Service]
Type=simple
WorkingDirectory=$app_dir
EnvironmentFile=$env_file
Environment=PATH=$path
ExecStart=$uv run foldapp scheduler
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

- [ ] **Step 4: Implement `units.py`**

`src/fold_at_scripps/foldapp/units.py`:
```python
"""Render + install the systemctl --user unit files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from string import Template

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run

# Templates live in the repo's deploy/ dir, resolved from this module's location
# (src/fold_at_scripps/foldapp/units.py -> parents[3] is the repo root). This is
# independent of paths.app_dir so unit tests that stub app_dir still find them.
_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "deploy" / "systemd"
_KINDS = {"api": "fold-api.service", "scheduler": "fold-scheduler.service"}
_BASE_PATH_DIRS = ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]


def _build_path(uv_path: str, autobio_dir: str | None) -> str:
    """Compose a PATH that includes uv's and autobio's dirs (fixes the Plan 10 footgun)."""
    dirs: list[str] = [str(Path(uv_path).parent)]
    if autobio_dir:
        dirs.append(autobio_dir)
    dirs.extend(_BASE_PATH_DIRS)
    seen: dict[str, None] = {}
    for d in dirs:
        seen.setdefault(d, None)
    return os.pathsep.join(seen)


def render_unit(
    kind: str,
    paths: FoldappPaths,
    *,
    port: int = 8000,
    uv_path: str | None = None,
    autobio_dir: str | None = None,
) -> str:
    """Render a user unit for ``kind`` ('api' | 'scheduler')."""
    if kind not in _KINDS:
        raise ValueError(f"unknown unit kind: {kind}")
    uv_path = uv_path or shutil.which("uv") or "uv"
    if autobio_dir is None:
        found = shutil.which("autobio")
        autobio_dir = str(Path(found).parent) if found else None
    template = Template((_TEMPLATE_DIR / f"{_KINDS[kind]}.tmpl").read_text())
    return template.substitute(
        app_dir=paths.app_dir,
        env_file=paths.env_file,
        path=_build_path(uv_path, autobio_dir),
        uv=uv_path,
        port=port,
    )


def install_units(paths: FoldappPaths, *, port: int = 8000, dry_run: bool = False) -> None:
    """Write both unit files and reload the user systemd manager."""
    if not dry_run:
        paths.user_unit_dir.mkdir(parents=True, exist_ok=True)
        paths.api_unit.write_text(render_unit("api", paths, port=port))
        paths.scheduler_unit.write_text(render_unit("scheduler", paths))
    run(["systemctl", "--user", "daemon-reload"], dry_run=dry_run)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_units.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deploy/systemd src/fold_at_scripps/foldapp/units.py tests/foldapp/test_units.py
git commit -m "feat(foldapp): render + install systemctl --user units"
```

---

## Task 6: `preflight.py` — checks + `doctor` engine

**Files:**
- Create: `src/fold_at_scripps/foldapp/preflight.py`, `tests/foldapp/test_preflight.py`

**Interfaces:**
- Consumes: `FoldappPaths` (Task 2).
- Produces: `Status` (StrEnum: `OK`, `WARN`, `FAIL`); `CheckResult(name: str, status: Status, detail: str, fix: str | None)`; individual check functions taking `(paths, *, which=shutil.which, runner=run)` and returning `CheckResult`; `run_checks(paths: FoldappPaths, *, context: str = "deploy") -> list[CheckResult]`; `has_failures(results: Sequence[CheckResult]) -> bool`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_preflight.py`:
```python
from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.preflight import Status, check_autobio, check_uv, has_failures


def _paths(tmp_path: Path):
    return resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")


def test_check_uv_ok_when_present(tmp_path: Path):
    result = check_uv(_paths(tmp_path), which=lambda name: "/opt/uv/uv")
    assert result.status is Status.OK


def test_check_uv_fail_when_missing(tmp_path: Path):
    result = check_uv(_paths(tmp_path), which=lambda name: None)
    assert result.status is Status.FAIL
    assert result.fix


def test_check_autobio_warns_in_dev_context(tmp_path: Path):
    result = check_autobio(_paths(tmp_path), which=lambda name: None, context="dev")
    assert result.status is Status.WARN


def test_check_autobio_fails_in_deploy_context(tmp_path: Path):
    result = check_autobio(_paths(tmp_path), which=lambda name: None, context="deploy")
    assert result.status is Status.FAIL


def test_has_failures():
    from fold_at_scripps.foldapp.preflight import CheckResult

    ok = CheckResult("a", Status.OK, "", None)
    warn = CheckResult("b", Status.WARN, "", None)
    fail = CheckResult("c", Status.FAIL, "", None)
    assert has_failures([ok, warn]) is False
    assert has_failures([ok, fail]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_preflight.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`src/fold_at_scripps/foldapp/preflight.py`:
```python
"""Environment preflight checks powering ``foldapp doctor``."""

from __future__ import annotations

import shutil
import socket
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run

Which = Callable[[str], str | None]


class Status(StrEnum):
    """Outcome of a single check."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    """One preflight check outcome."""

    name: str
    status: Status
    detail: str
    fix: str | None


def check_python(paths: FoldappPaths, *, which: Which = shutil.which) -> CheckResult:
    """Python must be >= 3.11."""
    ok = sys.version_info >= (3, 11)
    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    return CheckResult(
        "python", Status.OK if ok else Status.FAIL, f"Python {v}", None if ok else "Use Python 3.11+"
    )


def check_uv(paths: FoldappPaths, *, which: Which = shutil.which) -> CheckResult:
    """uv must be on PATH."""
    found = which("uv")
    return CheckResult(
        "uv",
        Status.OK if found else Status.FAIL,
        found or "not found",
        None if found else "Install uv: https://docs.astral.sh/uv/",
    )


def check_docker(paths: FoldappPaths, *, which: Which = shutil.which, runner=run) -> CheckResult:
    """Docker daemon must be reachable."""
    if not which("docker"):
        return CheckResult("docker", Status.FAIL, "docker not found", "Install Docker")
    result = runner(["docker", "info"], check=False)
    ok = result.returncode == 0
    return CheckResult(
        "docker", Status.OK if ok else Status.FAIL, "daemon reachable" if ok else "daemon unreachable",
        None if ok else "Start Docker and ensure your user can reach the socket",
    )


def check_autobio(
    paths: FoldappPaths, *, which: Which = shutil.which, context: str = "deploy"
) -> CheckResult:
    """autobio CLI must be on PATH for the scheduler (WARN in dev)."""
    found = which("autobio")
    if found:
        return CheckResult("autobio", Status.OK, found, None)
    status = Status.WARN if context == "dev" else Status.FAIL
    return CheckResult("autobio", status, "not found", "Put the autobio CLI on PATH")


def check_gpu(paths: FoldappPaths, *, which: Which = shutil.which, runner=run) -> CheckResult:
    """GPU access via the NVIDIA container runtime (WARN if absent)."""
    if not which("docker"):
        return CheckResult("gpu", Status.WARN, "docker missing", "Install Docker + NVIDIA runtime")
    result = runner(
        ["docker", "run", "--rm", "--gpus", "all", "nvidia/cuda:12.4.0-base-ubuntu22.04", "nvidia-smi"],
        check=False,
    )
    ok = result.returncode == 0
    return CheckResult(
        "gpu", Status.OK if ok else Status.WARN, "GPUs visible" if ok else "no GPU access",
        None if ok else "Install the NVIDIA container runtime (dev boxes can ignore)",
    )


def check_port_free(paths: FoldappPaths, port: int) -> CheckResult:
    """A required port must be bindable (or already ours)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        free = sock.connect_ex(("127.0.0.1", port)) != 0
    return CheckResult(
        f"port:{port}", Status.OK if free else Status.WARN,
        "free" if free else "in use", None if free else "Ensure it is our own service",
    )


def check_env(paths: FoldappPaths) -> CheckResult:
    """.env must exist with a non-default secret."""
    if not paths.env_file.is_file():
        return CheckResult("env", Status.FAIL, "no .env", "Run: foldapp config init")
    text = paths.env_file.read_text()
    bad = "dev-insecure-secret-change-me" in text or "CHANGE-ME" in text
    return CheckResult(
        "env", Status.FAIL if bad else Status.OK,
        "dev secret in use" if bad else "present",
        "Set a real FOLD_SECRET_KEY" if bad else None,
    )


def check_linger(paths: FoldappPaths, *, runner=run) -> CheckResult:
    """Lingering enables boot-start of user services (WARN if off)."""
    result = runner(["loginctl", "show-user", paths.user, "--property=Linger"], check=False)
    on = "Linger=yes" in result.stdout
    return CheckResult(
        "linger", Status.OK if on else Status.WARN, "enabled" if on else "disabled",
        None if on else f"Enable boot-start: sudo loginctl enable-linger {paths.user}",
    )


def run_checks(paths: FoldappPaths, *, context: str = "deploy") -> list[CheckResult]:
    """Run every check for the given context ('deploy' | 'dev')."""
    results = [
        check_python(paths),
        check_uv(paths),
        check_docker(paths),
        check_autobio(paths, context=context),
        check_gpu(paths),
        check_port_free(paths, 8000),
        check_port_free(paths, 5432),
        check_env(paths),
    ]
    if context == "deploy":
        results.append(check_linger(paths))
    return results


def has_failures(results: Sequence[CheckResult]) -> bool:
    """True if any result is FAIL."""
    return any(r.status is Status.FAIL for r in results)
```

Note: `check_docker`/`check_gpu`/`check_linger` call `run(..., check=False)` so a
non-zero command never raises — they classify the return code instead.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_preflight.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/preflight.py tests/foldapp/test_preflight.py
git commit -m "feat(foldapp): preflight checks engine"
```

---

## Task 7: `postgres.py` + `set_maintenance_mode`

**Files:**
- Create: `src/fold_at_scripps/foldapp/postgres.py`, `tests/foldapp/test_postgres.py`
- Modify: `src/fold_at_scripps/system_settings.py` (add `set_maintenance_mode`)
- Modify: `tests/foldapp/test_postgres.py` (integration test for maintenance toggle)

**Interfaces:**
- Consumes: `FoldappPaths` (Task 2), `shell.run` (Task 1).
- Produces: `compose_up(paths, *, dry_run=False) -> None`; `wait_ready(paths, *, timeout=30.0, dry_run=False, runner=run, sleep=time.sleep) -> bool`; `dump(paths, dest: Path, *, dry_run=False) -> Path`; `restore(paths, src: Path, *, dry_run=False) -> None`. In `system_settings.py`: `async def set_maintenance_mode(session, enabled: bool) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_postgres.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.postgres import wait_ready
from fold_at_scripps.foldapp.shell import CommandResult


def _paths(tmp_path: Path):
    return resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")


def test_wait_ready_true_when_pg_isready_succeeds(tmp_path: Path):
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=0, stdout="accepting", stderr="")

    assert wait_ready(_paths(tmp_path), runner=fake_runner, sleep=lambda s: None) is True


def test_wait_ready_false_on_timeout(tmp_path: Path):
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=1, stdout="", stderr="no")

    assert wait_ready(_paths(tmp_path), timeout=0.05, runner=fake_runner, sleep=lambda s: None) is False


def test_dump_is_dry_run_noop(tmp_path: Path):
    from fold_at_scripps.foldapp.postgres import dump

    dest = tmp_path / "b.sql.gz"
    out = dump(_paths(tmp_path), dest, dry_run=True)
    assert out == dest
    assert not dest.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_postgres.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `postgres.py`**

`src/fold_at_scripps/foldapp/postgres.py`:
```python
"""Postgres lifecycle helpers (compose up, readiness, dump/restore)."""

from __future__ import annotations

import gzip
import subprocess
import time
from pathlib import Path

import rich

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run

_SERVICE = "postgres"
_DB_USER = "fold"
_DB_NAME = "fold_at_scripps"


def compose_up(paths: FoldappPaths, *, dry_run: bool = False) -> None:
    """Start the Postgres container via docker compose."""
    run(["docker", "compose", "up", "-d", _SERVICE], cwd=paths.app_dir, dry_run=dry_run)


def wait_ready(
    paths: FoldappPaths,
    *,
    timeout: float = 30.0,
    dry_run: bool = False,
    runner=run,
    sleep=time.sleep,
) -> bool:
    """Poll ``pg_isready`` inside the container until ready or ``timeout``."""
    if dry_run:
        return True
    deadline = time.monotonic() + timeout
    while True:
        result = runner(
            ["docker", "compose", "exec", "-T", _SERVICE, "pg_isready", "-U", _DB_USER, "-d", _DB_NAME],
            cwd=paths.app_dir,
            check=False,
        )
        if result.returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(1.0)


def dump(paths: FoldappPaths, dest: Path, *, dry_run: bool = False) -> Path:
    """Write a gzipped pg_dump to ``dest`` and return the path."""
    if dry_run:
        rich.print(f"[dim]+ pg_dump -> {dest}[/dim]")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = run(
        ["docker", "compose", "exec", "-T", _SERVICE, "pg_dump", "-U", _DB_USER, _DB_NAME],
        cwd=paths.app_dir,
    )
    with gzip.open(dest, "wt", encoding="utf-8") as fh:
        fh.write(result.stdout)
    return dest


def restore(paths: FoldappPaths, src: Path, *, dry_run: bool = False) -> None:
    """Restore a gzipped pg_dump from ``src`` (destructive).

    The shared ``run`` helper does not stream stdin, so this pipes the SQL to
    ``psql`` via ``subprocess.run`` directly (still list args, never a shell).
    """
    if dry_run:
        rich.print(f"[dim]+ psql < {src}[/dim]")
        return
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        sql = fh.read()
    proc = subprocess.run(  # noqa: S603 - list args, no shell
        ["docker", "compose", "exec", "-T", _SERVICE, "psql", "-U", _DB_USER, "-d", _DB_NAME],
        cwd=str(paths.app_dir),
        input=sql,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"restore failed: {proc.stderr.strip()[-2000:]}")
```

- [ ] **Step 4: Add `set_maintenance_mode` to `system_settings.py`**

Append to `src/fold_at_scripps/system_settings.py`:
```python
async def set_maintenance_mode(session: AsyncSession, enabled: bool) -> None:
    """Toggle the maintenance flag on the singleton and commit (CLI operator action)."""
    settings = await get_system_settings(session)
    settings.maintenance_mode = enabled
    await session.commit()
```

- [ ] **Step 5: Add the integration test for the toggle**

Append to `tests/foldapp/test_postgres.py` (the `db_session` fixture and the
`integration` marker/auto-skip already exist in `tests/conftest.py`; async tests
work via `asyncio_mode = auto`):
```python
@pytest.mark.integration
async def test_set_maintenance_mode_roundtrip(db_session):
    from fold_at_scripps.system_settings import get_system_settings, set_maintenance_mode

    await set_maintenance_mode(db_session, True)
    assert (await get_system_settings(db_session)).maintenance_mode is True
    await set_maintenance_mode(db_session, False)
    assert (await get_system_settings(db_session)).maintenance_mode is False
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_postgres.py -v -m "not integration"`
Expected: unit tests PASS. Then, with Postgres up: `uv run pytest tests/foldapp/test_postgres.py -v -m integration` → PASS.

- [ ] **Step 7: Commit**

```bash
git add src/fold_at_scripps/foldapp/postgres.py src/fold_at_scripps/system_settings.py tests/foldapp/test_postgres.py
git commit -m "feat(foldapp): postgres helpers + set_maintenance_mode"
```

---

## Task 8: `frontend.py` — build + `migrate`

**Files:**
- Create: `src/fold_at_scripps/foldapp/frontend.py`, `tests/foldapp/test_frontend.py`

**Interfaces:**
- Consumes: `FoldappPaths` (Task 2), `shell.run` (Task 1).
- Produces: `build_frontend(paths, *, dry_run=False, runner=run) -> None` (docker build → `frontend/dist`); `migrate(paths, *, dry_run=False, runner=run) -> None` (`uv run alembic upgrade head`).

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_frontend.py`:
```python
from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.frontend import build_frontend, migrate
from fold_at_scripps.foldapp.shell import CommandResult


def _paths(tmp_path: Path):
    return resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")


def test_build_frontend_invokes_docker_dist_stage(tmp_path: Path):
    calls = []

    def fake_runner(args, **kw):
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    build_frontend(_paths(tmp_path), runner=fake_runner)
    assert calls and calls[0][0] == "docker" and "--target" in calls[0] and "dist" in calls[0]


def test_migrate_invokes_alembic(tmp_path: Path):
    calls = []

    def fake_runner(args, **kw):
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    migrate(_paths(tmp_path), runner=fake_runner)
    assert ["uv", "run", "alembic", "upgrade", "head"] == calls[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_frontend.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`src/fold_at_scripps/foldapp/frontend.py`:
```python
"""Frontend build and DB migration shell-outs."""

from __future__ import annotations

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run


def build_frontend(paths: FoldappPaths, *, dry_run: bool = False, runner=run) -> None:
    """Build the SPA via the Docker ``dist`` stage into ``frontend/dist``."""
    runner(
        [
            "docker", "build", "--target", "dist",
            "--output", "type=local,dest=frontend/dist", ".",
        ],
        cwd=paths.app_dir,
        dry_run=dry_run,
    )


def migrate(paths: FoldappPaths, *, dry_run: bool = False, runner=run) -> None:
    """Apply Alembic migrations to head."""
    runner(["uv", "run", "alembic", "upgrade", "head"], cwd=paths.app_dir, dry_run=dry_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_frontend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/frontend.py tests/foldapp/test_frontend.py
git commit -m "feat(foldapp): frontend build + migrate helpers"
```

---

## Task 9: `service.py` + `run.py` + `config.api_port`

**Files:**
- Create: `src/fold_at_scripps/foldapp/service.py`, `src/fold_at_scripps/foldapp/run.py`
- Create: `tests/foldapp/test_service.py`, `tests/foldapp/test_run.py`
- Modify: `src/fold_at_scripps/config.py` (add `api_port: int = 8000`)

**Interfaces:**
- Consumes: `shell.run` (Task 1).
- Produces: in `service.py`: `UNIT_NAMES: dict[str, str]` (`{"api": "fold-api", "scheduler": "fold-scheduler"}`); `resolve_units(target: str) -> list[str]` (`target` in `api|scheduler|all`); `systemctl(action: str, target: str, *, dry_run=False) -> None`; `is_active(unit: str, *, runner=run) -> bool`; `journal(target: str, *, follow: bool) -> None`. In `run.py`: `serve(host: str = "0.0.0.0", port: int | None = None) -> None`; `scheduler() -> None`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_service.py`:
```python
from __future__ import annotations

import pytest

from fold_at_scripps.foldapp.service import is_active, resolve_units
from fold_at_scripps.foldapp.shell import CommandResult


def test_resolve_units_all():
    assert resolve_units("all") == ["fold-api", "fold-scheduler"]


def test_resolve_units_single():
    assert resolve_units("scheduler") == ["fold-scheduler"]


def test_resolve_units_invalid():
    with pytest.raises(ValueError):
        resolve_units("bogus")


def test_is_active_true():
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=0, stdout="active\n", stderr="")

    assert is_active("fold-api", runner=fake_runner) is True


def test_is_active_false():
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=3, stdout="inactive\n", stderr="")

    assert is_active("fold-api", runner=fake_runner) is False
```

`tests/foldapp/test_run.py`:
```python
from __future__ import annotations

from unittest import mock

from fold_at_scripps.foldapp import run as run_module


def test_serve_calls_uvicorn_with_app_and_port():
    with mock.patch("uvicorn.run") as uv:
        run_module.serve(port=9001)
    args, kwargs = uv.call_args
    assert args[0] == "fold_at_scripps.main:app"
    assert kwargs["port"] == 9001


def test_scheduler_delegates_to_scheduler_main():
    with mock.patch("fold_at_scripps.scheduler.main.main") as m:
        run_module.scheduler()
    m.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_service.py tests/foldapp/test_run.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement `service.py`**

`src/fold_at_scripps/foldapp/service.py`:
```python
"""Wrappers over ``systemctl --user`` and ``journalctl --user``."""

from __future__ import annotations

import os

from fold_at_scripps.foldapp.shell import run

UNIT_NAMES: dict[str, str] = {"api": "fold-api", "scheduler": "fold-scheduler"}


def resolve_units(target: str) -> list[str]:
    """Map 'api' | 'scheduler' | 'all' to unit names."""
    if target == "all":
        return [UNIT_NAMES["api"], UNIT_NAMES["scheduler"]]
    if target in UNIT_NAMES:
        return [UNIT_NAMES[target]]
    raise ValueError(f"unknown target: {target}")


def systemctl(action: str, target: str, *, dry_run: bool = False) -> None:
    """Run ``systemctl --user <action>`` for the resolved units."""
    run(["systemctl", "--user", action, *resolve_units(target)], dry_run=dry_run)


def is_active(unit: str, *, runner=run) -> bool:
    """True if ``systemctl --user is-active <unit>`` reports active."""
    return runner(["systemctl", "--user", "is-active", unit], check=False).stdout.strip() == "active"


def journal(target: str, *, follow: bool) -> None:
    """Tail journald for the resolved units (streams to the terminal)."""
    units = resolve_units(target)
    args = ["journalctl", "--user"]
    for unit in units:
        args += ["-u", unit]
    if follow:
        args.append("-f")
    os.execvp("journalctl", args)
```
(Using `execvp` for `logs -f` hands the terminal to journalctl directly, so `Ctrl-C` behaves. This is intentionally not routed through `shell.run`.)

- [ ] **Step 4: Implement `run.py` + config**

Add to `src/fold_at_scripps/config.py` (after `frontend_dist`):
```python
    api_port: int = 8000
```

`src/fold_at_scripps/foldapp/run.py`:
```python
"""Foreground entry points invoked by the systemd user units."""

from __future__ import annotations

import uvicorn

from fold_at_scripps.config import get_settings
from fold_at_scripps.logging_config import configure_logging


def serve(host: str = "0.0.0.0", port: int | None = None) -> None:
    """Run the API with uvicorn in the foreground."""
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run("fold_at_scripps.main:app", host=host, port=port or settings.api_port)


def scheduler() -> None:
    """Run the scheduler daemon in the foreground."""
    from fold_at_scripps.scheduler.main import main as scheduler_main

    scheduler_main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_service.py tests/foldapp/test_run.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/foldapp/service.py src/fold_at_scripps/foldapp/run.py src/fold_at_scripps/config.py tests/foldapp/test_service.py tests/foldapp/test_run.py
git commit -m "feat(foldapp): systemctl/journal wrappers + serve/scheduler entries"
```

---

## Task 10: CLI — `doctor`, `version`, `config`, `serve`, `scheduler`

**Files:**
- Modify: `src/fold_at_scripps/foldapp/cli.py`
- Modify: `tests/foldapp/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2–9. All command bodies **lazily import** their dependencies (keep `--help` and `doctor` free of FastAPI/DB imports where possible).
- Produces: Typer commands `doctor`, `version`, `serve`, `scheduler`, and a `config` sub-app with `init` and `show`.

- [ ] **Step 1: Write the failing test**

Append to `tests/foldapp/test_cli.py`:
```python
def test_doctor_runs_and_reports(monkeypatch, tmp_path):
    from fold_at_scripps.foldapp import preflight

    fake = [preflight.CheckResult("uv", preflight.Status.OK, "ok", None)]
    monkeypatch.setattr(preflight, "run_checks", lambda paths, context="deploy": fake)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "uv" in result.output


def test_doctor_exit_nonzero_on_failure(monkeypatch):
    from fold_at_scripps.foldapp import preflight

    fake = [preflight.CheckResult("uv", preflight.Status.FAIL, "missing", "install uv")]
    monkeypatch.setattr(preflight, "run_checks", lambda paths, context="deploy": fake)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1


def test_config_init_creates_env(tmp_path, monkeypatch):
    from fold_at_scripps.foldapp import context

    paths = context.resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    monkeypatch.setattr(context, "resolve_paths", lambda **kw: paths)
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert paths.env_file.is_file()


def test_version_smoke():
    assert runner.invoke(app, ["version"]).exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_cli.py -v`
Expected: FAIL — commands not defined.

- [ ] **Step 3: Implement the commands**

Replace `src/fold_at_scripps/foldapp/cli.py`:
```python
"""The ``foldapp`` Typer application."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from fold_at_scripps.foldapp import context, envfile, preflight

app = typer.Typer(help="fold@Scripps operator CLI (install, deploy, operate, upgrade).")
config_app = typer.Typer(help="Configuration (.env) management.")
app.add_typer(config_app, name="config")
console = Console()

_STATUS_STYLE = {"OK": "green", "WARN": "yellow", "FAIL": "red"}


@app.command()
def doctor(dev: bool = typer.Option(False, "--dev", help="Use the dev check profile.")) -> None:
    """Run environment preflight checks; exit non-zero on any FAIL."""
    paths = context.resolve_paths()
    results = preflight.run_checks(paths, context="dev" if dev else "deploy")
    table = Table("Check", "Status", "Detail", "Fix")
    for r in results:
        table.add_row(r.name, f"[{_STATUS_STYLE[r.status]}]{r.status}[/]", r.detail, r.fix or "")
    console.print(table)
    if preflight.has_failures(results):
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the app version and current git ref."""
    from importlib.metadata import version as pkg_version

    from fold_at_scripps.foldapp.shell import run

    paths = context.resolve_paths()
    ref = run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.app_dir, check=False).stdout.strip()
    console.print(f"fold-at-scripps {pkg_version('fold-at-scripps')} ({ref or 'unknown'})")


@config_app.command("init")
def config_init() -> None:
    """Create ``.env`` from the template with a generated secret (never overwrites)."""
    paths = context.resolve_paths()
    created = envfile.scaffold_env(paths)
    console.print(f"[green]created[/] {paths.env_file}" if created else f"{paths.env_file} exists; kept")


@config_app.command("show")
def config_show() -> None:
    """Print resolved settings with secrets redacted."""
    from fold_at_scripps.config import get_settings

    values = envfile.redact_settings(get_settings().model_dump())
    for key, val in values.items():
        console.print(f"{key} = {val}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
) -> None:
    """Run the API in the foreground (invoked by the fold-api unit)."""
    from fold_at_scripps.foldapp.run import serve as _serve

    _serve(host=host, port=port)


@app.command()
def scheduler() -> None:
    """Run the scheduler in the foreground (invoked by the fold-scheduler unit)."""
    from fold_at_scripps.foldapp.run import scheduler as _scheduler

    _scheduler()


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_cli.py -v && uv run foldapp doctor --dev`
Expected: PASS; `doctor --dev` prints a table.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/cli.py tests/foldapp/test_cli.py
git commit -m "feat(foldapp): doctor, version, config, serve, scheduler commands"
```

---

## Task 11: `install` + `deploy` orchestration

**Files:**
- Create: `src/fold_at_scripps/foldapp/install.py`, `tests/foldapp/test_install.py`
- Modify: `src/fold_at_scripps/foldapp/cli.py` (add `install`, `deploy`)

**Interfaces:**
- Consumes: `preflight`, `envfile`, `postgres`, `frontend`, `units`, `service`, `context`.
- Produces: `deploy(paths, *, dry_run=False, first_run=False) -> None` (converge: ensure state dirs, Postgres up+ready, migrate, build frontend, install+enable+restart units; on `first_run` also scaffold `.env` and check linger). `install()` is `deploy(first_run=True)`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_install.py`:
```python
from __future__ import annotations

from pathlib import Path
from unittest import mock

from fold_at_scripps.foldapp import install as install_mod
from fold_at_scripps.foldapp.context import resolve_paths


def test_deploy_dry_run_orders_steps(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with (
        mock.patch.object(install_mod.postgres, "compose_up") as compose_up,
        mock.patch.object(install_mod.postgres, "wait_ready", return_value=True) as wait_ready,
        mock.patch.object(install_mod.frontend, "migrate") as migrate,
        mock.patch.object(install_mod.frontend, "build_frontend") as build,
        mock.patch.object(install_mod.units, "install_units") as install_units,
        mock.patch.object(install_mod.service, "systemctl") as systemctl,
    ):
        install_mod.deploy(paths, dry_run=True)
    compose_up.assert_called_once()
    wait_ready.assert_called_once()
    migrate.assert_called_once()
    build.assert_called_once()
    install_units.assert_called_once()
    assert systemctl.call_count >= 1


def test_deploy_raises_when_postgres_never_ready(tmp_path: Path):
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with (
        mock.patch.object(install_mod.postgres, "compose_up"),
        mock.patch.object(install_mod.postgres, "wait_ready", return_value=False),
    ):
        try:
            install_mod.deploy(paths)
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "postgres" in str(exc).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_install.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `install.py`**

`src/fold_at_scripps/foldapp/install.py`:
```python
"""First-run install and converge (deploy) orchestration."""

from __future__ import annotations

import rich

from fold_at_scripps.foldapp import envfile, frontend, postgres, preflight, service, units
from fold_at_scripps.foldapp.context import FoldappPaths


def deploy(paths: FoldappPaths, *, dry_run: bool = False, first_run: bool = False) -> None:
    """Bring the running system in line with the current checkout."""
    if first_run:
        for directory in (paths.data_dir, paths.backups_dir, paths.deploy_state_file.parent):
            if not dry_run:
                directory.mkdir(parents=True, exist_ok=True)
        if envfile.scaffold_env(paths, dry_run=dry_run):
            rich.print(f"[green]created[/] {paths.env_file}")

    postgres.compose_up(paths, dry_run=dry_run)
    if not postgres.wait_ready(paths, dry_run=dry_run):
        raise RuntimeError("postgres did not become ready in time")
    frontend.migrate(paths, dry_run=dry_run)
    frontend.build_frontend(paths, dry_run=dry_run)
    units.install_units(paths, dry_run=dry_run)
    service.systemctl("enable", "all", dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)

    if first_run:
        linger = preflight.check_linger(paths)
        if linger.status is not preflight.Status.OK:
            rich.print(f"[yellow]note[/] {linger.fix}")
        rich.print("[green]done[/] next: foldapp admin create-admin")
```

- [ ] **Step 4: Wire the CLI commands**

Add to `src/fold_at_scripps/foldapp/cli.py` (import `from fold_at_scripps.foldapp import install as install_mod` at top):
```python
@app.command()
def install(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """First-time setup: scaffold, migrate, build, enable + start services."""
    paths = context.resolve_paths()
    results = preflight.run_checks(paths)
    if preflight.has_failures(results):
        console.print("[red]preflight failed[/]; run `foldapp doctor` for details")
        raise typer.Exit(code=1)
    install_mod.deploy(paths, dry_run=dry_run, first_run=True)


@app.command()
def deploy(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Converge the running system to the current checkout."""
    install_mod.deploy(context.resolve_paths(), dry_run=dry_run)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_install.py tests/foldapp/test_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/foldapp/install.py src/fold_at_scripps/foldapp/cli.py tests/foldapp/test_install.py
git commit -m "feat(foldapp): install + deploy orchestration"
```

---

## Task 12: Operations — `status`, `start/stop/restart`, `logs`

**Files:**
- Modify: `src/fold_at_scripps/foldapp/cli.py`
- Create: `tests/foldapp/test_ops.py`

**Interfaces:**
- Consumes: `service` (Task 9), `context`, `shell.run`.
- Produces: CLI commands `status`, `start`, `stop`, `restart`, `logs`. `status` is also the default command (bare `foldapp`).

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_ops.py`:
```python
from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_status_reports_unit_activity(monkeypatch):
    from fold_at_scripps.foldapp import service

    monkeypatch.setattr(service, "is_active", lambda unit, **kw: True)
    with mock.patch("fold_at_scripps.foldapp.cli._api_healthy", return_value=True):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "fold-api" in result.output


def test_restart_invokes_systemctl(monkeypatch):
    calls = []
    from fold_at_scripps.foldapp import service

    monkeypatch.setattr(service, "systemctl", lambda action, target, **kw: calls.append((action, target)))
    result = runner.invoke(app, ["restart", "all"])
    assert result.exit_code == 0
    assert ("restart", "all") in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_ops.py -v`
Expected: FAIL — commands not defined.

- [ ] **Step 3: Implement**

Add to `src/fold_at_scripps/foldapp/cli.py` (add `from fold_at_scripps.foldapp import service` to imports):
```python
def _api_healthy(port: int = 8000, timeout: float = 2.0) -> bool:
    """True if GET /health returns 200 (stdlib only)."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@app.command()
def status() -> None:
    """Show service, health, and version status."""
    from fold_at_scripps.foldapp.shell import run

    paths = context.resolve_paths()
    table = Table("Component", "State")
    for kind, unit in service.UNIT_NAMES.items():
        state = "active" if service.is_active(unit) else "inactive"
        table.add_row(unit, f"[green]{state}[/]" if state == "active" else f"[red]{state}[/]")
    table.add_row("api /health", "ok" if _api_healthy() else "unreachable")
    ref = run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.app_dir, check=False).stdout.strip()
    table.add_row("git ref", ref or "unknown")
    console.print(table)


@app.command()
def start(target: str = typer.Argument("all")) -> None:
    """Start api|scheduler|all."""
    service.systemctl("start", target)


@app.command()
def stop(target: str = typer.Argument("all")) -> None:
    """Stop api|scheduler|all."""
    service.systemctl("stop", target)


@app.command()
def restart(target: str = typer.Argument("all")) -> None:
    """Restart api|scheduler|all."""
    service.systemctl("restart", target)


@app.command()
def logs(
    target: str = typer.Argument("all"),
    follow: bool = typer.Option(False, "-f", "--follow"),
) -> None:
    """Tail journald logs for api|scheduler|all."""
    service.journal(target, follow=follow)
```

Make `status` the default command by setting `no_args_is_help=False` on the Typer app and adding a callback that invokes status when no subcommand is given:
```python
@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Show status when run with no subcommand."""
    if ctx.invoked_subcommand is None:
        status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_ops.py tests/foldapp/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/cli.py tests/foldapp/test_ops.py
git commit -m "feat(foldapp): status, start/stop/restart, logs"
```

---

## Task 13: Guarded `upgrade` + `rollback` + `refresh` + `db`

**Files:**
- Create: `src/fold_at_scripps/foldapp/upgrade.py`, `tests/foldapp/test_upgrade.py`
- Modify: `src/fold_at_scripps/foldapp/cli.py` (add `upgrade`, `rollback`, `refresh`, `db` sub-app)

**Interfaces:**
- Consumes: `postgres` (dump/restore), `frontend` (build/migrate), `service`, `state`, `shell.run`, `context`, and the async `set_maintenance_mode` + `get_sessionmaker`.
- Produces: `upgrade(paths, *, ref: str | None = None, dry_run=False) -> None`; `rollback(paths, *, restore_db: bool = False, dry_run=False) -> None`; `refresh(paths, *, dry_run=False) -> None`; helper `set_maintenance(enabled: bool, *, dry_run=False) -> None` (opens a session and toggles), and `wait_healthy(port=8000, timeout=60.0) -> bool`.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_upgrade.py`:
```python
from __future__ import annotations

from unittest import mock

import pytest

from fold_at_scripps.foldapp import upgrade as up
from fold_at_scripps.foldapp.context import resolve_paths


@pytest.fixture
def stub_upgrade(monkeypatch):
    """Stub every external effect of upgrade; return the set_maintenance recorder."""
    maintenance = mock.Mock()
    monkeypatch.setattr(up, "set_maintenance", maintenance)
    monkeypatch.setattr(up, "_current_ref", lambda paths: "old")
    monkeypatch.setattr(up, "_git_pull", lambda paths, ref, *, dry_run: ("old", "new"))
    monkeypatch.setattr(up, "_uv_sync", lambda paths, *, dry_run: None)
    monkeypatch.setattr(up, "_rotate_backups", lambda paths, keep=5: None)
    monkeypatch.setattr(up.postgres, "dump", lambda paths, dest, *, dry_run=False: dest)
    monkeypatch.setattr(up.frontend, "build_frontend", lambda paths, *, dry_run=False: None)
    monkeypatch.setattr(up.frontend, "migrate", lambda paths, *, dry_run=False: None)
    monkeypatch.setattr(up.service, "systemctl", lambda action, target, *, dry_run=False: None)
    return maintenance


def test_upgrade_success_toggles_maintenance_off(tmp_path, stub_upgrade, monkeypatch):
    monkeypatch.setattr(up, "wait_healthy", lambda **kw: True)
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    up.upgrade(paths)
    calls = [c.args for c in stub_upgrade.call_args_list]
    assert calls[0] == (True,)
    assert calls[-1] == (False,)


def test_upgrade_failed_healthcheck_leaves_maintenance_on(tmp_path, stub_upgrade, monkeypatch):
    monkeypatch.setattr(up, "wait_healthy", lambda **kw: False)
    paths = resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    with pytest.raises(RuntimeError):
        up.upgrade(paths)
    calls = [c.args for c in stub_upgrade.call_args_list]
    assert (True,) in calls
    assert (False,) not in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_upgrade.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `upgrade.py`**

`src/fold_at_scripps/foldapp/upgrade.py`:
```python
"""Guarded upgrade, rollback, and refresh flows."""

from __future__ import annotations

import asyncio
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

import rich

from fold_at_scripps.foldapp import frontend, postgres, service
from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run
from fold_at_scripps.foldapp.state import DeployState, read_state, write_state


def _current_ref(paths: FoldappPaths) -> str:
    """Current git HEAD (full sha)."""
    return run(["git", "rev-parse", "HEAD"], cwd=paths.app_dir).stdout.strip()


def _git_pull(paths: FoldappPaths, ref: str | None, *, dry_run: bool) -> tuple[str, str]:
    """Update the checkout; return (old_ref, new_ref)."""
    old = _current_ref(paths)
    if ref:
        run(["git", "fetch", "origin"], cwd=paths.app_dir, dry_run=dry_run)
        run(["git", "checkout", ref], cwd=paths.app_dir, dry_run=dry_run)
    else:
        run(["git", "pull", "--ff-only"], cwd=paths.app_dir, dry_run=dry_run)
    new = old if dry_run else _current_ref(paths)
    return old, new


def _uv_sync(paths: FoldappPaths, *, dry_run: bool) -> None:
    """Sync Python dependencies."""
    run(["uv", "sync"], cwd=paths.app_dir, dry_run=dry_run)


def set_maintenance(enabled: bool, *, dry_run: bool = False) -> None:
    """Toggle DB-backed maintenance_mode (no-op on dry-run)."""
    if dry_run:
        rich.print(f"[dim]+ maintenance_mode = {enabled}[/dim]")
        return

    async def _toggle() -> None:
        from fold_at_scripps.db import dispose_engine, get_sessionmaker
        from fold_at_scripps.system_settings import set_maintenance_mode

        try:
            async with get_sessionmaker()() as session:
                await set_maintenance_mode(session, enabled)
        finally:
            await dispose_engine()

    asyncio.run(_toggle())


def wait_healthy(port: int = 8000, timeout: float = 60.0) -> bool:
    """Poll GET /health until 200 or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2.0)
    return False


def _rotate_backups(paths: FoldappPaths, keep: int = 5) -> None:
    """Delete all but the newest ``keep`` pre-upgrade snapshots."""
    snaps = sorted(paths.backups_dir.glob("pre-upgrade-*.sql.gz"))
    for old in snaps[:-keep]:
        old.unlink()


def upgrade(paths: FoldappPaths, *, ref: str | None = None, dry_run: bool = False) -> None:
    """Backed-up, health-gated upgrade. On failure, leave maintenance ON and stop."""
    old_ref = _current_ref(paths)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = paths.backups_dir / f"pre-upgrade-{stamp}.sql.gz"
    set_maintenance(True, dry_run=dry_run)
    postgres.dump(paths, backup, dry_run=dry_run)
    if not dry_run:
        _rotate_backups(paths)
    old_ref, new_ref = _git_pull(paths, ref, dry_run=dry_run)
    write_state(
        paths.deploy_state_file,
        DeployState(prev_ref=old_ref, new_ref=new_ref, backup_path=str(backup), timestamp=stamp),
    )
    _uv_sync(paths, dry_run=dry_run)
    frontend.build_frontend(paths, dry_run=dry_run)
    frontend.migrate(paths, dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)
    if not dry_run and not wait_healthy():
        raise RuntimeError(
            "post-upgrade health check failed; maintenance_mode left ON. "
            "Recover with: foldapp rollback (add --db if a migration is at fault)."
        )
    set_maintenance(False, dry_run=dry_run)
    rich.print(f"[green]upgraded[/] {old_ref[:8]} -> {new_ref[:8]} (backup {backup})")


def refresh(paths: FoldappPaths, *, dry_run: bool = False) -> None:
    """Light re-apply: rebuild frontend, sync catalog, restart (no pull/migrate)."""
    frontend.build_frontend(paths, dry_run=dry_run)
    run(["uv", "run", "foldapp", "catalog", "sync"], cwd=paths.app_dir, dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)


def rollback(paths: FoldappPaths, *, restore_db: bool = False, dry_run: bool = False) -> None:
    """Restore the previous git ref (and optionally the DB snapshot)."""
    st = read_state(paths.deploy_state_file)
    if st is None or st.prev_ref is None:
        raise RuntimeError("no recorded deploy state to roll back to")
    set_maintenance(True, dry_run=dry_run)
    run(["git", "checkout", st.prev_ref], cwd=paths.app_dir, dry_run=dry_run)
    _uv_sync(paths, dry_run=dry_run)
    frontend.build_frontend(paths, dry_run=dry_run)
    if restore_db and st.backup_path:
        from pathlib import Path

        postgres.restore(paths, Path(st.backup_path), dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)
    if not dry_run and not wait_healthy():
        raise RuntimeError("rollback health check failed; maintenance_mode left ON")
    set_maintenance(False, dry_run=dry_run)
    rich.print(f"[green]rolled back[/] to {st.prev_ref[:8]}")
```

- [ ] **Step 4: Wire CLI commands**

Add to `cli.py` (imports `from fold_at_scripps.foldapp import upgrade as upgrade_mod`; add a `db` sub-app):
```python
db_app = typer.Typer(help="Database backup/restore.")
app.add_typer(db_app, name="db")


@app.command()
def upgrade(
    ref: str = typer.Option(None, "--ref", help="Git ref to deploy (default: pull latest)."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Guarded upgrade: backup + health-gate; failures stop with maintenance ON."""
    upgrade_mod.upgrade(context.resolve_paths(), ref=ref, dry_run=dry_run)


@app.command()
def refresh(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Rebuild frontend + sync catalog + restart (no pull/migrate)."""
    upgrade_mod.refresh(context.resolve_paths(), dry_run=dry_run)


@app.command()
def rollback(
    db: bool = typer.Option(False, "--db", help="Also restore the pre-upgrade DB snapshot."),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Restore the previous git ref (and optionally the DB snapshot)."""
    if db and not yes and not typer.confirm("Restoring the DB snapshot is destructive. Continue?"):
        raise typer.Abort()
    upgrade_mod.rollback(context.resolve_paths(), restore_db=db, dry_run=dry_run)


@db_app.command("dump")
def db_dump() -> None:
    """Write a gzipped pg_dump snapshot to the backups directory."""
    from datetime import UTC, datetime

    from fold_at_scripps.foldapp import postgres

    paths = context.resolve_paths()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = postgres.dump(paths, paths.backups_dir / f"manual-{stamp}.sql.gz")
    console.print(f"[green]dumped[/] {dest}")


@db_app.command("restore")
def db_restore(
    path: str = typer.Argument(..., help="Path to a .sql.gz snapshot."),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Restore the database from a snapshot (destructive)."""
    from pathlib import Path

    from fold_at_scripps.foldapp import postgres

    if not yes and not typer.confirm("This overwrites the current database. Continue?"):
        raise typer.Abort()
    postgres.restore(context.resolve_paths(), Path(path))
    console.print("[green]restored[/]")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_upgrade.py tests/foldapp/test_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fold_at_scripps/foldapp/upgrade.py src/fold_at_scripps/foldapp/cli.py tests/foldapp/test_upgrade.py
git commit -m "feat(foldapp): guarded upgrade, rollback, refresh, db dump/restore"
```

---

## Task 14: `dev up` + `uninstall`

**Files:**
- Modify: `src/fold_at_scripps/foldapp/cli.py`
- Create: `tests/foldapp/test_dev_uninstall.py`

**Interfaces:**
- Consumes: `postgres`, `service`, `units`, `context`, `shell.run`.
- Produces: a `dev` sub-app with `up`; an `uninstall` command.

- [ ] **Step 1: Write the failing test**

`tests/foldapp/test_dev_uninstall.py`:
```python
from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from fold_at_scripps.foldapp.cli import app

runner = CliRunner()


def test_uninstall_disables_units(monkeypatch, tmp_path):
    from fold_at_scripps.foldapp import context, service

    paths = context.resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")
    paths.user_unit_dir.mkdir(parents=True)
    paths.api_unit.write_text("x")
    paths.scheduler_unit.write_text("x")
    monkeypatch.setattr(context, "resolve_paths", lambda **kw: paths)
    calls = []
    monkeypatch.setattr(service, "systemctl", lambda action, target, **kw: calls.append(action))
    result = runner.invoke(app, ["uninstall", "--yes"])
    assert result.exit_code == 0
    assert "disable" in calls
    assert not paths.api_unit.exists()


def test_dev_up_starts_postgres_and_processes(monkeypatch):
    from fold_at_scripps.foldapp import postgres

    monkeypatch.setattr(postgres, "compose_up", lambda paths, **kw: None)
    monkeypatch.setattr(postgres, "wait_ready", lambda paths, **kw: True)
    with mock.patch("fold_at_scripps.foldapp.cli._run_dev_processes") as procs:
        result = runner.invoke(app, ["dev", "up"])
    assert result.exit_code == 0
    procs.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_dev_uninstall.py -v`
Expected: FAIL — commands not defined.

- [ ] **Step 3: Implement**

Add to `cli.py`:
```python
dev_app = typer.Typer(help="Local development stack.")
app.add_typer(dev_app, name="dev")


def _run_dev_processes(paths) -> None:
    """Start uvicorn --reload and the Vite dev server; wait until interrupted."""
    import subprocess

    procs = [
        subprocess.Popen(  # noqa: S603 - list args
            ["uv", "run", "uvicorn", "fold_at_scripps.main:app", "--reload", "--port", "8000"],
            cwd=str(paths.app_dir),
        ),
        subprocess.Popen(["npm", "run", "dev"], cwd=str(paths.app_dir / "frontend")),  # noqa: S603
    ]
    try:
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        for proc in procs:
            proc.terminate()


@dev_app.command("up")
def dev_up() -> None:
    """Foreground dev stack: Postgres + uvicorn --reload + Vite (Ctrl-C to stop)."""
    from fold_at_scripps.foldapp import postgres

    paths = context.resolve_paths()
    postgres.compose_up(paths)
    if not postgres.wait_ready(paths):
        raise typer.Exit(code=1)
    console.print("[green]dev[/] api :8000  vite :5173  (Ctrl-C to stop)")
    _run_dev_processes(paths)


@app.command()
def uninstall(
    purge: bool = typer.Option(False, "--purge", help="Also delete data/state."),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Disable + remove the user units (keeps data unless --purge)."""
    import shutil

    paths = context.resolve_paths()
    if not yes and not typer.confirm("Disable and remove fold services?"):
        raise typer.Abort()
    service.systemctl("stop", "all")
    service.systemctl("disable", "all")
    for unit in (paths.api_unit, paths.scheduler_unit):
        unit.unlink(missing_ok=True)
    from fold_at_scripps.foldapp.shell import run

    run(["systemctl", "--user", "daemon-reload"], check=False)
    if purge and (yes or typer.confirm(f"Delete {paths.state_dir}?")):
        shutil.rmtree(paths.state_dir, ignore_errors=True)
    console.print("[green]uninstalled[/]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp/test_dev_uninstall.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fold_at_scripps/foldapp/cli.py tests/foldapp/test_dev_uninstall.py
git commit -m "feat(foldapp): dev up + uninstall"
```

---

## Task 15: Fold in admin/catalog; remove old scripts

**Files:**
- Modify: `src/fold_at_scripps/foldapp/cli.py` (add `admin create-admin`, `catalog sync`)
- Delete: `src/fold_at_scripps/cli.py`
- Modify: `pyproject.toml` (remove `fold-admin`/`fold-scheduler` scripts — already replaced in Task 1; verify)
- Modify: `tests/foldapp/test_cli.py`
- Check: any tests referencing `fold_at_scripps.cli` — migrate them.

**Interfaces:**
- Consumes: `hash_password`, `AutobioToolSource`, `sync_catalog`, `get_sessionmaker`, `dispose_engine`, ORM models (same imports the old `cli.py` used).
- Produces: `admin` sub-app with `create-admin`; `catalog` sub-app with `sync`.

- [ ] **Step 1: Write the failing test**

Append to `tests/foldapp/test_cli.py`:
```python
def test_admin_and_catalog_help():
    assert runner.invoke(app, ["admin", "--help"]).exit_code == 0
    assert runner.invoke(app, ["catalog", "--help"]).exit_code == 0
    assert "create-admin" in runner.invoke(app, ["admin", "--help"]).output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foldapp/test_cli.py::test_admin_and_catalog_help -v`
Expected: FAIL — sub-apps not defined.

- [ ] **Step 3: Port the commands and delete the old CLI**

Add to `cli.py`:
```python
admin_app = typer.Typer(help="Administrative actions.")
catalog_app = typer.Typer(help="Tool catalog.")
app.add_typer(admin_app, name="admin")
app.add_typer(catalog_app, name="catalog")


@admin_app.command("create-admin")
def admin_create_admin(
    email: str = typer.Option(..., help="Admin email address."),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Admin password."),
    display_name: str = typer.Option(..., help="Admin display name."),
) -> None:
    """Create an active admin account and allowlist its email."""
    import asyncio

    from sqlalchemy import select

    from fold_at_scripps.auth.passwords import hash_password
    from fold_at_scripps.db import dispose_engine, get_sessionmaker
    from fold_at_scripps.models import AllowedEmail, User, UserRole, UserStatus

    async def _create() -> None:
        try:
            async with get_sessionmaker()() as session:
                if await session.scalar(select(User).where(User.email == email)):
                    console.print(f"[red]error[/] user {email} already exists")
                    raise typer.Exit(code=1)
                if not await session.scalar(select(AllowedEmail).where(AllowedEmail.email == email)):
                    session.add(AllowedEmail(email=email))
                session.add(
                    User(
                        email=email,
                        display_name=display_name,
                        hashed_password=hash_password(password),
                        role=UserRole.ADMIN,
                        status=UserStatus.ACTIVE,
                    )
                )
                await session.commit()
            console.print(f"[green]created admin[/] {email}")
        finally:
            await dispose_engine()

    asyncio.run(_create())


@catalog_app.command("sync")
def catalog_sync() -> None:
    """Sync the tool catalog from autobio."""
    import asyncio

    from fold_at_scripps.catalog.autobio_source import AutobioToolSource
    from fold_at_scripps.catalog.service import sync_catalog
    from fold_at_scripps.db import dispose_engine, get_sessionmaker

    async def _sync() -> None:
        try:
            async with get_sessionmaker()() as session:
                result = await sync_catalog(session, AutobioToolSource())
            console.print(f"[green]synced[/] {result.added} added, {result.updated} updated")
        finally:
            await dispose_engine()

    asyncio.run(_sync())
```

Delete the old CLI:
```bash
git rm src/fold_at_scripps/cli.py
```

Migrate the existing `tests/test_cli.py` (it imports the now-removed
`fold_at_scripps.cli` and calls the old command names). Rewrite it to target the
`foldapp` sub-apps — replace its top import and command args:
```python
from fold_at_scripps.foldapp.cli import app  # was: fold_at_scripps.cli
```
and change the invocations: `["create-admin", ...]` → `["admin", "create-admin", ...]`
and `["sync-catalog"]` → `["catalog", "sync"]`. The three test bodies, the
`pytestmark = pytest.mark.integration`, the `db_session` fixture usage, and the
`shutil.which("autobio")` skip on the catalog test all stay as-is.

Then search for any other stragglers:
```bash
grep -rn "fold_at_scripps.cli\|fold-admin\|fold-scheduler" src tests deploy docs
```
Confirm `pyproject.toml [project.scripts]` contains only `foldapp` (set in Task 1).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/foldapp -v && uv run pytest -q`
Expected: PASS; no references to the removed module remain.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(foldapp): fold admin/catalog in; remove fold-admin/fold-scheduler scripts"
```

---

## Task 16: Retire Makefile + system units; update env example

**Files:**
- Delete: `Makefile`, `deploy/fold-api.service`, `deploy/fold-scheduler.service`
- Modify: `deploy/fold.env.example` (user-scoped defaults + `FOLD_API_PORT`)

**Interfaces:** none (ops artifacts only).

- [ ] **Step 1: Remove the retired artifacts**

```bash
git rm Makefile deploy/fold-api.service deploy/fold-scheduler.service
```

- [ ] **Step 2: Update `deploy/fold.env.example`**

Replace its contents:
```bash
# fold@Scripps environment — copy to <APP_DIR>/.env and fill in.
# `foldapp config init` generates this automatically with a fresh secret.
# NEVER commit a real secret. Secrets/infra only — policy config lives in the DB.

FOLD_SECRET_KEY=CHANGE-ME-to-a-long-random-secret
FOLD_DATABASE_URL=postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps
FOLD_STORAGE_ROOT=/home/fold/.local/share/fold/data
FOLD_FRONTEND_DIST=/home/fold/fold-at-scripps/frontend/dist

FOLD_SESSION_HTTPS_ONLY=true
FOLD_GPU_COUNT=8
FOLD_API_PORT=8000
FOLD_LOG_LEVEL=INFO
FOLD_MAX_UPLOAD_BYTES=104857600
# FOLD_SCHEDULER_POLL_INTERVAL=2.0
# FOLD_DEBUG=false
```

- [ ] **Step 3: Verify nothing references the removed files**

Run: `grep -rn "Makefile\|deploy/fold-api.service\|deploy/fold-scheduler.service\|make build-frontend\|make postgres\|make migrate" . --exclude-dir=.git`
Expected: only matches in `docs/DEPLOYMENT.md` (rewritten next) and this plan/spec.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(foldapp): retire Makefile + system units; user-scoped env example"
```

---

## Task 17: Rewrite `docs/DEPLOYMENT.md` + add `bootstrap.sh`

**Files:**
- Create: `bootstrap.sh`
- Rewrite: `docs/DEPLOYMENT.md`

**Interfaces:** none (docs + bootstrap).

- [ ] **Step 1: Add `bootstrap.sh`**

`bootstrap.sh`:
```bash
#!/usr/bin/env bash
# Bootstrap fold@Scripps: sync deps, then hand off to foldapp.
# Usage: ./bootstrap.sh   (run from the repo checkout)
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH. Install it: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv sync
echo
echo "Dependencies synced. Next:"
echo "  uv run foldapp doctor      # verify prerequisites"
echo "  uv run foldapp install     # first-time setup"
echo "  uv run foldapp admin create-admin --email you@scripps.edu --display-name 'You'"
```
Then: `chmod +x bootstrap.sh`.

- [ ] **Step 2: Rewrite `docs/DEPLOYMENT.md`**

Write a guide covering, in order:
```markdown
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

## TLS / reverse proxy

The app does not terminate TLS. Put the intranet reverse proxy in front of the
API port (default 8000) and keep `FOLD_SESSION_HTTPS_ONLY=true`.

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
```

- [ ] **Step 3: Verify**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add bootstrap.sh docs/DEPLOYMENT.md
git commit -m "docs(foldapp): user-scoped DEPLOYMENT guide + bootstrap.sh"
```

---

## Final verification

- [ ] `uv run pytest -q` (unit + `-m "not integration"`) green.
- [ ] With Postgres up: `uv run pytest -q -m integration` green.
- [ ] `uv run ruff check . && uv run ruff format --check .` clean.
- [ ] `uv run foldapp --help` shows all groups; `uv run foldapp doctor --dev` runs.
- [ ] `uv run foldapp install --dry-run` prints the full ordered plan without executing.
- [ ] `grep -rn "fold-admin\|fold-scheduler\|Makefile" src tests` returns nothing (docs excepted).
- [ ] The Alembic no-drift test still passes.

## Self-review notes (coverage map)

- Spec §Architecture/packaging → Tasks 1, 10. §Layout → Tasks 2, 4, 5. §Command
  surface → Tasks 10–15. §Preflight → Task 6, 10. §Guarded upgrade/rollback →
  Task 13. §Config handling → Tasks 4, 9, 10. §Retire/replace → Tasks 15, 16, 17.
  §Error handling/idempotency (dry-run, no shell=True, no sudo) → Tasks 1, 5, 7,
  11, 13. §Testing → every task; integration marker in Task 7.
- The PATH footgun fix (compute `Environment=PATH=` from `which`) lands in Task 5.
- The cold-boot Postgres race fix (`wait_ready`/`pg_isready`) lands in Tasks 7, 11.
- The advisory-lock-after-Postgres-restart caveat is documented (Task 17); the
  automated lease-watchdog remains deferred per the spec.
