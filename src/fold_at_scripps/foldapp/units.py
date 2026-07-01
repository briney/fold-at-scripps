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
