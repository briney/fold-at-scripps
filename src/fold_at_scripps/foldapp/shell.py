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
