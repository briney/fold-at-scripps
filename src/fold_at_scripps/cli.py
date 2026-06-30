"""Administrative CLI for fold@Scripps (e.g. first-admin bootstrap)."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any

import typer
from sqlalchemy import select

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.db import get_sessionmaker
from fold_at_scripps.models import AllowedEmail, User, UserRole, UserStatus

app = typer.Typer(help="fold@Scripps administrative CLI.")


def _run_async(coro: Coroutine[Any, Any, None]) -> None:
    """Run an async coroutine from a sync context.

    If an event loop is already running (e.g. inside pytest-asyncio), the
    coroutine is executed in a fresh thread so that ``asyncio.run`` can create
    its own loop without conflicting with the caller's loop.
    """
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if in_loop:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            future.result()
    else:
        asyncio.run(coro)


@app.callback()
def _cli_callback() -> None:
    """fold@Scripps administrative CLI."""


async def _create_admin(email: str, password: str, display_name: str) -> None:
    async with get_sessionmaker()() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            typer.echo(f"Error: a user with email {email} already exists.", err=True)
            raise typer.Exit(code=1)
        allowed = await session.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
        if allowed is None:
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
    typer.echo(f"Created admin user {email}.")


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., help="Admin email address."),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Admin password."),
    display_name: str = typer.Option(..., help="Admin display name."),
) -> None:
    """Create an active admin account and allowlist its email."""
    _run_async(_create_admin(email, password, display_name))


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    app()
