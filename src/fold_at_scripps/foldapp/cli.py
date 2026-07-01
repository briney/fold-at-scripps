"""The ``foldapp`` Typer application."""

from __future__ import annotations

import typer

app = typer.Typer(help="foldapp: fold@Scripps operator CLI (install, deploy, operate, upgrade).")


@app.callback(invoke_without_command=True)
def _cli_callback() -> None:
    """fold@Scripps operator CLI (install, deploy, operate, upgrade)."""


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
