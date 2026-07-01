"""First-run install and converge (deploy) orchestration."""

from __future__ import annotations

import rich

from fold_at_scripps.config import get_settings
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
    port = get_settings().api_port
    units.install_units(paths, port=port, dry_run=dry_run)
    service.systemctl("enable", "all", dry_run=dry_run)
    service.systemctl("restart", "all", dry_run=dry_run)

    if first_run:
        linger = preflight.check_linger(paths)
        if linger.status is not preflight.Status.OK:
            rich.print(f"[yellow]note[/] {linger.fix}")
        rich.print("[green]done[/] next: foldapp admin create-admin")
