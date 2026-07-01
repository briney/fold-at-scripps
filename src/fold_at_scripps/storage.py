"""Run artifact storage: a Storage boundary and a local-filesystem implementation."""

from __future__ import annotations

import json
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fold_at_scripps.config import get_settings


@dataclass
class StoredFile:
    """A file discovered in a run's output directory."""

    name: str
    relative_path: str
    size_bytes: int
    content_type: str | None


class Storage(Protocol):
    """Per-run file storage for inputs, the tool config, and outputs."""

    def create_run_dir(self, run_id: uuid.UUID) -> None: ...
    def write_config(self, run_id: uuid.UUID, config: dict[str, Any]) -> str: ...
    def config_path(self, run_id: uuid.UUID) -> Path: ...
    def input_path(self, run_id: uuid.UUID, filename: str) -> Path: ...
    def outputs_dir(self, run_id: uuid.UUID) -> Path: ...
    def run_root(self, run_id: uuid.UUID) -> Path: ...
    def list_outputs(self, run_id: uuid.UUID) -> list[StoredFile]: ...
    def write_input(self, run_id: uuid.UUID, filename: str, content: bytes) -> str: ...
    def remove_run_dir(self, run_id: uuid.UUID) -> None: ...


class LocalStorage:
    """Stores run files under ``<root>/runs/<run_id>/{inputs,config,outputs}``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def run_root(self, run_id: uuid.UUID) -> Path:
        """Return the run's root directory."""
        return self._root / "runs" / str(run_id)

    def create_run_dir(self, run_id: uuid.UUID) -> None:
        """Create the run's inputs/config/outputs directories."""
        root = self.run_root(run_id)
        for sub in ("inputs", "config", "outputs"):
            (root / sub).mkdir(parents=True, exist_ok=True)

    def config_path(self, run_id: uuid.UUID) -> Path:
        """Return the path to the run's config JSON."""
        return self.run_root(run_id) / "config" / "config.json"

    def write_config(self, run_id: uuid.UUID, config: dict[str, Any]) -> str:
        """Write the tool config JSON; return its path relative to the run root."""
        path = self.config_path(run_id)
        path.write_text(json.dumps(config, indent=2))
        return "config/config.json"

    def input_path(self, run_id: uuid.UUID, filename: str) -> Path:
        """Return the path for an uploaded input file, rejecting traversal."""
        base = (self.run_root(run_id) / "inputs").resolve()
        resolved = (base / filename).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError(f"filename escapes inputs directory: {filename!r}")
        return resolved

    def outputs_dir(self, run_id: uuid.UUID) -> Path:
        """Return the run's outputs directory."""
        return self.run_root(run_id) / "outputs"

    def list_outputs(self, run_id: uuid.UUID) -> list[StoredFile]:
        """Index every file under the run's outputs directory."""
        outputs = self.outputs_dir(run_id)
        files: list[StoredFile] = []
        for path in sorted(p for p in outputs.rglob("*") if p.is_file()):
            rel = path.relative_to(outputs)
            files.append(
                StoredFile(
                    name=path.name,
                    relative_path=str(rel),
                    size_bytes=path.stat().st_size,
                    content_type=mimetypes.guess_type(path.name)[0],
                )
            )
        return files

    def write_input(self, run_id: uuid.UUID, filename: str, content: bytes) -> str:
        """Stage an uploaded input file under ``inputs/``; return its relative path."""
        path = self.input_path(run_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"inputs/{path.name}"

    def remove_run_dir(self, run_id: uuid.UUID) -> None:
        """Best-effort recursive removal of the run's directory tree."""
        shutil.rmtree(self.run_root(run_id), ignore_errors=True)


def get_storage() -> Storage:
    """Return the configured storage backend."""
    return LocalStorage(Path(get_settings().storage_root))
