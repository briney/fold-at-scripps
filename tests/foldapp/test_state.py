from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.state import DeployState, read_state, write_state


def test_read_missing_returns_none(tmp_path: Path):
    assert read_state(tmp_path / "nope.json") is None


def test_write_then_read_roundtrip(tmp_path: Path):
    path = tmp_path / "state" / "last_deploy.json"
    state = DeployState(prev_ref="aaa", new_ref="bbb", backup_path="/b/x.sql.gz", timestamp="t0")
    write_state(path, state)
    assert path.is_file()
    assert read_state(path) == state
