"""The ``foldapp`` Typer application."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from fold_at_scripps.foldapp import context, envfile, preflight, service
from fold_at_scripps.foldapp import install as install_mod
from fold_at_scripps.foldapp import upgrade as upgrade_mod

app = typer.Typer(help="fold@Scripps operator CLI (install, deploy, operate, upgrade).")
config_app = typer.Typer(help="Configuration (.env) management.")
app.add_typer(config_app, name="config")
db_app = typer.Typer(help="Database backup/restore.")
app.add_typer(db_app, name="db")
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
    result = run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.app_dir, check=False)
    ref = result.stdout.strip()
    console.print(f"fold-at-scripps {pkg_version('fold-at-scripps')} ({ref or 'unknown'})")


@config_app.command("init")
def config_init() -> None:
    """Create ``.env`` from the template with a generated secret (never overwrites)."""
    paths = context.resolve_paths()
    created = envfile.scaffold_env(paths)
    if created:
        console.print(f"[green]created[/] {paths.env_file}")
    else:
        console.print(f"{paths.env_file} exists; kept")


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
def db_dump(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Write a gzipped pg_dump snapshot to the backups directory."""
    from datetime import UTC, datetime

    from fold_at_scripps.foldapp import postgres

    paths = context.resolve_paths()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = postgres.dump(paths, paths.backups_dir / f"manual-{stamp}.sql.gz", dry_run=dry_run)
    console.print(f"[green]dumped[/] {dest}")


@db_app.command("restore")
def db_restore(
    path: str = typer.Argument(..., help="Path to a .sql.gz snapshot."),
    yes: bool = typer.Option(False, "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Restore the database from a snapshot (destructive)."""
    from pathlib import Path

    from fold_at_scripps.foldapp import postgres

    msg = "This overwrites the current database. Continue?"
    if not dry_run and not yes and not typer.confirm(msg):
        raise typer.Abort()
    postgres.restore(context.resolve_paths(), Path(path), dry_run=dry_run)
    console.print("[green]restored[/]")


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
    for _kind, unit in service.UNIT_NAMES.items():
        state = "active" if service.is_active(unit) else "inactive"
        table.add_row(unit, f"[green]{state}[/]" if state == "active" else f"[red]{state}[/]")
    table.add_row("api /health", "ok" if _api_healthy() else "unreachable")
    result = run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.app_dir, check=False)
    table.add_row("git ref", result.stdout.strip() or "unknown")
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


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Show status when run with no subcommand."""
    if ctx.invoked_subcommand is None:
        status()


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
