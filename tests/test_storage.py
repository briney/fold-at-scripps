"""Tests for local filesystem storage."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from fold_at_scripps.storage import LocalStorage


def test_create_run_dir_makes_subdirs(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    root = storage.run_root(run_id)
    assert (root / "inputs").is_dir()
    assert (root / "config").is_dir()
    assert (root / "outputs").is_dir()


def test_write_config_round_trips(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    rel = storage.write_config(run_id, {"num_sequences": 8})
    assert rel == "config/config.json"
    assert json.loads(storage.config_path(run_id).read_text()) == {"num_sequences": 8}


def test_list_outputs_indexes_files(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    (storage.outputs_dir(run_id) / "design.pdb").write_text("ATOM\n")
    outputs = storage.list_outputs(run_id)
    assert len(outputs) == 1
    assert outputs[0].name == "design.pdb"
    assert outputs[0].relative_path == "design.pdb"
    assert outputs[0].size_bytes == 5


def test_input_path_allows_plain_filename(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    path = storage.input_path(run_id, "structure.pdb")
    assert path.name == "structure.pdb"
    assert path.parent.name == "inputs"


def test_input_path_rejects_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    with pytest.raises(ValueError):
        storage.input_path(run_id, "../config/config.json")
