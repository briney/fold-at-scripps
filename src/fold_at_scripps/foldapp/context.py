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
