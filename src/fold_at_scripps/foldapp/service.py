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
    result = runner(["systemctl", "--user", "is-active", unit], check=False)
    return result.stdout.strip() == "active"


def journal(target: str, *, follow: bool) -> None:
    """Tail journald for the resolved units (streams to the terminal)."""
    units = resolve_units(target)
    args = ["journalctl", "--user"]
    for unit in units:
        args += ["-u", unit]
    if follow:
        args.append("-f")
    os.execvp("journalctl", args)
