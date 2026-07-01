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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
