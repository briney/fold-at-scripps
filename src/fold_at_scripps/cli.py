"""Administrative CLI for fold@Scripps (e.g. first-admin bootstrap)."""

from __future__ import annotations

import asyncio

import typer
from sqlalchemy import select

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.catalog.autobio_source import AutobioToolSource
from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.db import dispose_engine, get_sessionmaker
from fold_at_scripps.models import AllowedEmail, User, UserRole, UserStatus

app = typer.Typer(help="fold@Scripps administrative CLI.")


@app.callback()
def _cli_callback() -> None:
    """fold@Scripps administrative CLI."""


async def _create_admin(email: str, password: str, display_name: str) -> None:
    try:
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
    finally:
        await dispose_engine()


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., help="Admin email address."),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Admin password."),
    display_name: str = typer.Option(..., help="Admin display name."),
) -> None:
    """Create an active admin account and allowlist its email."""
    asyncio.run(_create_admin(email, password, display_name))


async def _sync_catalog() -> None:
    """Run the autobio-backed catalog sync and print the result."""
    source = AutobioToolSource()
    try:
        async with get_sessionmaker()() as session:
            result = await sync_catalog(session, source)
        typer.echo(f"Catalog synced: {result.added} added, {result.updated} updated.")
    finally:
        await dispose_engine()


@app.command("sync-catalog")
def sync_catalog_command() -> None:
    """Sync the tool catalog from autobio."""
    asyncio.run(_sync_catalog())


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    app()
