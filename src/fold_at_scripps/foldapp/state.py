"""Persist the last-deploy record used by upgrade/rollback."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeployState:
    """Snapshot of the last upgrade, for rollback."""

    prev_ref: str | None
    new_ref: str | None
    backup_path: str | None
    timestamp: str


def read_state(path: Path) -> DeployState | None:
    """Load the deploy state, or ``None`` if it does not exist."""
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return DeployState(**data)


def write_state(path: Path, state: DeployState) -> None:
    """Write the deploy state as JSON, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
